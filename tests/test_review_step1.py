"""The 2026-10-04 review, step 1: the prompt tells the truth about the simulator, an invention's purpose is read by
whole words, every store counts as a store, blurbs say what the code does, and a chit remembers more of what failed."""

from chits import views
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import actions as A, food
from chits.sim.invent import judge, mentions
from chits.sim.items import DESIGNS, STATIONS
from chits.sim.world import World


def _world(seed=3, n=2, culture="direct"):
    w = World("A", "A", seed, culture, 64, n)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.inventory.clear()
        o.plan = []
    return w, a


def _store(w, a, design, stored):
    pos = w.find_site(design, a.x + 2, a.y, 8)
    s = w.place_site(design, pos[0], pos[1], a)
    w.complete_structure(s, a)
    s.storage.update(stored)
    return s


def test_a_purpose_is_read_by_whole_words():
    assert mentions("a pointed stick", "stick") and not mentions("a pointed stick", "sick")
    assert mentions("warm shoes", "shoe") and not mentions("warm shoes", "hoe")
    assert not mentions("something to heat the hut", "eat")
    # matched as a substring, the first bucket (defence) and healing ("sick") used to win on any word that held them
    _, pid, _, _ = judge({"wood": 1, "sharp_stone": 1}, "a pointed stick to catch fish")
    assert pid == "fishing"
    ok, pid, _, _ = judge({"wood": 2}, "a shoe to run fast")
    assert ok and pid == "speed"
    _, pid, _, _ = judge({"wood": 1, "stone": 1}, "something to heat the hut")
    assert pid != "food"
    # "joy" is one of the purposes the guide names, so the word itself has to count
    ok, pid, eff, _ = judge({"stone": 1, "wood": 1}, "joy")
    assert ok and pid == "joy" and eff["mood"] == 8
    ok, pid, _, _ = judge({"stone": 1, "wood": 1}, "something pretty to dance to")
    assert ok and pid == "joy"


def test_the_guide_names_every_station_both_ores_and_the_real_bag_sizes():
    w, a = _world()
    guide = P.verb_guide(w)
    for st in STATIONS:
        assert st in guide, st
    assert "iron ore" in guide
    assert "1-5 carried items" in guide and "1-3 carried" not in guide  # iron takes 4, an engine 5
    assert "up to 3 kinds" in guide
    compact = P.compact_system_prompt(w, a)
    assert "warm_up" not in compact and "wander" not in compact  # the simulator's reflexes, not verbs to ask for
    for st in ("forge", "factory", "loom"):
        assert st in compact
    for field in ("site", "near", "dir", "give", "intent"):
        assert field in compact


def test_a_warehouse_is_a_store_to_the_food_gauge_the_scene_and_the_viewer():
    w, a = _world(n=4)
    wh = _store(w, a, "warehouse", {"bread": 20, "seeds": 5})
    days = food.food_days(w, a)
    assert days and days == food.food_days(w)
    line = P.food_around(w, a)
    assert line.startswith("20 food stored; 5 seeds stored"), line
    assert "holds 20 bread" in P.scene(w, a)
    assert views.structure_view(wh, w)["storage"] == {"bread": 20, "seeds": 5}


def test_blurbs_say_what_the_code_does():
    from chits.sim import buildings as B

    assert str(B.HOME_CAP["brick_house"]) == "5" and "up to five" in DESIGNS["brick_house"].blurb
    for key in ("palisade", "street_lamp"):  # wolves still walk in; only the biting is stopped (animals.py)
        assert "bites" in DESIGNS[key].blurb and "comes within" not in DESIGNS[key].blurb


def test_a_chit_keeps_more_than_thirty_failed_experiments():
    w, a = _world(seed=5)
    a.failed_experiments = [f"{i} wood at the fire" for i in range(A.FAILED_MEMORY - 1)]
    a.add("stone", 1)
    a.add("berries", 1)
    a.plan = [{"do": "experiment", "with": ["stone", "berries"]}]
    for _ in range(200):
        w.step()
        if not a.plan:
            break
    assert "berries + stone" in a.failed_experiments[-1]
    assert len(a.failed_experiments) == A.FAILED_MEMORY and A.FAILED_MEMORY > 30
    assert "0 wood at the fire" in a.failed_experiments  # the oldest is still there


def test_tinkering_plans_resolve_names_through_the_world():
    """A hint memory names things as the chit saw them: an invention by its name, a culture's own word for a thing.
    Planned through the base table those came back as nothing and the follow-up was silently dropped."""
    from chits.sim.invent import register_invention

    w, a = _world(seed=7)
    ins = Instinct()
    ins._world = w
    register_invention(w, "inv_a_1", "Fishnet", {"fiber": 2, "wood": 1}, ("invented",), {"tool": "spear", "tool_power": 1.2})
    w.inventions["inv_a_1"] = {"name": "Fishnet", "inputs": {"fiber": 2, "wood": 1}, "purpose": "fishing", "effect": {}}
    a.add("inv_a_1", 1)
    a.add("stone", 1)
    plan = ins._exp_plan(a, ["Fishnet", "stone"], None, "try")
    assert plan and plan["steps"][-1]["with"] == ["inv_a_1", "stone"], plan
    assert Instinct()._exp_plan(a, ["stone", "stone"], None, "try")  # without a world the base table still serves


def test_blind_tinkering_can_draw_a_bag_of_five():
    import inspect

    from chits.brain import instinct as I

    # iron takes 4 and an engine 5: a draw that never reached 5 left them to the "wrong amounts" hunch alone
    src = inspect.getsource(I.Instinct._experiment)
    assert "(1, 2, 2, 2, 3, 3, 4, 5)" in src
