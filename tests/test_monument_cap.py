"""Monuments by the town, not by the corner. A town that sprawled 70 tiles across kept finding no monument within 20
tiles of where a chit stood, and stood 39 of them for 89 people by day 2,600 (live World A)."""

import random

from chits.brain.instinct import Instinct
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def town(n=14):
    w = World("A", "A", 5, "direct", 128, n)
    w.tick = 40 * TICKS_PER_DAY
    a = next(o for o in w.agents.values() if not o.is_child(w.tick))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = o.health = 95.0
    a.learn("design:monument", "taught", w.tick)
    a.inventory.clear()
    a.inventory.update({"stone": 16, "copper": 4})
    return w, a


def monument_goals(w, a, tries=150):
    ins = Instinct()
    return sum(1 for s in range(tries) if (ins._progress(w, a, random.Random(s)) or {}).get("goal") == "build a monument")


def test_a_town_with_its_monument_out_of_sight_builds_no_second_one():
    w, a = town()
    assert monument_goals(w, a) > 0  # (none anywhere: one is wanted)
    far = w.place_site("monument", *w.find_site("monument", a.x + 30, a.y, 20), a)
    w.complete_structure(far, a)
    assert far.dist(a.x, a.y) > 20  # out of the 20 tiles the chit looks for one in
    assert monument_goals(w, a) == 0
