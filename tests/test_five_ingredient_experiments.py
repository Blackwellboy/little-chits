"""Issue #2: the steam engine takes 5 inputs (2 steel, 2 gears, a pot), but a near-miss experiment stopped growing its
bag at 4 items, so "right materials, wrong amounts" could never become the engine."""

import random

from chits.brain import instinct as I
from chits.sim import actions
from chits.sim.items import RECIPES

from test_machine_age import build, machine_age_village

CLOSE = "Tried 2 gear + pot + steel at the forge: Right materials, wrong amounts perhaps."


def chit_at_the_forge():
    w, forge, pile = machine_age_village(steel=0, gear=0)
    a = next(iter(w.agents.values()))
    a.x, a.y = forge.center()[0] + 2, forge.center()[1]
    a.inventory.update({"steel": 2, "gear": 2, "pot": 1})
    a.remember(w.tick, CLOSE, 2, "experiment")
    return w, a


def test_the_largest_recipe_sets_the_bag_size():
    assert I.MAX_BAG == max(sum(q for _, q in r.inputs) for r in RECIPES.values()) >= 5


def test_a_near_miss_at_four_items_can_take_the_fifth():
    w, a = chit_at_the_forge()
    ins = I.Instinct()
    ins._world = w
    bags = set()
    for seed in range(40):
        p = ins._near_miss(w, a, random.Random(seed))
        if p:
            step = p["steps"][-1]
            bags.add((tuple(sorted(step["with"])), step.get("at")))
    assert (("gear", "gear", "pot", "steel", "steel"), "forge") in bags, bags


def test_and_the_five_item_bag_at_the_forge_is_the_steam_engine():
    w, a = chit_at_the_forge()
    a.plan = [{"do": "experiment", "with": ["gear", "gear", "pot", "steel", "steel"], "at": "forge"}]
    for _ in range(80):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    assert "recipe:engine" in w.first, a.last_result
