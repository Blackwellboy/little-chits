"""Fires fed from the stores. A fire burning low was fed with freshly chopped wood, whatever lay in the stores: in
two days from the live save, 88 trips to chop wood for fires while 7,600 wood sat stored in World A. Wood in hand
first, then the stores, and only with none stored nearby does a chit go chopping."""

from chits.brain import instinct as I
from test_buildings import put, village


def test_fuel_comes_from_hand_then_the_stores_then_the_woods():
    w, (a, _) = village()
    a.inventory.clear()
    assert I._fuel_steps(w, a) == [{"do": "gather", "what": "wood", "qty": 2}]
    pile = put(w, "stockpile", a)
    pile.storage["wood"] = 40
    assert I._fuel_steps(w, a) == [{"do": "take", "what": "wood", "qty": 2}]
    a.inventory["wood"] = 2
    assert I._fuel_steps(w, a) == []


def test_a_cold_chit_feeds_the_fire_from_the_stores(monkeypatch):
    w, (a, _) = village()
    a.inventory.clear()
    a.learn("design:campfire", "taught", w.tick)
    fire = put(w, "campfire", a)
    fire.fuel = 0.0
    pile = put(w, "stockpile", a)
    pile.storage["wood"] = 40
    monkeypatch.setattr(type(w), "season", property(lambda self: "winter"))
    a.hunger = a.energy = a.warmth = 80.0
    import random
    plan = I.Instinct()._survive(w, a, random.Random(1))
    assert plan and plan["goal"] == "keep the fire going"
    assert plan["steps"][0] == {"do": "take", "what": "wood", "qty": 2}


def test_one_in_hand_and_one_stored_is_enough():
    # a chit holding one wood went chopping two while one lay in the stores (Codex, #44)
    w, (a, _) = village()
    a.inventory.clear()
    a.inventory["wood"] = 1
    pile = put(w, "stockpile", a)
    pile.storage["wood"] = 1
    assert I._fuel_steps(w, a) == [{"do": "take", "what": "wood", "qty": 1}]
    pile.storage["wood"] = 0
    assert I._fuel_steps(w, a) == [{"do": "gather", "what": "wood", "qty": 1}]
