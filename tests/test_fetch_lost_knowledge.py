"""Lost knowledge, far away. A loose tablet of something nobody alive still knows is read when it lies within the
read step's own 25 tiles; live World B's only tablet of steel lay 30+ tiles from where anyone went, and steel stayed
lost. A chit now makes a deliberate trip to it (up to 80 tiles, on its own land), and only for what nobody knows."""

import random

from chits.brain.instinct import LOST_TABLET_TRIP, Instinct
from chits.sim import actions
from chits.sim.world import Tablet, World
from test_buildings import grass


def far_tablet(dist=50):
    w = World("A", "A", 5, "direct", 256, 3)
    a = next(iter(w.agents.values()))
    a.hunger = a.energy = a.warmth = a.health = 95.0
    a.traits["curiosity"] = 1.0
    grass(w, a, 100)  # (one land: only the distance can rule a trip out)
    tb = Tablet("t9", "recipe:steel", "gone", "an old smith", w.tick, a.x + dist, a.y, None, "steel is iron and charcoal")
    w.tablets[tb.id] = tb
    for o in w.agents.values():
        o.knows.pop("recipe:steel", None)
    return w, a, tb


def goals(w, a, n=300):
    ins = Instinct()
    return [(ins._communal(w, a, random.Random(s)) or {}) for s in range(n)]


def test_a_chit_fetches_lost_knowledge_from_a_far_tablet_and_learns_it():
    w, a, tb = far_tablet()
    plan = next(p for p in goals(w, a) if p.get("goal") == "fetch lost knowledge")
    assert plan["steps"] == [{"do": "read", "tablet": tb.id}]
    step, s = plan["steps"][0], {}
    for _ in range(900):
        w.tick += 1
        a.hunger = a.energy = a.warmth = 95.0
        if actions.advance(w, a, step) != actions.RUNNING:
            break
    assert "recipe:steel" in a.knows


def test_no_trip_for_what_someone_alive_still_knows_or_for_a_tablet_too_far():
    w, a, tb = far_tablet()
    other = next(o for o in w.agents.values() if o is not a)
    other.learn("recipe:steel", "discovered", w.tick)
    assert not any(p.get("goal") == "fetch lost knowledge" for p in goals(w, a))
    w, a, tb = far_tablet()
    tb.x = a.x + LOST_TABLET_TRIP + 5 if a.x + LOST_TABLET_TRIP + 5 < w.w else a.x - LOST_TABLET_TRIP - 5
    assert not any(p.get("goal") == "fetch lost knowledge" for p in goals(w, a))
