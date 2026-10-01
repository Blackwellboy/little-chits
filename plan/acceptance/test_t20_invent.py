import json

from chits.brain import prompt as P
from chits.brain.parse import parse_plan
from chits.sim import actions as A
from chits.sim.invent import judge
from chits.sim.items import ITEMS, RECIPES, all_knowledge_keys, match_recipe
from chits.sim.world import World


def fresh(wid="A", culture="direct", seed=3):
    w = World(wid, wid, seed, culture, 64, 2)
    a, b = list(w.agents.values())[:2]
    return w, a, b


def ready(*agents):
    for a in agents:
        a.hunger = a.energy = a.warmth = a.health = 100.0
        a.inventory.clear()
        a.plan = []


def run(w, a, step, limit=200):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


NET = {"do": "invent", "with": ["fiber", "fiber", "wood"], "name": "Fishnet", "purpose": "catch fish"}


def test_judge_is_lawful():
    ok, pid, eff, _ = judge({"fiber": 2, "wood": 1}, "catch fish")
    assert ok and pid == "fishing" and eff["tool"] == "spear"
    ok, pid, eff, fb = judge({"berries": 2}, "catch fish")
    assert not ok and pid == "fishing"
    assert any(p in fb for p in ("stringy", "binding", "flexible"))
    ok, pid, eff, _ = judge({"stone": 1, "wood": 1}, "make music")
    assert ok and pid == "joy" and eff["mood"] == 8
    ok, pid, eff, _ = judge({"berries": 2, "grain": 1}, "a tasty meal")
    assert ok and pid == "food" and eff["food"] == 55
    ok, pid, eff, fb = judge({"wood": 1, "berries": 1}, "food for winter")
    assert not ok and "edible" in fb
    ok, pid, eff, fb = judge({"wood": 2}, "fly to the moon")
    assert not ok and pid is None
    for word in ("catching fish", "cutting", "digging", "carrying", "keeping warm", "light", "food", "joy"):
        assert word in fb
    ok, _, _, fb = judge({"wood": 1}, "make music")
    assert not ok and "2" in fb and "4" in fb


def test_parse_keeps_invent_args():
    plan = parse_plan(json.dumps({"goal": "fish", "steps": [
        {"do": "invent", "with": ["fiber", "wood"], "name": "Reed Net", "purpose": "catch fish"},
        {"do": "devise", "items": ["stone", "wood"], "called": "Drum", "for": "music"}]}))
    s0, s1 = plan["steps"][0], plan["steps"][1]
    assert s0["do"] == "invent" and s0["name"] == "Reed Net" and s0["purpose"] == "catch fish"
    assert s0["with"] == ["fiber", "wood"]
    assert s1["do"] == "invent" and s1["name"] == "Drum" and s1["purpose"] == "music" and s1["with"] == ["stone", "wood"]
    assert A.normalize_verb("invent") == "invent"


def test_invent_creates_a_world_local_thing():
    w, a, b = fresh()
    ready(a, b)
    a.add("fiber", 2)
    a.add("wood", 1)
    run(w, a, NET)
    assert len(w.inventions) == 1, a.last_result
    key, inv = next(iter(w.inventions.items()))
    assert key == "inv_a_1"
    assert inv["name"] == "Fishnet" and inv["purpose"] == "fishing" and inv["by"] == a.id
    assert inv["inputs"] == {"fiber": 2, "wood": 1}
    assert key not in ITEMS and key not in RECIPES  # never in the shared base tables
    assert w.item(key).tool == "spear" and w.recipe(key) is not None
    assert "invented" in w.item(key).props
    assert a.inventory.get(key) == 1 and not a.inventory.get("fiber") and not a.inventory.get("wood")
    assert a.knows_recipe(key)
    assert a.best_tool("spear") == key
    evs = [e for e in w.events if e.kind == "invention"]
    assert evs and "Fishnet" in evs[0].text and evs[0].importance == 5
    # never stumbled on by experiment, never part of the base table
    assert match_recipe({"fiber": 2, "wood": 1}, None) is None
    assert "recipe:" + key not in all_knowledge_keys()


def test_failed_invention_costs_nothing_and_teaches():
    w, a, b = fresh(seed=5)
    ready(a, b)
    a.add("berries", 2)
    run(w, a, {"do": "invent", "with": ["berries", "berries"], "name": "Berry Net", "purpose": "catch fish"})
    assert not w.inventions
    assert a.inventory.get("berries") == 2
    assert any(p in a.last_result for p in ("stringy", "binding", "flexible"))


def test_craft_teach_and_reinvent():
    w, a, b = fresh(seed=7)
    ready(a, b)
    a.add("fiber", 2)
    a.add("wood", 1)
    run(w, a, NET)
    key = next(iter(w.inventions))
    assert w.invention_by_name("fishnet") == key and w.invention_by_name("FISHNET") == key
    a.add("fiber", 2)
    a.add("wood", 1)
    run(w, a, {"do": "craft", "what": "Fishnet"})
    assert a.inventory.get(key) == 2, a.last_result
    run(w, a, {"do": "teach", "to": b.name, "what": "Fishnet"}, limit=400)
    assert b.knows_recipe(key), a.last_result
    # the same idea from someone else re-uses the invention instead of duplicating it
    c = b
    c.inventory.clear()
    c.add("fiber", 2)
    c.add("wood", 1)
    run(w, c, dict(NET, name="Other Net"))
    assert len(w.inventions) == 1
    assert c.inventory.get(key) == 1


def test_twin_worlds_diverge():
    wa, a, _ = fresh("A", "direct", 11)
    wb, b, _ = fresh("B", "stigmergy", 11)
    ready(a, b)
    for c in (a, b):
        c.add("fiber", 2)
        c.add("wood", 1)
    run(wa, a, NET)
    run(wb, b, dict(NET, name="Reed Trap"))
    ka, kb = next(iter(wa.inventions)), next(iter(wb.inventions))
    assert ka != kb and ka.startswith("inv_a_") and kb.startswith("inv_b_")
    assert wb.item(ka) is None and wa.item(kb) is None  # isolation is structural
    assert wb.invention_by_name("Fishnet") is None and wa.invention_by_name("Reed Trap") is None
    b.add("fiber", 2)
    b.add("wood", 1)
    msg = run(wb, b, {"do": "craft", "what": "Fishnet"})
    assert b.inventory.get(ka) is None and msg


def test_persistence_re_registers():
    w, a, b = fresh(seed=13)
    ready(a, b)
    a.add("stone", 1)
    a.add("wood", 1)
    run(w, a, {"do": "invent", "with": ["stone", "wood"], "name": "Log Drum", "purpose": "music for dancing"})
    key = next(iter(w.inventions))
    d = json.loads(json.dumps(w.to_dict()))
    w2 = World.from_dict(d)
    assert w2.inventions[key]["name"] == "Log Drum"
    assert w2.item(key).name == "Log Drum" and w2.recipe(key) is not None
    assert World("A", "A", 13, "direct", 64, 1).item(key) is None
    d.pop("inventions", None)
    assert World.from_dict(d).inventions == {}


def test_prompt_mentions_inventing():
    w, a, b = fresh(seed=17)
    ready(a, b)
    assert '"do":"invent"' in P.verb_guide(w).replace(" ", "")
    a.add("fiber", 2)
    a.add("wood", 1)
    run(w, a, NET)
    assert "Fishnet" in P.scene(w, a)
