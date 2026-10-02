"""The road to the Electric Age. The dynamo is an engine, a magnet and two wires, at a factory. No hunch could ever
form that four-ingredient bag (random tries held at most three, and nothing it is made of shares a word with "spins,
makes lightning, humming"), and the village project sought it with no engine anywhere in the stores: World A
searched for 700 days. Now the village makes a discovery's ingredients first, and "something that makes lightning"
has a hunch: a machine that turns, something that pulls iron, and wire to carry it."""

import random

from chits.brain import civic
from chits.sim import projects as PJ
from test_buildings import put, village


def machine_village():
    w, (a, _) = village()
    for k in ("recipe:engine", "recipe:magnet", "recipe:wire", "recipe:steel", "recipe:gear", "recipe:pot",
              "recipe:iron", "recipe:copper", "recipe:charcoal"):
        a.learn(k, "discovered", w.tick)
    for d in ("factory", "forge", "kiln", "furnace", "workshop"):
        put(w, d, a, radius=20)
    w.tick += 1
    return w, a


def road(w):
    designs, recipes = PJ._known(w)
    return PJ.next_step(w, designs, recipes, PJ._stations(w), "recipe", "dynamo")


def test_a_village_makes_an_engine_before_trying_for_the_dynamo():
    w, a = machine_village()
    a.inventory.update({"magnet": 1, "wire": 2})
    assert road(w) == ("make", "engine", {"n": 1, "try": "dynamo"})
    assert PJ.title({"kind": "make", "key": "engine", "n": 1, "try": "dynamo"}) == "make 1 steam engine to try for something new"
    a.inventory["engine"] = 1
    assert road(w) == ("discover", "dynamo", {})


def test_something_that_makes_lightning_is_a_turning_machine_a_magnet_and_wire():
    w, a = machine_village()
    props = set(w.item("dynamo").props)
    bag = civic._hunch(w, random.Random(1), props, ["engine", "magnet", "wire", "wood", "stone"])
    assert sorted(bag) == ["engine", "magnet", "wire", "wire"]
    assert dict(civic.RIDDLE_STATION)["makes lightning"] == "factory"
