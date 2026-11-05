import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, insert, update, func
import database as db
import economy as e


def now():
    return int(time.time())


def day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def fail(message, code=409):
    raise HTTPException(code, message)


def row(conn, table, uid, lock=False):
    query = select(table).where(table.c.user_id == uid)
    if lock:
        query = query.with_for_update()
    return dict(conn.execute(query).mappings().one())


def record(conn, uid, asset, amount, kind, reference, ts):
    """Post a user entry and equal opposite system-account change atomically."""
    account = row(conn, db.balances, uid, True)
    before = account[asset]
    after = before + amount
    if after < 0:
        fail('Недостаточно ' + asset)
    conn.execute(update(db.balances).where(db.balances.c.user_id == uid).values(**{asset: after}))
    system_id = 'system:' + asset
    system = conn.execute(select(db.ledger_accounts).where(db.ledger_accounts.c.id == system_id).with_for_update()).mappings().one()
    conn.execute(update(db.ledger_accounts).where(db.ledger_accounts.c.id == system_id).values(balance=system['balance'] - amount))
    conn.execute(insert(db.ledger).values(id=str(uuid.uuid4()), user_id=uid, type=kind, asset=asset, amount=amount, before=before, after=after, source=system_id, reference_id=reference, created_at=ts))


def initialize():
    db.migrate()
    with db.transaction() as conn:
        if conn.execute(select(db.events.c.id).where(db.events.c.id == 'egg_rush')).scalar() is None:
            conn.execute(insert(db.events).values(id='egg_rush', title='EGG RUSH', goal=100, reward=35))
        for asset in ['eggs', 'coins']:
            if conn.execute(select(db.ledger_accounts.c.id).where(db.ledger_accounts.c.id == 'system:' + asset)).scalar() is None:
                conn.execute(insert(db.ledger_accounts).values(id='system:' + asset, asset=asset, balance=0))
        if conn.execute(select(db.economy_config.c.version).where(db.economy_config.c.version == e.VERSION)).scalar() is None:
            cfg = {k: v for k, v in vars(e).items() if k.isupper()}
            conn.execute(insert(db.economy_config).values(version=e.VERSION, config=json.dumps(cfg)))


def ensure_user(conn, user, start_param='', ts=None):
    ts = ts or now()
    uid = user['id']
    # PostgreSQL advisory lock serializes concurrent first launches of one identity.
    if db.engine.dialect.name == 'postgresql':
        conn.execute(select(func.pg_advisory_xact_lock(uid)))
    exists = conn.execute(select(db.users.c.id).where(db.users.c.id == uid)).scalar()
    if exists is not None:
        conn.execute(update(db.users).where(db.users.c.id == uid).values(profile=json.dumps(user)))
        return
    conn.execute(insert(db.users).values(id=uid, profile=json.dumps(user), created_at=ts))
    conn.execute(insert(db.balances).values(user_id=uid, eggs=0, coins=0))
    conn.execute(insert(db.game).values(user_id=uid, level=1, pending=0, food=100, water=100, clean=100, last_accrual_at=ts, outfit='Royal Neon', care_at=0, collected=0, cared=0))
    conn.execute(insert(db.items).values(user_id=uid, sku='Royal Neon', created_at=ts))
    record(conn, uid, 'eggs', e.INITIAL_EGGS, 'welcome', 'welcome', ts)
    try:
        ref = int(start_param.removeprefix('ref_')) if start_param.startswith('ref_') else 0
    except (ValueError, AttributeError):
        ref = 0
    if not ref:
        ref = conn.execute(select(db.referral_intents.c.referrer_id).where(db.referral_intents.c.user_id == uid)).scalar() or 0
    # Only a new account can acquire a parent. Parent must predate it; cycles cannot form.
    if uid > 0 and ref > 0 and ref != uid and conn.execute(select(db.users.c.id).where(db.users.c.id == ref)).scalar() is not None:
        conn.execute(insert(db.referrals).values(user_id=uid, referrer_id=ref, created_at=ts))


def snapshot(conn, uid, ts):
    g = row(conn, db.game, uid, True)
    coop = conn.execute(select(db.upgrades.c.level).where(db.upgrades.c.user_id == uid, db.upgrades.c.sku == 'coop')).scalar() or 0
    g['coop_level'] = coop
    e.accrue(g, ts)
    g.pop('coop_level')
    conn.execute(update(db.game).where(db.game.c.user_id == uid).values(**{k:v for k,v in g.items() if k != 'user_id'}))
    b = row(conn, db.balances, uid)
    g.update(eggs=b['eggs'], coins=b['coins'], rate=e.base_rate(g['level']) * (1 + .1 * coop), upgradeCost=e.upgrade_cost(g['level']), rewardClaimed=conn.execute(select(db.daily.c.user_id).where(db.daily.c.user_id == uid, db.daily.c.day == day(ts))).scalar() is not None)
    g['owned'] = list(conn.execute(select(db.items.c.sku).where(db.items.c.user_id == uid)).scalars())
    g['completedTasks'] = {r['task']:True for r in conn.execute(select(db.claims).where(db.claims.c.user_id == uid)).mappings()}
    g['friends'] = conn.execute(select(func.count()).select_from(db.referrals).where(db.referrals.c.referrer_id == uid)).scalar()
    g['history'] = [dict(r) for r in conn.execute(select(db.ledger).where(db.ledger.c.user_id == uid).order_by(db.ledger.c.created_at.desc(), db.ledger.c.id).limit(30)).mappings()]
    sold = conn.execute(select(func.coalesce(func.sum(-db.ledger.c.amount), 0)).where(db.ledger.c.user_id == uid, db.ledger.c.type == 'sell', db.ledger.c.asset == 'eggs', db.ledger.c.created_at >= ts - ts % 86400)).scalar()
    g['sellRemaining'] = max(0, e.SELL_LIMIT - int(sold))
    g['coopUpgrade'] = {'level': coop, 'cost': 100 + 100 * coop * coop, 'max': 10}
    event = conn.execute(select(db.participation).where(db.participation.c.user_id == uid, db.participation.c.event_id == 'egg_rush', db.participation.c.day == day(ts))).mappings().first()
    progress = 0
    if event:
        progress = int(conn.execute(select(func.coalesce(func.sum(db.ledger.c.amount), 0)).where(db.ledger.c.user_id == uid, db.ledger.c.type == 'collect')).scalar()) - event['baseline']
    g['event'] = {'id': 'egg_rush', 'title': 'EGG RUSH', 'goal': 100, 'reward': 35, 'entryCoins': 10, 'joined': bool(event), 'claimed': bool(event and event['claimed_at']), 'progress': min(100, progress), 'endsAt': ts - ts % 86400 + 86400}
    g['catalog'] = {'outfits': e.OUTFITS, 'packages': e.PACKAGES, 'care': e.CARE_COST, 'tasks': e.TASKS, 'daily': e.DAILY_REWARD}
    return g


def act(uid, action, value, key):
    ts = now()
    fingerprint = hashlib.sha256(json.dumps([action, value], sort_keys=True).encode()).hexdigest()
    with db.transaction() as conn:
        row(conn, db.balances, uid, True)
        prev = conn.execute(select(db.operations).where(db.operations.c.user_id == uid, db.operations.c.key == key)).mappings().first()
        if prev:
            if prev['fingerprint'] != fingerprint:
                fail('Idempotency key reused with different operation')
            return json.loads(prev['response'])
        recent = conn.execute(select(func.count()).select_from(db.operations).where(db.operations.c.user_id == uid, db.operations.c.created_at > ts - 60)).scalar()
        if recent >= 30:
            fail('Слишком много действий. Подождите минуту', 429)
        g = snapshot(conn, uid, ts)
        ref = key
        changes = {}
        if action == 'collect':
            amount = int(g['pending'])
            if amount < 1:
                fail('Пока нечего собирать')
            record(conn, uid, 'eggs', amount, action, ref, ts)
            changes = {'pending': g['pending'] - amount, 'collected': g['collected'] + 1}
        elif action == 'care':
            if value not in e.CARE_COST:
                fail('Unknown care', 400)
            if ts - g['care_at'] < 30:
                fail('Подождите 30 секунд между действиями ухода', 429)
            if g[value] >= 99:
                fail('Уход пока не нужен')
            record(conn, uid, 'eggs', -e.CARE_COST[value], action, ref, ts)
            changes = {value: 100, 'care_at': ts, 'cared': g['cared'] + 1}
        elif action == 'upgrade':
            if g['level'] >= e.MAX_LEVEL:
                fail('Максимальный уровень')
            record(conn, uid, 'eggs', -e.upgrade_cost(g['level']), action, ref, ts)
            changes = {'level': g['level'] + 1}
        elif action == 'daily':
            if g['rewardClaimed']:
                fail('Сегодня награда уже получена')
            conn.execute(insert(db.daily).values(user_id=uid, day=day(ts), created_at=ts))
            record(conn, uid, 'eggs', e.DAILY_REWARD, action, ref, ts)
        elif action == 'task':
            if value not in e.TASKS or value in g['completedTasks']:
                fail('Задание недоступно')
            # Actions count is persistent; each task reward is once per account.
            if conn.execute(select(db.claims.c.task).where(db.claims.c.user_id == uid, db.claims.c.task == value)).first():
                fail('Награда уже получена')
            eligible = {'care': g['cared'] > 0, 'collect': g['collected'] > 0, 'invite': g['friends'] > 0}
            if not eligible[value]:
                fail('Сначала выполните задание')
            conn.execute(insert(db.claims).values(user_id=uid, task=value, day=day(ts), created_at=ts))
            record(conn, uid, 'eggs', e.TASKS[value], 'task', ref, ts)
        elif action == 'outfit':
            if value not in e.OUTFITS:
                fail('Unknown outfit', 400)
            if value not in g['owned']:
                record(conn, uid, 'eggs', -e.OUTFITS[value], 'outfit', ref, ts)
                conn.execute(insert(db.items).values(user_id=uid, sku=value, created_at=ts))
            changes = {'outfit': value}
        elif action == 'coop':
            coop = g['coopUpgrade']
            if coop['level'] >= coop['max']:
                fail('Курятник полностью улучшен')
            record(conn, uid, 'coins', -coop['cost'], 'coop', ref, ts)
            if coop['level'] == 0:
                conn.execute(insert(db.upgrades).values(user_id=uid, sku='coop', level=1))
            else:
                conn.execute(update(db.upgrades).where(db.upgrades.c.user_id == uid, db.upgrades.c.sku == 'coop').values(level=coop['level'] + 1))
        elif action == 'event_join':
            if g['event']['joined']:
                fail('Вы уже участвуете')
            record(conn, uid, 'coins', -10, 'event_entry', ref, ts)
            baseline = int(conn.execute(select(func.coalesce(func.sum(db.ledger.c.amount), 0)).where(db.ledger.c.user_id == uid, db.ledger.c.type == 'collect')).scalar())
            conn.execute(insert(db.participation).values(user_id=uid, event_id='egg_rush', day=day(ts), joined_at=ts, baseline=baseline, claimed_at=None))
        elif action == 'event_claim':
            if not g['event']['joined'] or g['event']['claimed'] or g['event']['progress'] < 100:
                fail('Соберите 100 яиц после вступления в событие')
            conn.execute(update(db.participation).where(db.participation.c.user_id == uid, db.participation.c.event_id == 'egg_rush', db.participation.c.day == day(ts)).values(claimed_at=ts))
            record(conn, uid, 'eggs', 35, 'event_reward', ref, ts)
        elif action == 'sell':
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= g['sellRemaining']:
                fail('Лимит продажи: ' + str(g['sellRemaining']))
            record(conn, uid, 'eggs', -value, 'sell', ref, ts)
            # Internal coins only; no TON equivalence or withdrawal promise.
            record(conn, uid, 'coins', value * 2, 'sell', ref, ts)
        else:
            fail('Unknown action', 400)
        if changes:
            conn.execute(update(db.game).where(db.game.c.user_id == uid).values(**changes))
        result = snapshot(conn, uid, ts)
        conn.execute(insert(db.operations).values(user_id=uid, key=key, fingerprint=fingerprint, response=json.dumps(result), created_at=ts))
        conn.execute(insert(db.audit).values(id=str(uuid.uuid4()), user_id=uid, action=action, reference_id=key, created_at=ts))
        return result


def new_order(uid, sku, key):
    if uid <= 0:
        fail('Платежи доступны только в Telegram', 403)
    if sku not in e.PACKAGES:
        fail('Unknown SKU', 400)
    ts = now()
    with db.transaction() as conn:
        row(conn, db.balances, uid, True)
        fingerprint = hashlib.sha256(('order:' + sku).encode()).hexdigest()
        prev = conn.execute(select(db.operations).where(db.operations.c.user_id == uid, db.operations.c.key == key)).mappings().first()
        if prev:
            if prev['fingerprint'] != fingerprint:
                fail('Idempotency key reused')
            saved = json.loads(prev['response'])
            return dict(conn.execute(select(db.orders).where(db.orders.c.id == saved['id'])).mappings().one())
        count = conn.execute(select(func.count()).select_from(db.orders).where(db.orders.c.user_id == uid, db.orders.c.created_at >= ts - ts % 86400)).scalar()
        if count >= 10:
            fail('Дневной лимит заказов', 429)
        package = e.PACKAGES[sku]
        oid = str(uuid.uuid4())
        order = {'id': oid, 'user_id': uid, 'sku': sku, 'stars': package['stars'], 'eggs': package['eggs'], 'payload': 'cocochi:' + oid, 'status': 'pending', 'created_at': ts, 'updated_at': ts}
        conn.execute(insert(db.orders).values(**order))
        conn.execute(insert(db.operations).values(user_id=uid, key=key, fingerprint=fingerprint, response=json.dumps(order), created_at=ts))
        return order


def check_order(conn, uid, payment, require_pending=True):
    order = conn.execute(select(db.orders).where(db.orders.c.payload == payment.get('invoice_payload', '')).with_for_update()).mappings().first()
    if not order or order['user_id'] != uid or payment.get('currency') != 'XTR' or payment.get('total_amount') != order['stars']:
        fail('Payment does not match order', 400)
    if require_pending and (order['status'] != 'pending' or now() - order['created_at'] > 3600):
        fail('Order expired or paid', 400)
    return order


def credit_payment(uid, payment):
    with db.transaction() as conn:
        # Lock ordering matches gameplay: balance, then order, then system account.
        row(conn, db.balances, uid, True)
        order = check_order(conn, uid, payment, False)
        charge = payment.get('telegram_payment_charge_id')
        if not isinstance(charge, str) or not charge or len(charge) > 200:
            fail('Missing charge', 400)
        existing = conn.execute(select(db.payments).where(db.payments.c.charge_id == charge)).mappings().first()
        if existing:
            if existing['order_id'] != order['id']:
                fail('Charge reused', 400)
            return
        if order['status'] != 'pending':
            fail('Order already settled', 400)
        ts = now()
        conn.execute(insert(db.payments).values(charge_id=charge, order_id=order['id'], user_id=uid, amount=order['stars'], status='paid', created_at=ts))
        record(conn, uid, 'eggs', order['eggs'], 'stars_purchase', order['id'], ts)
        conn.execute(update(db.orders).where(db.orders.c.id == order['id']).values(status='paid', updated_at=ts))
        conn.execute(insert(db.audit).values(id=str(uuid.uuid4()), user_id=uid, action='payment', reference_id=order['id'], created_at=ts))


def reserve_checkout(uid, checkout):
    """Accept at most one distinct checkout per order, even across invoice links."""
    with db.transaction() as conn:
        row(conn, db.balances, uid, True)
        order = check_order(conn, uid, checkout)
        previous = conn.execute(select(db.checkouts).where(db.checkouts.c.order_id == order['id'])).mappings().first()
        if previous:
            if previous['query_id'] != checkout['id']:
                fail('Another checkout already accepted for this order', 400)
            return
        conn.execute(insert(db.checkouts).values(order_id=order['id'], query_id=checkout['id'], created_at=now()))
