"""A model was offered fetches of heavy ore and charcoal its full hands could not take: "my hands are full", 95 tries by
day 107 of the 2026-10-05 live game. Instinct.options leaves such options out (#119, _drafted_runs); with them left
out, a chit whose hands are nearly full is offered to store or put down its load instead."""

from chits.brain.instinct import Instinct
from chits.sim.world import World


def _world():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    return w, a


def _full_but(a, room):
    while a.free_space() > room:
        a.add("stone", 1)


def test_a_models_menu_has_no_fetch_that_cannot_fit():
    w, a = _world()
    ins = Instinct()
    _full_but(a, 0)
    room_made = 0
    for t in range(40):
        w.tick = 1000 + t * 37
        opts = ins.options(w, a)
        room_made += any(o["steps"][0].get("do") in ("store", "drop") for o in opts)
        for o in opts:
            first = next((s for s in o["steps"] if s.get("do") != "go"), {})
            if first.get("do") in ("take", "gather", "pickup"):
                it = w.item(w.norm_item(first.get("what")) or "")
                assert it is None or it.carry_bonus or it.weight <= a.free_space(), o
    assert room_made == 40  # (what it is offered instead: put the load down)
