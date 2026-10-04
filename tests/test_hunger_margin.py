"""The hunger margin (actions.HUNGER_MARGIN). Every starvation the harness found had one shape: a chit let its hunger
run low under another step, then could not make the walk to food. Sheltering, warming up, sleeping and storing gave
way to food only below hunger 8, a harvest step counted as fetching food even when it had turned to sowing, a starving
chit picking berries ate the first one and went back to what it was doing, and an eat step walked past a store on its
way to another. Now a chit weighs the ticks its hunger has left against the walk to the nearest food."""

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


def test_a_chit_far_from_food_leaves_its_plan_for_food_before_hunger_16():
    w, (a, _) = village()
    _only_store(w, a, 24)
    a.hunger = 20.0
    a.plan = [{"do": "explore"}]
    A.reflexes(w, a)
    assert a.plan[0] == {"do": "eat", "_reflex": True} and a.plan[1]["do"] == "explore"
    a.plan = [{"do": "explore"}]
    a.hunger = 30.0  # ample for a walk of 24 tiles
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "explore"


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


def test_a_starving_chit_picking_berries_eats_the_one_in_hand_and_picks_on():
    # replaced by the eat, the fetch ended at one berry (+18) each time: warm up to hunger 8, eat one, warm up again,
    # until the bushes ran out and the walk to the store was too long (seed 27)
    w, (a, _) = village()
    a.hunger = 5.0
    a.add("berries", 1)
    fetch = {"do": "gather", "what": "berries", "qty": 3, "_reflex": True, "_s": {"got": 1, "want": 3}}
    a.plan = [fetch]
    A.reflexes(w, a)
    assert a.plan == [{"do": "eat", "_reflex": True}, fetch]


def test_a_spear_carrier_with_only_fish_in_reach_counts_the_walk_to_the_fish():
    # the food reflex fishes with a spear when nothing else is in reach, but the margin knew only the other foods: it
    # saw no food at all, and an exhausted spearman sheltered on to hunger 8 (Codex, #100)
    w, (a, _) = village()
    fish = (a.x + 15, a.y)
    w.nearest_resource = lambda x, y, kind, radius=24, avoid=None: (
        fish if kind == "fish" and max(abs(fish[0] - x), abs(fish[1] - y)) <= radius else None)
    w.piles_near = lambda *args, **kw: []
    a.add("spear", 1)
    assert a.best_tool("spear") and not A._food_options(w, a)
    a.energy, a.hunger = 10.0, 15.0  # exhausted: 15 tiles is ~90 ticks on foot, and it has ~68
    a.plan = [{"do": "shelter", "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0] == {"do": "gather", "what": "fish", "qty": 3, "_reflex": True} and a.plan[1]["do"] == "shelter"


def test_a_harvest_naming_a_far_farm_is_judged_by_that_farm_not_a_nearer_one():
    # the margin and the "already fetching food" exemption looked at the nearest ripe farm, while the step walked to
    # the far one it named (Codex, #100)
    w, (a, _) = village()
    w.nearest_resource = lambda *args, **kw: None
    w.piles_near = lambda *args, **kw: []
    near = put(w, "farm", a, radius=4)
    far = put(w, "farm", a, near=(a.x + 22, a.y))
    for f in (near, far):
        f.planted, f.growth = True, 1.0
    assert A._farm_ready(w, a) is near and far.dist(a.x, a.y) >= 16
    for hunger in (12.0, 18.0):  # below 16; and above it, short only for the walk to the far farm
        a.hunger = hunger
        a.plan = [{"do": "harvest", "target": far.id}]
        A.reflexes(w, a)
        assert a.plan[0] == {"do": "harvest", "target": near.id, "_reflex": True}, hunger
        assert a.plan[1]["target"] == far.id
    a.plan = [{"do": "harvest", "target": near.id}]  # the near one named: harvesting it is the fetch
    A.reflexes(w, a)
    assert len(a.plan) == 1 and a.plan[0]["target"] == near.id and not a.plan[0].get("_reflex")


def test_an_eat_step_takes_food_from_a_store_it_passes_once():
    # kept to the store it set out for, 30 tiles round a lake, a child walked by a store 2 tiles off with 114 food in
    # it and starved a few tiles short of the first (seed 42)
    w, (a, _) = village()
    a.hunger = 5.0
    far = put(w, "stockpile", a, near=(a.x + 12, a.y))
    near = put(w, "stockpile", a, near=(a.x, a.y), radius=2)
    other = put(w, "stockpile", a, near=(a.x, a.y), radius=3)
    for st in (far, near, other):
        st.storage["grain"] = 20
    assert near.dist(a.x, a.y) <= A.PASSING_STORE < far.dist(a.x, a.y)
    s = {"store": far.id}
    A._do_eat(w, a, {"do": "eat"}, s)
    assert s["store"] == near.id
    a.inventory.clear()
    s["store"] = other.id  # once: two stores can't take turns
    A._do_eat(w, a, {"do": "eat"}, s)
    assert s["store"] == other.id

