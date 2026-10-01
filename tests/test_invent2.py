"""Invention 2.0: new purposes with real effects, and better materials make better tools."""

from chits.sim.invent import judge
from chits.sim.world import World


def test_new_purposes_are_understood_and_judged_by_materials():
    ok, pid, eff, _ = judge({"sharp_stone": 1, "wood": 1}, "a club to fight off wolves")
    assert ok and pid == "defence" and eff["tool"] == "weapon"
    ok, pid, eff, _ = judge({"copper": 1, "wood": 1}, "a hoe to till the field")
    assert ok and pid == "farming" and eff["farming"] == 3
    ok, pid, _, _ = judge({"fiber": 1, "berries": 1}, "a poultice to heal the sick")
    assert ok and pid == "healing"
    ok, pid, _, _ = judge({"wood": 2}, "a sledge to travel fast")
    assert ok and pid == "speed"
    _, _, stone, _ = judge({"sharp_stone": 1, "wood": 1}, "a weapon")
    _, _, metal, _ = judge({"copper": 1, "wood": 1}, "a weapon")
    assert metal["tool_power"] > stone["tool_power"]


def _with_invention(effect):
    from chits.sim.invent import register_invention

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    register_invention(w, "inv_a_1", "thing", {"wood": 2}, ("invented",), effect)
    w.inventions["inv_a_1"] = {"name": "thing", "inputs": {"wood": 2}, "purpose": "x", "effect": effect}
    a.inventory.clear()
    return w, a


def test_speed_farming_and_healing_inventions_work():
    from chits.sim import actions as ACT

    w, a = _with_invention({"speed": 1.2})
    slow = ACT._speed(w, a)
    a.add("inv_a_1", 1)
    assert ACT._speed(w, a) > slow

    w, a = _with_invention({"heal": 1})
    a.health, a.hunger, a.warmth = 50.0, 90.0, 90.0
    w._needs(a, 0.6)
    plain = a.health
    a.health = 50.0
    a.add("inv_a_1", 1)
    w._needs(a, 0.6)
    assert a.health > plain
