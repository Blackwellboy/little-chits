"""Transport (issue #9, #168): what rolls goes faster on a road, and the motor car is a wagon that pulls itself
(actions.TRANSPORT)."""

import random

import pytest

from chits.brain import civic
from chits.brain import instinct as INS
from chits.sim import actions
from chits.sim.items import RECIPES, match_recipe
from chits.views import agent_brief
from test_buildings import village


def _ticks_down_a_road(monkeypatch, on: bool, carry: str = "") -> int:
    monkeypatch.setattr(actions, "TRANSPORT", on)
    w, (a, _) = village(size=96)
    a.inventory.clear()
    if carry:
        a.add(carry, 1)
    y = a.y
    xs = [x for x in range(4, w.w - 4) if all(w.passable(x + d, y) for d in range(12))]
    x0 = xs[0]
    for x in range(x0, x0 + 12):
        w.roads.add(y * w.w + x)
    a.x, a.y, a.path, a.move_acc = x0, y, [], 0.0
    s, n = {}, 0
    while actions.move_toward(w, a, s, {(x0 + 11, y)}) != "arrived" and n < 500:
        n += 1
    return n


def test_a_motor_car_crosses_a_road_far_faster_and_a_wagon_a_little(monkeypatch):
    walk = _ticks_down_a_road(monkeypatch, True)
    car = _ticks_down_a_road(monkeypatch, True, "motor_car")
    wagon = _ticks_down_a_road(monkeypatch, True, "wagon")
    assert car * 2 <= walk and car < wagon < walk
    assert actions.road_speed(type("A", (), {"inventory": {"motor_car": 1, "cart": 1}})()) == actions.ROAD_SPEED["motor_car"]


def test_without_transport_a_road_is_as_fast_for_everyone(monkeypatch):
    assert _ticks_down_a_road(monkeypatch, False, "motor_car") == _ticks_down_a_road(monkeypatch, False)


def test_the_motor_car_is_a_wagon_an_engine_and_steel_at_a_factory_and_the_hunch_finds_it():
    r = RECIPES["motor_car"]
    assert dict(r.inputs) == {"wagon": 1, "engine": 1, "steel": 2} and r.station == "factory"
    w, _ = village()
    bag = civic._hunch(w, random.Random(1), set(w.item("motor_car").props), ["wagon", "engine", "steel", "wood"])
    assert sorted(bag) == ["engine", "steel", "steel", "wagon"]
    assert match_recipe({k: bag.count(k) for k in bag}, "factory").key == "motor_car"


def test_the_motor_car_is_the_best_carrier_and_is_what_the_view_draws():
    assert INS.CARRIERS[0] == "motor_car"
    w, (a, _) = village()
    a.inventory.clear()
    a.add("wagon", 1)
    a.add("motor_car", 1)
    assert agent_brief(w, a)["vehicle"] == "motor_car"


@pytest.mark.parametrize("on", [True, False])
def test_switched_off_nothing_finds_teaches_or_hands_out_a_motor_car(on, monkeypatch):
    """Off, the world draws as the tree before it did: chests, alien teachers, hints and experiments never reach it."""
    from chits.sim import artifacts, items
    monkeypatch.setattr(actions, "TRANSPORT", on)
    assert ("motor_car" in items.hidden()) is (not on) and "rocket" in items.hidden()
    w, _ = village()
    assert ("motor_car" in artifacts.undiscovered(w)) is on


def test_a_car_is_made_only_from_a_spare_engine_and_never_switched_off(monkeypatch):
    """Engines are the factories', pumps' and rockets' first: a car takes one only when the stores hold spares."""
    w, (a, _) = village()
    a.inventory.clear()
    a.learn("recipe:motor_car", "taught", w.tick)
    monkeypatch.setattr(INS, "_craft_steps", lambda a, k, world=None: [{"do": "craft", "what": k}])
    stock = {"engine": 0}
    monkeypatch.setattr(INS, "_stock_near", lambda world, a, k, radius=25: stock.get(k, 0))
    got = INS._better_carrier(w, a)
    assert not got or "motor car" not in got[1]["goal"]  # no spare engine: no car
    stock["engine"] = 2 + actions.keep_stock(w).get("engine", 0)
    assert "motor car" in INS._better_carrier(w, a)[1]["goal"]
    monkeypatch.setattr(actions, "TRANSPORT", False)
    got = INS._better_carrier(w, a)
    assert not got or "motor car" not in got[1]["goal"]  # switched off: never
