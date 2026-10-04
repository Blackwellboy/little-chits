"""The hunger margin (actions.HUNGER_MARGIN). Every starvation the harness found had one shape: a chit let its hunger
run low under another step, then could not make the walk to food. Sheltering, warming up, sleeping and storing gave
way to food only below hunger 8, a harvest step counted as fetching food even when it had turned to sowing, and a
meal from the store was three items. Now a chit weighs the ticks its hunger has left against the walk to the nearest
food, and eats a meal when it gets there."""

import pytest

from chits.sim import actions as A
from chits.sim.agent import HUNGER_PER_TICK
from test_buildings import put, village


def _only_store(w, a, dx):
    """A store with grain about dx tiles east, and no other food: no berries, fish or food on the ground."""
    w.nearest_resource = lambda *args, **kw: None
    w.piles_near = lambda *args, **kw: []
    pile = put(w, "stockpile", a, near=(a.x + dx, a.y))
    pile.storage["grain"] = 30
    assert A._stockpile_with(w, a, A.FOODS, 30) is pile
    cx, cy = pile.center()
    return pile, max(abs(cx - a.x), abs(cy - a.y))


def _threshold(d, speed):
    """The hunger below which the margin is short, for a walk of d tiles at this speed."""
    return (A.FOOD_SAFETY * d * A.WALK_COST / speed + A.FOOD_SLACK) * HUNGER_PER_TICK


@pytest.mark.parametrize("verb", ["shelter", "warm_up", "sleep", "store"])
def test_a_chit_far_from_food_leaves_its_reflex_while_it_can_still_make_the_walk(verb, monkeypatch):
    w, (a, _) = village()
    _, d = _only_store(w, a, 24)
    assert d >= 18
    a.hunger = 20.0  # well above 8, where these reflexes gave way before: from 8 it has 36 ticks, for a walk of ~60
    a.plan = [{"do": verb, "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "eat" and a.plan[1]["do"] == verb
    a.plan = [{"do": verb, "_reflex": True}]
    a.inventory["berries"] = 3  # +54 in hand: ample to finish first, then walk
    A.reflexes(w, a)
    assert a.plan[0]["do"] == verb
    a.inventory.clear()
    monkeypatch.setattr(A, "HUNGER_MARGIN", False)  # switched off: hunger 8, as before
    A.reflexes(w, a)
    assert a.plan[0]["do"] == verb


def test_a_chit_beside_food_keeps_to_its_reflex_longer_than_one_far_from_it():
    w, (a, _) = village()
    pile, d = _only_store(w, a, 4)
    assert d <= 8
    a.hunger = 12.0
    a.plan = [{"do": "shelter", "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "shelter"
    w.remove_structure(pile)
    _only_store(w, a, 24)
    a.plan = [{"do": "shelter", "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "eat"


def test_an_exhausted_chit_sets_out_sooner():
    w, (a, _) = village()
    _, d = _only_store(w, a, 14)
    rested = _threshold(d, A._speed(w, a))
    a.energy = 10.0
    tired = _threshold(d, A._speed(w, a))
    assert tired > rested + 2
    a.hunger = (rested + tired) / 2
    a.plan = [{"do": "warm_up", "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "eat"
    a.energy = 90.0
    a.plan = [{"do": "warm_up", "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "warm_up"


def test_a_hungry_chit_sowing_a_farm_goes_to_the_food_instead():
    # seed 27: at hunger 10, with a store 8 tiles off, a chit followed "harvest the farm" 20 tiles to an unripe farm,
    # sowed it, and starved walking back. A harvest step counted as fetching food, so nothing interrupted it
    w, (a, _) = village()
    _only_store(w, a, 6)
    a.hunger = 10.0
    a.plan = [{"do": "harvest", "_s": {"redirect": {"do": "plant", "target": "f1"}}}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "eat" and a.plan[0].get("_reflex") and a.plan[1]["do"] == "harvest"
    ripe = put(w, "farm", a, radius=4)  # even with a ripe farm the nearest food: sowing another one is no meal
    ripe.planted, ripe.growth = True, 1.0
    a.plan = [{"do": "harvest", "target": "f1", "_s": {"redirect": {"do": "plant", "target": "f1"}}}]
    A.reflexes(w, a)
    assert a.plan[0].get("_reflex") and a.plan[0] == {"do": "harvest", "target": ripe.id, "_reflex": True}


def test_a_hungry_chit_harvests_on_when_the_farm_is_the_nearest_food():
    w, (a, _) = village()
    _only_store(w, a, 24)
    farm = put(w, "farm", a)
    farm.planted, farm.growth = True, 1.0
    assert A._farm_ready(w, a) is farm
    a.hunger = 10.0
    a.plan = [{"do": "harvest"}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "harvest"
    a.plan = [{"do": "harvest"}]  # ...but not with a store nearer than the farm
    farm.growth = 0.5
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "eat"


def test_a_starving_chit_eats_a_meal_at_the_store_not_a_bite():
    w, (a, _) = village()
    pile, _ = _only_store(w, a, 3)
    a.hunger = 5.0
    step, s = {"do": "eat", "_reflex": True}, {}
    for _ in range(400):
        w.tick += 1
        if A._do_eat(w, a, step, s) != A.RUNNING:
            break
    # three grain (+36) took it to 41, and it was back in danger soon after
    assert a.hunger >= A.EAT_TO and pile.storage["grain"] == 30 - 6
