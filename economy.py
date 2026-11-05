"""Versioned, integer-valued game economy. Eggs have no cash value."""
VERSION = 1
INITIAL_EGGS = 120
OFFLINE_CAP = 6 * 3600
MAX_LEVEL = 30
DAILY_REWARD = 30
CARE_COST = {'food': 8, 'water': 5, 'clean': 6}
DECAY = {'food': 3, 'water': 4, 'clean': 2}
OUTFITS = {'Royal Neon': 0, 'Street Gold': 400, 'Cosmic': 800, 'Angel': 1200}
TASKS = {'care': 12, 'collect': 15, 'invite': 20}
PACKAGES = {'eggs_500': {'eggs': 500, 'stars': 50}, 'eggs_1200': {'eggs': 1200, 'stars': 100}}
SELL_LIMIT = 200

def base_rate(level):
    return 20 + 4 * (level - 1)

def upgrade_cost(level):
    return 100 + 50 * level * level

def accrue(state, now):
    """Integrate care decay in minute-sized intervals; retain fractional eggs.

    The cap discards time older than six hours. Timestamp always advances to now;
    clients cannot recover capped production by repeatedly refreshing.
    """
    elapsed = max(0, now - state['last_accrual_at'])
    credited = min(elapsed, OFFLINE_CAP)
    care = {k: float(state[k]) for k in CARE_COST}
    pending = float(state['pending'])
    for offset in range(0, int(credited), 60):
        seconds = min(60, credited - offset)
        mid = {k: max(0, v - DECAY[k] * seconds / 7200) for k, v in care.items()}
        multiplier = .25 + .75 * min(mid.values()) / 100
        pending += base_rate(state['level']) * (1 + .1 * state.get('coop_level', 0)) * multiplier * seconds / 3600
        care = {k: max(0, v - DECAY[k] * seconds / 3600) for k, v in care.items()}
    # Care decays even when offline production is capped.
    for k in care:
        state[k] = max(0, float(state[k]) - DECAY[k] * elapsed / 3600)
    state['pending'] = pending
    state['last_accrual_at'] = max(now, state['last_accrual_at'])
    return state
