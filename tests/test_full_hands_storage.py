"""A chit whose hands are full and whose stores are full builds a new stockpile only from what it carries: a plan
that starts by picking something up fails at once, and came back 56 times in a row (tools/harness, seed 7)."""

from chits.brain.instinct import Instinct
from chits.sim.world import World


def test_a_full_handed_chit_is_not_offered_a_stockpile_it_must_first_pick_up_wood_for():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.knows["design:stockpile"] = {"how": "instinct", "tick": 0, "from": None, "status": "worked"}
    while a.free_space() > 0:
        a.add("stone", 1)
    w.put_ground(a.x + 1, a.y, "wood", 10)
    w.put_ground(a.x + 1, a.y, "cord", 2)
    plan = Instinct._more_storage(w, a)
    assert plan is None or plan["steps"][0]["do"] not in ("gather", "pickup", "take"), plan
