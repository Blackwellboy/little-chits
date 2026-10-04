"""A chit whose hands are full and whose stores are full builds a new stockpile only from what it carries: a plan
that starts by picking something up, or taking it from a store, fails at once and came back 56 times in a row
(tools/harness, seed 7)."""

from chits.brain.instinct import Instinct
from chits.sim.world import World


def _full_handed():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.knows["design:stockpile"] = {"how": "instinct", "tick": 0, "from": None, "status": "worked"}
    while a.free_space() > 0:
        a.add("stone", 1)
    return w, a


def _starts_by_fetching(plan):
    return plan is not None and plan["steps"][0]["do"] in ("gather", "pickup", "take")


def test_a_full_handed_chit_is_not_offered_a_stockpile_it_must_first_pick_up_wood_for():
    w, a = _full_handed()
    w.put_ground(a.x + 1, a.y, "wood", 10)
    w.put_ground(a.x + 1, a.y, "cord", 2)
    plan = Instinct._more_storage(w, a)
    assert not _starts_by_fetching(plan), plan


def test_nor_one_it_must_first_take_wood_from_a_full_store_for():
    # the materials are in a store: the plan would start by taking them (Codex, #91)
    w, a = _full_handed()
    pos = w.find_site("stockpile", a.x + 3, a.y, 10)
    pile = w.place_site("stockpile", pos[0], pos[1], a)
    w.complete_structure(pile, a)
    pile.storage.update({"wood": 10, "cord": 2})
    steps_before = Instinct._more_storage(w, a)
    assert not _starts_by_fetching(steps_before), steps_before
