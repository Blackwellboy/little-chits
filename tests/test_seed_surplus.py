"""Seeds that pile up for ever (issue #7). Berry pips were the only seeds never used up: one live world held 20,311
seeds by day 2,900, 62% of everything in its stores, and the other 3,436. Pips are kept only while the stores are
short of seed, and mice eat a surplus no granary keeps."""

from chits.sim import actions
from chits.sim import buildings as BLD
from test_buildings import put, village


def picks_with_pips(w, a, home, tries=400):
    """Seeds a chit keeps from this many single berry picks, each set out from beside the village store."""
    got = 0
    for _ in range(tries):
        a.inventory.clear()
        a.x, a.y = home.x, home.y
        s = {}
        for _ in range(400):
            w.tick += 1
            a.hunger = a.energy = a.warmth = 90.0
            if actions._do_gather(w, a, {"do": "gather", "what": "berries", "qty": 1}, s) != actions.RUNNING:
                break
        got += a.inventory.get("seeds", 0)
    return got


def test_berry_pips_are_kept_only_while_the_stores_are_short_of_seed():
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    pile.storage["seeds"] = actions.SEED_PLENTY
    assert picks_with_pips(w, a, pile, 150) == 0
    pile.storage["seeds"] = 0
    assert picks_with_pips(w, a, pile, 150) > 0


def test_mice_eat_surplus_seed_but_not_what_a_village_sows_or_a_granary_keeps():
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    pile.storage["seeds"] = 1000
    BLD._mice(w)
    assert pile.storage["seeds"] == 1000 - int((1000 - BLD.SEED_KEEP) * BLD.MICE_SHARE)
    pile.storage["seeds"] = BLD.SEED_KEEP
    BLD._mice(w)
    assert pile.storage["seeds"] == BLD.SEED_KEEP
    pile.storage["seeds"] = 1000
    put(w, "granary", a, near=(pile.x + 3, pile.y))
    w.tick += 1  # (the working buildings are looked up once a tick)
    BLD._mice(w)
    assert pile.storage["seeds"] == 1000
