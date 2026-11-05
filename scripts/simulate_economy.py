"""Deterministic policy simulation; not a return or cash-value projection."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import economy as e

print('| scenario | day | earned eggs | spent eggs | balance | level | base/hour | net issuance |')
print('|---|---:|---:|---:|---:|---:|---:|---:|')
for name,visits,payer,cosmetics in [('casual',1,False,False),('active',3,False,True),('heavy',8,False,True),('payer',3,True,True),('non-payer',2,False,True)]:
    state={'level':1,'pending':0,'food':100,'water':100,'clean':100,'last_accrual_at':0}
    balance=e.INITIAL_EGGS; earned=balance;spent=0;owned=set()
    for day in range(1,91):
        balance+=e.DAILY_REWARD;earned+=e.DAILY_REWARD
        if payer and day % 30 == 1:
            balance+=500;earned+=500 # 50 Stars package; no cash-out
        for visit in range(visits):
            ts=int(((day-1)+((visit+1)/visits))*86400)
            e.accrue(state,ts)
            amount=int(state['pending']);state['pending']-=amount;balance+=amount;earned+=amount
            for care,cost in e.CARE_COST.items():
                if state[care]<75 and balance>=cost:
                    balance-=cost;spent+=cost;state[care]=100
            cost=e.upgrade_cost(state['level'])
            if state['level']<e.MAX_LEVEL and balance>=cost+60:
                balance-=cost;spent+=cost;state['level']+=1
            if cosmetics:
                for sku,cost in e.OUTFITS.items():
                    if sku not in owned and cost and balance>=cost+200:
                        balance-=cost;spent+=cost;owned.add(sku);break
        if day in [1,7,30,90]:
            print(f'| {name} | {day} | {earned} | {spent} | {balance} | {state["level"]} | {e.base_rate(state["level"])} | {earned-spent} |')
