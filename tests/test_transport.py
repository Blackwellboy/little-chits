"""Transport (issue #9): a sled before the cart, a wagon after it, and chits that make and carry the best one they
know. Carts were known by a dozen chits in each live world and none was ever made: instinct only made baskets."""

import random

from chits.brain import civic
from chits.brain import instinct as I
from chits.sim.items import RECIPES
from test_buildings import put, village


def test_the_carriers_rise_from_basket_to_wagon():
    w, (a, _) = village()
    caps = {k: w.item(k).carry_bonus - w.item(k).weight for k in ("basket", "sled", "cart", "wagon")}
    assert caps["basket"] < caps["sled"] < caps["cart"] < caps["wagon"]
    base = a.capacity()
    a.inventory["sled"] = 1
    assert a.capacity() == base + w.item("sled").carry_bonus
    assert RECIPES["wagon"].station == "workshop" and dict(RECIPES["wagon"].inputs)["cart"] == 1


def test_a_chit_makes_the_best_carrier_it_knows_and_not_a_worse_one():
    w, (a, _) = village()
    a.learn("recipe:sled", "discovered", w.tick)
    a.inventory.update({"wood": 2, "cord": 1})
    plan = I._better_carrier(w, a)
    assert plan and plan[1]["goal"] == "make a sled"
    a.inventory["cart"] = 1  # it already carries something better
    assert I._better_carrier(w, a) is None


def test_a_cart_in_the_stores_is_fetched():
    w, (a, _) = village()
    a.learn("recipe:cart", "discovered", w.tick)
    pile = put(w, "stockpile", a)
    pile.storage["cart"] = 1
    plan = I._better_carrier(w, a)
    assert plan and plan[1]["steps"] == [{"do": "take", "what": "cart", "qty": 1}]


def test_something_that_hauls_is_a_cart_with_more_wheels_and_iron():
    w, (a, _) = village()
    bag = civic._hunch(w, random.Random(2), set(w.item("wagon").props), ["cart", "wheel", "iron", "wood", "stone"])
    assert sorted(bag) == ["cart", "iron", "wheel", "wheel"]


def test_instinct_gets_round_to_making_one():
    w, (a, _) = village()
    a.learn("recipe:sled", "discovered", w.tick)
    a.inventory.update({"wood": 2, "cord": 1})
    a.hunger = a.energy = a.warmth = a.health = 95.0
    ins = I.Instinct()
    goals = {(ins._progress(w, a, random.Random(s)) or {}).get("goal") for s in range(200)}
    assert "make a sled" in goals


def test_a_chit_who_knows_carts_tries_for_something_that_hauls_and_finds_the_wagon():
    # the wagon's hunch is a curious chit's own try: no age or building made it a village project (Codex, #41), and
    # as one it took the village's one project slot (#58)
    from chits.sim import actions

    w, (a, _) = village()
    a.inventory.clear()
    for k in ("recipe:cart", "recipe:wheel", "recipe:iron"):
        a.learn(k, "taught", w.tick)
    a.inventory.update({"cart": 1, "wheel": 2, "iron": 1})
    a.familiar |= {"cart", "wheel", "iron"}
    ins = I.Instinct()
    ins._world = w

    def tries():
        return [p for p in (ins._haul_idea(w, a, random.Random(s)) for s in range(40)) if p]

    assert not tries()  # no workshop to try it at
    ws = put(w, "workshop", a)
    plans = tries()
    assert plans and 4 <= len(plans) <= 24  # some of the time, not every time
    step = plans[0]["steps"][-1]
    assert step == {"do": "experiment", "with": ["cart", "iron", "wheel", "wheel"], "at": "workshop"}
    # (and it's one of the ideas a chit experimenting has)
    assert any((ins._experiment(w, a, random.Random(s)) or {}).get("steps", [{}])[-1] == step for s in range(40))
    a.x, a.y = next(iter(w.stand_tiles_for_structure(ws)))
    s = {}
    for _ in range(300):
        w.tick += 1
        if actions._do_experiment(w, a, step, s) != actions.RUNNING:
            break
    assert a.knows_recipe("wagon")
    a.inventory.update({"cart": 1, "wheel": 2, "iron": 1})
    assert not tries()  # (known now, with all it needs still to hand)
