"""Operator-only refund command. Never expose as an unauthenticated endpoint.

Reserves/revokes purchased eggs before calling Telegram. A lost HTTP response
leaves refund_pending for operator reconciliation, never automatic release.
"""
import asyncio
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,update,insert
import database as db
import game_service as game
from server import tg_call

async def refund(order_id):
    with db.transaction() as conn:
        order=conn.execute(select(db.orders).where(db.orders.c.id==order_id)).mappings().one()
        uid=order['user_id']
        game.row(conn,db.balances,uid,True)
        order=conn.execute(select(db.orders).where(db.orders.c.id==order_id).with_for_update()).mappings().one()
        if order['status']!='paid':raise RuntimeError('Order is not paid; reconcile pending/refunded orders manually')
        payment=conn.execute(select(db.payments).where(db.payments.c.order_id==order_id)).mappings().one()
        game.record(conn,uid,'eggs',-order['eggs'],'refund_reserve','refund:'+order_id,game.now())
        conn.execute(update(db.orders).where(db.orders.c.id==order_id).values(status='refund_pending',updated_at=game.now()))
        charge=payment['charge_id']
    # On failure keep the reservation: the provider may have processed the refund.
    await tg_call('refundStarPayment',{'user_id':uid,'telegram_payment_charge_id':charge})
    with db.transaction() as conn:
        conn.execute(update(db.orders).where(db.orders.c.id==order_id).values(status='refunded',updated_at=game.now()))
        conn.execute(update(db.payments).where(db.payments.c.charge_id==charge).values(status='refunded'))
        conn.execute(insert(db.audit).values(id=str(uuid.uuid4()),user_id=uid,action='refund',reference_id=order_id,created_at=game.now()))

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python scripts/refund_order.py ORDER_ID')
    asyncio.run(refund(sys.argv[1]))
