"""A hungry chit's plan uses the stores and farms its steps can reach: one a walk found to be a long way round on foot
is marked unreachable for a day, and the plan must not choose it again (it did, every tick, until the chit starved
with food a few tiles off: seed 42, 60 days, found in the F35 work)."""

import random

from chits.brain.instinct import Instinct
from chits.sim.world import World


def _world():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.inventory.clear()
        o.plan = []
    a.hunger, a.energy, a.warmth, a.health = 30.0, 90.0, 90.0, 90.0
    a.inventory.clear()
    return w, a


def _build(w, a, design, dx):
    pos = w.find_site(design, a.x + dx, a.y, 10)
    s = w.place_site(design, pos[0], pos[1], a)
    w.complete_structure(s, a)
    return s


def test_a_store_marked_a_long_way_round_is_not_planned_for_again():
    w, a = _world()
    pile = _build(w, a, "stockpile", 4)
    pile.storage["berries"] = 20
    plan = Instinct()._survive(w, a, random.Random(1))
    assert plan and plan["goal"] == "eat from the stores"
    a.reflex_rest["unreach:" + pile.id] = w.tick + 240  # the eat step found it a long way round on foot
    plan = Instinct()._survive(w, a, random.Random(1))
    assert plan and plan["goal"] != "eat from the stores", plan


def test_a_farm_marked_a_long_way_round_is_not_planned_for_again():
    w, a = _world()
    farm = _build(w, a, "farm", 4)
    farm.planted, farm.growth = True, 1.0
    plan = Instinct()._survive(w, a, random.Random(1))
    assert plan and plan["goal"] == "harvest the farm"
    a.reflex_rest["unreach:" + farm.id] = w.tick + 240
    plan = Instinct()._survive(w, a, random.Random(1))
    assert plan and plan["goal"] != "harvest the farm", plan
