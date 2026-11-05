import os
import tempfile
import unittest
import json
import time
import uuid
import hmac
import hashlib
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, AsyncMock

TEMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite:///' + TEMP.name + '/game.sqlite3')
os.environ['BOT_TOKEN'] = ''
os.environ['PUBLIC_BASE_URL'] = ''
os.environ['TELEGRAM_WEBHOOK_SECRET'] = ''
from fastapi.testclient import TestClient
from sqlalchemy import select, update, func
import server
import database as db
import game_service as game
import economy


def signed(uid, token='test-token', date=None, start=''):
    pairs={'auth_date':str(int(time.time()) if date is None else date), 'user':json.dumps({'id':uid,'first_name':'Test'})}
    if start:
        pairs['start_param']=start
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    pairs['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(pairs.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(pairs)


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        game.initialize()

    def setUp(self):
        self.client=TestClient(server.app)
        r=self.client.post('/api/session',json={'initData':''})
        self.assertEqual(r.status_code,200)
        self.uid=self.client.get('/api/game').json()['user_id']

    def action(self, action, value=None, key=None):
        return self.client.post('/api/game/action',json={'action':action,'value':value},headers={'X-Cocochi-Request':'1','Idempotency-Key':key or str(uuid.uuid4())})

    def test_no_auth_and_csrf(self):
        self.assertEqual(TestClient(server.app).get('/api/game').status_code,401)
        self.assertEqual(self.client.post('/api/game/action',json={'action':'daily'}).status_code,403)
        self.assertEqual(self.client.post('/api/game/action',json={'action':'daily'},headers={'X-Cocochi-Request':'1','Origin':'https://evil.example'}).status_code,403)

    def test_daily_idempotent_and_atomic(self):
        key=str(uuid.uuid4())
        r=self.action('daily',key=key); self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['eggs'],economy.INITIAL_EGGS+economy.DAILY_REWARD)
        self.assertEqual(self.action('daily',key=key).json(),r.json())
        self.assertEqual(self.action('collect',key=key).status_code,409)
        self.assertEqual(self.action('daily').status_code,409)
        with db.engine.connect() as c:
            rows=c.execute(select(db.ledger).where(db.ledger.c.user_id==self.uid,db.ledger.c.type=='daily')).all()
            self.assertEqual(len(rows),1)

    def test_persistence_across_clients(self):
        self.action('daily')
        second=TestClient(server.app);second.cookies.update(self.client.cookies)
        self.assertEqual(second.get('/api/game').json()['eggs'],150)
        with db.engine.connect() as c:
            self.assertEqual(c.execute(select(db.balances.c.eggs).where(db.balances.c.user_id==self.uid)).scalar(),150)

    def test_cannot_claim_unperformed_task_or_overspend(self):
        self.assertEqual(self.action('task','collect').status_code,409)
        self.assertEqual(self.action('upgrade').status_code,409)
        self.assertEqual(self.client.get('/api/game').json()['eggs'],120)
        self.assertEqual(self.action('sell',121).status_code,409)
        self.assertEqual(self.action('sell',True).status_code,422)

    def test_collect_cap_and_clock(self):
        with db.transaction() as c:
            c.execute(update(db.game).where(db.game.c.user_id==self.uid).values(last_accrual_at=int(time.time())-3600*24))
        g=self.client.get('/api/game').json()
        self.assertGreater(g['pending'],0);self.assertLessEqual(g['pending'],120)
        r=self.action('collect');self.assertEqual(r.status_code,200)
        eggs=r.json()['eggs'];self.assertLessEqual(eggs,240)
        self.assertEqual(self.action('collect').status_code,409)
        self.assertEqual(self.action('task','collect').status_code,200)
        self.assertEqual(self.action('task','collect').status_code,409)

    def test_concurrent_daily_single_credit(self):
        def run(_):
            try: return game.act(self.uid,'daily',None,str(uuid.uuid4()))
            except server.HTTPException: return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(run,range(6)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.client.get('/api/game').json()['eggs'],150)

    def test_internal_market(self):
        r=self.action('sell',20);self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['eggs'],100);self.assertEqual(r.json()['coins'],40)
        self.assertEqual(r.json()['sellRemaining'],180)
        self.assertEqual(self.client.post('/api/withdrawals',headers={'X-Cocochi-Request':'1'}).status_code,403)

    def test_signature_and_expiry(self):
        with patch.object(server,'BOT_TOKEN','test-token'):
            self.assertEqual(server.validate_init_data(signed(99))['user']['id'],99)
            for data in [signed(99,date=0),signed(99,date=int(time.time())+100),signed(99,date=int(time.time())-4000),signed(99)+'&user=bad',signed(99,token='wrong')]:
                with self.assertRaises(server.HTTPException):server.validate_init_data(data)
        with patch.object(server,'DEMO_ENABLED',False):
            with self.assertRaises(server.HTTPException):server.validate_init_data('')

    def test_referral_fixed_on_first_launch(self):
        a,b=12345+int(time.time()),12346+int(time.time())
        with db.transaction() as c:
            game.ensure_user(c,{'id':a})
            game.ensure_user(c,{'id':b},'ref_'+str(a))
            game.ensure_user(c,{'id':b},'ref_'+str(b))
            self.assertEqual(c.execute(select(db.referrals.c.referrer_id).where(db.referrals.c.user_id==b)).scalar(),a)
            game.ensure_user(c,{'id':a},'ref_'+str(b))
            self.assertIsNone(c.execute(select(db.referrals.c.referrer_id).where(db.referrals.c.user_id==a)).scalar())

    def test_payment_match_and_duplicate_webhook(self):
        uid=uuid.uuid4().int % 2**48 + 1
        with db.transaction() as c: game.ensure_user(c,{'id':uid})
        order=game.new_order(uid,'eggs_500',str(uuid.uuid4()))
        payment={'invoice_payload':order['payload'],'currency':'XTR','total_amount':50,'telegram_payment_charge_id':str(uuid.uuid4())}
        with self.assertRaises(server.HTTPException):game.credit_payment(uid,{**payment,'total_amount':1})
        game.credit_payment(uid,payment);game.credit_payment(uid,payment)
        with db.engine.connect() as c:
            self.assertEqual(c.execute(select(db.balances.c.eggs).where(db.balances.c.user_id==uid)).scalar(),620)
            self.assertEqual(c.execute(select(func.count()).select_from(db.payments).where(db.payments.c.user_id==uid)).scalar(),1)

    def test_webhook_requires_secret(self):
        self.assertEqual(self.client.post('/telegram/webhook',json={}).status_code,403)

    def test_assets_and_manifest(self):
        for path in ['/app','/healthz','/tonconnect-manifest.json','/static/v2.js','/static/v2.css']:
            self.assertEqual(self.client.get(path).status_code,200)

    def test_event_progress_and_duplicate_reward(self):
        self.action('sell',10)
        self.assertEqual(self.action('event_join').status_code,200)
        self.assertEqual(self.action('event_claim').status_code,409)
        with db.transaction() as c:
            c.execute(update(db.game).where(db.game.c.user_id==self.uid).values(pending=100))
        self.assertEqual(self.action('collect').status_code,200)
        r=self.action('event_claim');self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['event']['claimed'])
        self.assertEqual(self.action('event_claim').status_code,409)

    def test_coop_and_wardrobe_no_double_charge(self):
        self.action('sell',100)
        r=self.action('coop');self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['coopUpgrade']['level'],1)
        self.assertEqual(r.json()['coins'],100)
        self.assertAlmostEqual(r.json()['rate'],22)
        self.assertEqual(self.action('outfit','Royal Neon').status_code,200)
        self.assertEqual(self.action('outfit','made-up').status_code,400)

    def test_payment_webhook_and_precheckout(self):
        uid=uuid.uuid4().int%2**48+1
        with db.transaction() as c:game.ensure_user(c,{'id':uid})
        order=game.new_order(uid,'eggs_500',str(uuid.uuid4()))
        payload={'invoice_payload':order['payload'],'currency':'XTR','total_amount':50}
        with patch.object(server,'WEBHOOK_SECRET','test-secret'),patch.object(server,'STARS_ENABLED',True),patch.object(server,'tg_call',new_callable=AsyncMock) as call:
            r=self.client.post('/telegram/webhook',json={'pre_checkout_query':{'id':str(uuid.uuid4()),'from':{'id':uid},**payload}},headers={'X-Telegram-Bot-Api-Secret-Token':'test-secret'})
            self.assertEqual(r.status_code,200);self.assertTrue(call.call_args.args[1]['ok'])
            duplicate={'pre_checkout_query':{'id':str(uuid.uuid4()),'from':{'id':uid},**payload}}
            self.client.post('/telegram/webhook',json=duplicate,headers={'X-Telegram-Bot-Api-Secret-Token':'test-secret'})
            self.assertFalse(call.call_args.args[1]['ok'])
            with db.engine.connect() as c:self.assertEqual(c.execute(select(db.balances.c.eggs).where(db.balances.c.user_id==uid)).scalar(),120)
            message={'from':{'id':uid},'successful_payment':{**payload,'telegram_payment_charge_id':str(uuid.uuid4())}}
            for _ in range(2):self.assertEqual(self.client.post('/telegram/webhook',json={'message':message},headers={'X-Telegram-Bot-Api-Secret-Token':'test-secret'}).status_code,200)
            with db.engine.connect() as c:self.assertEqual(c.execute(select(db.balances.c.eggs).where(db.balances.c.user_id==uid)).scalar(),620)

    def test_refund_reservation_and_confirmation(self):
        import asyncio
        from scripts import refund_order
        uid=uuid.uuid4().int%2**48+1
        with db.transaction() as c:game.ensure_user(c,{'id':uid})
        order=game.new_order(uid,'eggs_500',str(uuid.uuid4()))
        game.credit_payment(uid,{'invoice_payload':order['payload'],'currency':'XTR','total_amount':50,'telegram_payment_charge_id':str(uuid.uuid4())})
        with patch.object(refund_order,'tg_call',new_callable=AsyncMock) as call:
            asyncio.run(refund_order.refund(order['id']))
            self.assertEqual(call.call_args.args[0],'refundStarPayment')
        with db.engine.connect() as c:
            self.assertEqual(c.execute(select(db.orders.c.status).where(db.orders.c.id==order['id'])).scalar(),'refunded')
            self.assertEqual(c.execute(select(db.balances.c.eggs).where(db.balances.c.user_id==uid)).scalar(),120)
        with self.assertRaises(RuntimeError):asyncio.run(refund_order.refund(order['id']))

    def test_refund_uncertain_result_stays_reserved(self):
        import asyncio
        from scripts import refund_order
        uid=uuid.uuid4().int%2**48+1
        with db.transaction() as c:game.ensure_user(c,{'id':uid})
        order=game.new_order(uid,'eggs_500',str(uuid.uuid4()))
        game.credit_payment(uid,{'invoice_payload':order['payload'],'currency':'XTR','total_amount':50,'telegram_payment_charge_id':str(uuid.uuid4())})
        with patch.object(refund_order,'tg_call',new_callable=AsyncMock,side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):asyncio.run(refund_order.refund(order['id']))
        with db.engine.connect() as c:
            self.assertEqual(c.execute(select(db.orders.c.status).where(db.orders.c.id==order['id'])).scalar(),'refund_pending')
            self.assertEqual(c.execute(select(db.balances.c.eggs).where(db.balances.c.user_id==uid)).scalar(),120)

    def test_ledger_reconciles(self):
        self.action('daily');self.action('sell',20)
        with db.engine.connect() as c:
            for asset in ['eggs','coins']:
                total=c.execute(select(func.sum(db.ledger.c.amount)).where(db.ledger.c.asset==asset)).scalar() or 0
                system=c.execute(select(db.ledger_accounts.c.balance).where(db.ledger_accounts.c.id=='system:'+asset)).scalar()
                balances=c.execute(select(func.sum(db.balances.c[asset]))).scalar() or 0
                self.assertEqual(total,balances);self.assertEqual(total+system,0)

if __name__=='__main__':unittest.main()
