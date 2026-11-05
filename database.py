"""Portable schema v1. PostgreSQL in production; file-backed SQLite locally."""
import os
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import (create_engine, MetaData, Table, Column, String, BigInteger,
                        Integer, Float, Text, CheckConstraint, UniqueConstraint, select, insert)

url = os.getenv('DATABASE_URL') or 'sqlite:///' + str(Path(__file__).resolve().parent / 'data' / 'game.sqlite3')
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql+psycopg://', 1)
elif url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
PRODUCTION = os.getenv('APP_ENV') == 'production'
if PRODUCTION and not url.startswith('postgresql+psycopg://'):
    raise RuntimeError('Production requires persistent PostgreSQL DATABASE_URL')
if url.startswith('sqlite:///'):
    Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(url, pool_pre_ping=True, **({'connect_args': {'timeout': 30}} if url.startswith('sqlite:') else {}))
meta = MetaData()
schema_versions = Table('schema_versions', meta, Column('version', Integer, primary_key=True))
users = Table('users', meta, Column('id', BigInteger, primary_key=True), Column('profile', Text, nullable=False), Column('created_at', BigInteger, nullable=False))
balances = Table('user_balances', meta, Column('user_id', BigInteger, primary_key=True), Column('eggs', BigInteger, nullable=False), Column('coins', BigInteger, nullable=False), CheckConstraint('eggs >= 0 AND coins >= 0'))
game = Table('game_state', meta, Column('user_id', BigInteger, primary_key=True), Column('level', Integer, nullable=False), Column('pending', Float, nullable=False), Column('food', Float, nullable=False), Column('water', Float, nullable=False), Column('clean', Float, nullable=False), Column('last_accrual_at', BigInteger, nullable=False), Column('outfit', String(40), nullable=False), Column('care_at', BigInteger, nullable=False, default=0), Column('collected', Integer, nullable=False, default=0), Column('cared', Integer, nullable=False, default=0))
ledger_accounts = Table('ledger_accounts', meta, Column('id', String(80), primary_key=True), Column('asset', String(10), nullable=False), Column('balance', BigInteger, nullable=False))
ledger = Table('ledger_entries', meta, Column('id', String(36), primary_key=True), Column('user_id', BigInteger, nullable=False), Column('type', String(40), nullable=False), Column('asset', String(10), nullable=False), Column('amount', BigInteger, nullable=False), Column('before', BigInteger, nullable=False), Column('after', BigInteger, nullable=False), Column('source', String(80), nullable=False), Column('reference_id', String(100), nullable=False), Column('created_at', BigInteger, nullable=False), UniqueConstraint('user_id', 'asset', 'reference_id'))
operations = Table('operations', meta, Column('user_id', BigInteger, primary_key=True), Column('key', String(80), primary_key=True), Column('fingerprint', String(64), nullable=False), Column('response', Text, nullable=False), Column('created_at', BigInteger, nullable=False))
orders = Table('orders', meta, Column('id', String(36), primary_key=True), Column('user_id', BigInteger, nullable=False), Column('sku', String(40), nullable=False), Column('stars', Integer, nullable=False), Column('eggs', Integer, nullable=False), Column('payload', String(100), unique=True, nullable=False), Column('status', String(30), nullable=False), Column('created_at', BigInteger, nullable=False), Column('updated_at', BigInteger, nullable=False))
payments = Table('payments', meta, Column('charge_id', String(200), primary_key=True), Column('order_id', String(36), unique=True, nullable=False), Column('user_id', BigInteger, nullable=False), Column('amount', Integer, nullable=False), Column('status', String(30), nullable=False), Column('created_at', BigInteger, nullable=False))
referrals = Table('referrals', meta, Column('user_id', BigInteger, primary_key=True), Column('referrer_id', BigInteger, nullable=False), Column('created_at', BigInteger, nullable=False))
claims = Table('task_claims', meta, Column('user_id', BigInteger, primary_key=True), Column('task', String(40), primary_key=True), Column('day', String(10), primary_key=True), Column('created_at', BigInteger, nullable=False))
daily = Table('daily_rewards', meta, Column('user_id', BigInteger, primary_key=True), Column('day', String(10), primary_key=True), Column('created_at', BigInteger, nullable=False))
items = Table('user_items', meta, Column('user_id', BigInteger, primary_key=True), Column('sku', String(40), primary_key=True), Column('created_at', BigInteger, nullable=False))
sessions = Table('sessions', meta, Column('token_hash', String(64), primary_key=True), Column('user_id', BigInteger, nullable=False), Column('expires_at', BigInteger, nullable=False))
audit = Table('audit_log', meta, Column('id', String(36), primary_key=True), Column('user_id', BigInteger, nullable=False), Column('action', String(40), nullable=False), Column('reference_id', String(100), nullable=False), Column('created_at', BigInteger, nullable=False))
economy_config = Table('economy_config', meta, Column('version', Integer, primary_key=True), Column('config', Text, nullable=False))
# Disabled settlement scaffold: no automated signing or pretend confirmations.
withdrawals = Table('withdrawals', meta, Column('id', String(36), primary_key=True), Column('user_id', BigInteger, nullable=False), Column('amount', BigInteger, nullable=False), Column('status', String(20), nullable=False), Column('created_at', BigInteger, nullable=False))

@contextmanager
def transaction():
    with engine.connect() as conn:
        if engine.dialect.name == 'sqlite':
            conn.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            conn.begin()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

def migrate():
    # Future schema changes must be explicit numbered migrations, not create_all.
    meta.create_all(engine)
    with transaction() as conn:
        if conn.execute(select(schema_versions.c.version)).scalar() is None:
            conn.execute(insert(schema_versions).values(version=1))

referral_intents = Table('referral_intents', meta, Column('user_id', BigInteger, primary_key=True), Column('referrer_id', BigInteger, nullable=False), Column('created_at', BigInteger, nullable=False))
events = Table('events', meta, Column('id', String(40), primary_key=True), Column('title', String(80), nullable=False), Column('goal', Integer, nullable=False), Column('reward', Integer, nullable=False))
participation = Table('event_participation', meta, Column('user_id', BigInteger, primary_key=True), Column('event_id', String(40), primary_key=True), Column('day', String(10), primary_key=True), Column('joined_at', BigInteger, nullable=False), Column('baseline', BigInteger, nullable=False), Column('claimed_at', BigInteger, nullable=True))
upgrades = Table('inventory', meta, Column('user_id', BigInteger, primary_key=True), Column('sku', String(40), primary_key=True), Column('level', Integer, nullable=False))
checkouts = Table('payment_checkouts', meta, Column('order_id', String(36), primary_key=True), Column('query_id', String(200), unique=True, nullable=False), Column('created_at', BigInteger, nullable=False))
