"""Chits' own building ideas (sim/ideas.py): an invention that is a building becomes a named variant of a design its
world already knows. It is built with its own name and materials, does what its base does, spreads like any other
knowledge and never reaches the shared DESIGNS table or another world."""

import dataclasses
import json
import re

import pytest

from chits import views
from chits.brain import prompt as P
from chits.brain.parse import parse_plan
from chits.sim import ideas as IDEAS
from chits.sim.items import DESIGNS
from chits.sim.world import World

HALL = {"do": "invent", "with": ["wood", "wood", "wood", "fiber"], "name": "Wind Hall",
        "purpose": "a hall to shelter the family from the wind"}


def _world(seed=3):
    w = World("A", "A", seed, "direct", 64, 2)
    a, b = list(w.agents.values())
    for o in w.agents.values():
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.inventory.clear()
        o.plan = []
    return w, a, b


def run(w, a, step, limit=2000):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def _hall(w, a):
    a.inventory.update({"wood": 3, "fiber": 1})
    msg = run(w, a, HALL)
    assert len(w.building_ideas) == 1, msg
    return next(iter(w.building_ideas.values()))


def test_a_building_idea_is_a_named_variant_built_from_its_own_materials():
    w, a, b = _world()
    designs = dict(DESIGNS)
    idea = _hall(w, a)
    assert idea["base"] == "hut" and idea["purpose"] == "shelter" and idea["by_name"] == a.name
    # the parts say what it is built from, scaled up until it takes at least what a hut does
    assert idea["materials"] == {"wood": 9, "fiber": 4}  # (and never less of any of a hut's own: 4 fiber, not 3)
    assert sum(idea["materials"].values()) >= sum(n for _, n in DESIGNS["hut"].materials)
    assert a.inventory == {"wood": 3, "fiber": 1}  # (the parts were only the model of it)
    assert f"idea:{idea['key']}" in a.knows and DESIGNS == designs and "Wind Hall" not in str(list(DESIGNS))
    ev = [e for e in w.events if e.kind == "invention"][-1]
    assert ev.data["building"] and ev.data["base"] == "hut" and "Wind Hall" in ev.text
    # built by its name: a hut, so every rule for huts holds for it, but with its own name and materials
    a.inventory.update({"wood": 9, "fiber": 4})
    run(w, a, {"do": "build", "what": "the wind hall"})
    st = next(s for s in w.structures.values() if s.idea == idea["key"])
    site = [e for e in w.events if e.kind == "site"][-1]
    assert "Wind Hall (needs 9 wood, 4 plant fiber)" in site.text
    assert st.design == "hut" and st.title == "Wind Hall" and st.complete, a.last_result
    assert a.inventory == {}  # (it took all thirteen pieces)
    built = [e for e in w.events if e.kind == "built"][-1]
    assert built.text == f"{a.name} built the first Wind Hall, {a.name}'s idea"
    assert built.data["idea"] == idea["key"] and built.data["design"] == "hut"
    assert a.home == st.id  # (it is a home, as a hut is)
    # the next one is just one more
    b.learn(f"idea:{idea['key']}", "taught", w.tick)
    b.inventory.update({"wood": 9, "fiber": 4})
    run(w, b, {"do": "build", "what": "Wind Hall", "near": f"{a.x + 8},{a.y}"})
    assert [e for e in w.events if e.kind == "built"][-1].text == f"{b.name} finished a Wind Hall", b.last_result
    # what the observer sees
    v = views.structure_view(st, w)
    assert v["name"] == "Wind Hall" and v["title"] == "Wind Hall" and v["base_name"] == "hut" and v["inventor"] == a.name
    assert views.snapshot(w)["building_ideas"][0]["name"] == "Wind Hall"
    assert any(k["name"] == "Wind Hall" and "a kind of hut" in k["detail"] for k in views.agent_detail(w, a)["knows"])


def test_it_is_saved_with_the_world_and_an_old_save_still_loads():
    w, a, _ = _world()
    idea = _hall(w, a)
    a.inventory.update({"wood": 9, "fiber": 4})
    run(w, a, {"do": "build", "what": "Wind Hall"})
    d = json.loads(json.dumps(w.to_dict()))
    w2 = World.from_dict(d)
    st = next(s for s in w2.structures.values() if s.design == "hut")
    assert w2.building_ideas[idea["key"]]["name"] == "Wind Hall" and st.title == "Wind Hall" and st.idea == idea["key"]
    assert IDEAS.by_name(w2, "Wind Hall")["base"] == "hut"
    # a save from before ideas (or one whose idea is broken) loads, and the structure is simply its base
    d.pop("building_ideas")
    d["structures"][0].pop("title")
    w3 = World.from_dict(d)
    assert not w3.building_ideas and next(iter(w3.structures.values())).design == "hut"
    d["building_ideas"] = {"x": {"name": "Odd", "base": "no_such_design", "materials": {}}, "y": "junk"}
    assert not World.from_dict(d).building_ideas
    # a world without any saves exactly as before: no new keys in it or in its structures
    w4, a4, _ = _world()
    a4.inventory.update({"wood": 8, "fiber": 4})
    run(w4, a4, {"do": "build", "what": "hut"})
    d4 = w4.to_dict()
    assert "building_ideas" not in d4 and all("idea" not in s and "title" not in s for s in d4["structures"])


def test_only_who_knows_it_can_build_it_and_it_is_taught_written_and_read():
    w, a, b = _world()
    idea = _hall(w, a)
    kk = f"idea:{idea['key']}"
    b.inventory.update({"wood": 9, "fiber": 4})
    assert run(w, b, {"do": "build", "what": "Wind Hall"}).endswith("I don't know how to build a Wind Hall yet")
    run(w, a, {"do": "teach", "what": "Wind Hall", "to": b.name})
    assert b.knows[kk]["how"] == "taught" and b.knows[kk]["status"] == "told", a.last_result
    assert a.last_result.endswith("Wind Hall")
    del b.knows[kk]
    a.inventory["clay_tablet"] = 1
    run(w, a, {"do": "write", "what": "Wind Hall"})
    tb = next(iter(w.tablets.values()))
    assert tb.knowledge == kk and "a kind of hut" in tb.text and "9 wood" in tb.text, a.last_result
    run(w, b, {"do": "read"})
    assert b.knows[kk]["how"] == "read", b.last_result
    run(w, b, {"do": "build", "what": "Wind Hall"})
    st = next(s for s in w.structures.values() if s.idea == idea["key"])
    assert st.complete and b.knows[kk]["status"] == "worked", b.last_result


def test_the_kind_of_building_comes_from_its_words_and_only_from_what_the_world_knows():
    w, a, b = _world()
    pick = lambda name, purpose="": IDEAS.archetype(w, name, purpose)
    assert pick("Wind Hall") == ("shelter", "hut")
    assert pick("Ember Hearth", "a hearth to keep warm") == ("warmth", "campfire")
    assert pick("Warm Coat", "a coat to keep warm") is None  # (no building named: an item, judged as before)
    assert pick("Hut Heater", "something to heat the hut") is None  # (a thing for a hut is not a hut)
    assert pick("Ember", "a hearth for the village") == ("warmth", "campfire")
    assert pick("Grain Barn", "a barn for the grain") is None  # nobody here knows a granary or a farm
    b.learn("design:farm", "insight", w.tick)
    assert pick("Grain Barn", "a barn for the grain") == ("food", "farm")
    b.learn("design:granary", "insight", w.tick)
    assert pick("Grain Barn", "a barn for the grain") == ("food", "granary")  # the better one, once it is known
    b.learn("design:brick_house", "insight", w.tick)
    assert pick("Wind Hall") == ("shelter", "brick_house")  # (by era: the best home the world knows)
    # a hall to keep the grain in is about the grain, a tower that watches for wolves is about defence
    assert pick("Long Hall", "a hall to store and keep the grain and the harvest")[0] == "food"
    assert pick("Wolf Tower", "a tower to watch for wolves") is None  # (no watchtower known)
    # never a shrine where there is no religion, whoever knows one
    w.rules = dataclasses.replace(w.rules, religion=False)
    b.knows["design:shrine"] = {"how": "insight", "tick": 0, "from": None, "status": "worked", "worked_tick": 0}
    assert pick("Stone Temple", "a temple to pray") is None
    # a building can't be made of berries; and the same parts for the same base are one idea
    a.inventory.update({"berries": 4})
    msg = run(w, a, {"do": "invent", "with": ["berries", "berries"], "name": "Berry Hut", "purpose": "a hut"})
    assert "can't be made of berries" in msg and not w.building_ideas
    _hall(w, a)
    b.inventory.update({"wood": 3, "fiber": 1})
    run(w, b, dict(HALL, name="Gale House"))
    assert len(w.building_ideas) == 1 and "same idea" in b.last_result
    assert any(k.startswith("idea:") for k in b.knows)
    # and its name is taken: no item or idea can have it again
    a.inventory.update({"wood": 3, "fiber": 1})
    assert "already taken" in run(w, a, dict(HALL, purpose="a toy for joy"))


@pytest.mark.parametrize("base", sorted({b for _, _, _, bases in IDEAS.KINDS for b in bases}))
def test_an_idea_is_never_cheaper_than_its_base(base):
    for bag in ({"wood": 2}, {"stone": 1, "wood": 1}, {"wood": 3, "fiber": 1}, {"brick": 2, "glass": 1, "cord": 1}):
        mats = IDEAS.materials(bag, base)
        assert sum(mats.values()) >= sum(n for _, n in DESIGNS[base].materials)
        assert all(m in mats for m in bag)  # (built from its parts)
        # (and never less of any of the base's own materials: its bricks or glass can't be swapped for wood)
        assert all(mats.get(m, 0) >= n for m, n in DESIGNS[base].materials), (bag, mats)
    # the reviewer's case: a two-storey house of wood and one brick still takes its 16 bricks and 4 glass
    assert IDEAS.materials({"wood": 27, "brick": 1}, "two_storey_house") == {"wood": 27, "brick": 16, "glass": 4}


def test_a_model_is_told_the_ideas_it_knows_by_name_and_builds_one_by_name():
    """End to end with a stand-in model that reads its prompt: the idea is listed by name only to who knows it, and the
    plan it writes from that line goes through the parser to a standing building."""
    w, a, b = _world()
    _hall(w, a)
    seen = P.scene(w, a)
    assert "Wind Hall (" + a.name + "'s idea: a kind of hut; 9 wood, 4 plant fiber)" in seen
    assert "Wind Hall" not in P.scene(w, b) and "Wind Hall" in P.compact_scene(w, a)
    # the stand-in reads the line it knows how to build, and writes the plan a model would
    line = next(l for l in seen.splitlines() if l.startswith("YOU KNOW HOW TO BUILD:"))
    name = re.search(r"; ([^;(]+) \([^()]*'s idea", line).group(1)
    plan = parse_plan(json.dumps({"goal": "build my own hall", "steps": [{"do": "build", "what": name}]}))
    a.inventory.update({"wood": 9, "fiber": 4})
    a.plan = plan["steps"]
    for _ in range(2000):
        w.step()
        if not a.plan:
            break
    st = next(s for s in w.structures.values() if s.title == "Wind Hall")
    assert st.complete and st.design == "hut", a.last_result
    assert "Wind Hall (a hut) " + st.id in P.scene(w, b)  # (others see what it is, by its name)


def test_instinct_now_and_then_builds_a_known_idea_instead_of_its_base():
    w, a, _ = _world()
    steps = [{"do": "gather", "what": "wood", "qty": 2}, {"do": "build", "what": "hut"}]
    assert IDEAS.instead(w, a, steps) is steps  # (no ideas: the plan itself, untouched)
    idea = _hall(w, a)
    a.inventory.update({"wood": 9, "fiber": 4})  # enough for a hut and for the hall
    swapped = 0
    for t in range(200):
        w.tick = t
        out = IDEAS.instead(w, a, steps)
        assert out[0] == steps[0] and out[1]["what"] in ("hut", "Wind Hall")
        swapped += out[1]["what"] == "Wind Hall"
    assert 70 <= swapped <= 130, swapped  # about half
    a.inventory["fiber"] = 3  # not enough for the hut as well: never
    assert all(IDEAS.instead(w, a, steps)[1]["what"] == "hut" for w.tick in range(50))
    a.inventory["fiber"] = 4
    w.building_ideas[idea["key"]]["materials"] = {"wood": 99}  # nor when it can't afford the idea
    assert all(IDEAS.instead(w, a, steps)[1]["what"] == "hut" for w.tick in range(50))


def test_with_the_switch_off_a_building_named_invention_is_an_item_as_before(monkeypatch):
    monkeypatch.setattr(IDEAS, "INVENTED_BUILDINGS", False)
    w, a, _ = _world()
    a.inventory.update({"wood": 3, "fiber": 1})
    run(w, a, HALL)
    assert not w.building_ideas and not any(k.startswith("idea:") for k in a.knows)


def test_a_name_with_an_article_is_found_however_it_is_written():
    w, a, b = _world()
    a.inventory.update({"wood": 3, "fiber": 1})
    run(w, a, dict(HALL, name="The Wind Hall"))
    idea = next(iter(w.building_ideas.values()))
    for said in ("The Wind Hall", "the wind hall", "Wind Hall", "a  wind hall", f"idea:{idea['key']}"):
        assert IDEAS.by_name(w, said) is idea, said
    a.inventory.update({"wood": 3, "fiber": 1})
    assert "already taken" in run(w, a, dict(HALL, name="Wind Hall", purpose="a toy for joy"))  # (one name, written two ways)
    run(w, a, {"do": "teach", "what": "the Wind Hall", "to": b.name})
    assert f"idea:{idea['key']}" in b.knows, a.last_result
    b.inventory.update({"wood": 9, "fiber": 4, "stone": 0})
    swapped = next(IDEAS.instead(w, b, [{"do": "build", "what": "hut"}]) for w.tick in range(w.tick, w.tick + 40)
                   if IDEAS.instead(w, b, [{"do": "build", "what": "hut"}])[0]["what"] != "hut")
    b.inventory = {"wood": 9, "fiber": 4}
    run(w, b, swapped[0])  # (instinct's swap writes the idea's own name, article and all)
    assert any(s.idea == idea["key"] and s.complete for s in w.structures.values()), b.last_result


def test_a_new_idea_never_takes_the_key_of_one_a_save_left_out():
    w, a, b = _world()
    _hall(w, a)
    a.inventory.update({"wood": 3, "stone": 1})
    run(w, a, {"do": "invent", "with": ["wood", "wood", "wood", "stone"], "name": "Rain Hut", "purpose": "a hut"})
    first, second = list(w.building_ideas)
    a.inventory = {"wood": 9, "fiber": 4}
    run(w, a, {"do": "build", "what": "Wind Hall"})
    d = json.loads(json.dumps(w.to_dict()))
    d["building_ideas"][first]["materials"] = {}  # (broken: left out on load, while a structure was built as it)
    w2 = World.from_dict(d)
    assert list(w2.building_ideas) == [second]
    a2 = w2.agents[a.id]
    a2.inventory = {"stone": 3, "fiber": 1}
    run(w2, a2, {"do": "invent", "with": ["stone", "stone", "stone", "fiber"], "name": "Stone Lodge", "purpose": "a lodge"})
    assert len(w2.building_ideas) == 2 and w2.building_ideas[second]["name"] == "Rain Hut", a2.last_result
    new = [k for k in w2.building_ideas if k != second][0]
    assert new not in (first, second)  # (nor the key the standing Wind Hall still carries)
    assert w2.counters["idea"] == int(new.rsplit("_", 1)[1])
    # and a world without ideas saves no counter for them
    w3, _, _ = _world()
    assert "idea" not in w3.to_dict()["counters"]


def test_an_idea_is_one_invention_event_and_counts_as_a_first_as_an_item_invention_does():
    from chits.runtime import Runtime

    w, a, _ = _world()
    seq = w.seq
    idea = _hall(w, a)
    kk = f"idea:{idea['key']}"
    new = [e for e in w.events if e.seq > seq and e.kind not in ("site",)]
    assert [e.kind for e in new if e.kind in ("invention", "discovery", "learned")] == ["invention"]
    assert kk in w.first  # (as an item invention's recipe is: one more thing this world was the first to have)
    assert Runtime._first_text(w, kk, seq).startswith(f"{a.name} thought up the Wind Hall")
    a.inventory.update({"fiber": 1, "wood": 1})
    run(w, a, {"do": "invent", "with": ["fiber", "wood"], "name": "Reed Net", "purpose": "to catch fish"})
    assert any(k.startswith("recipe:inv_") for k in w.first)


def test_village_stock_counts_what_an_idea_site_was_really_given():
    from chits.sim import projects

    w, a, _ = _world()
    _hall(w, a)
    a.inventory = {"wood": 3}
    run(w, a, {"do": "build", "what": "Wind Hall"})
    st = next(s for s in w.structures.values() if s.idea)
    assert st.needs == {"wood": 6, "fiber": 4} and not st.complete, a.last_result
    assert projects.stock(w, "wood", "hut") == 3 and projects.stock(w, "fiber", "hut") == 0


def test_an_idea_from_over_the_sea_is_not_taught_or_named_by_its_key():
    from chits.brain.instinct import Instinct

    w, a, b = _world()
    kk = "idea:idea_b_1"
    a.knows[kk] = {"how": "discovered", "tick": 0, "from": None, "status": "worked", "worked_tick": 0}
    assert not IDEAS.teachable(w, kk) and IDEAS.teachable(w, "design:hut")
    assert views.knowledge_name(kk, w) == "an idea from over the sea"
    a.traits["sociability"] = 1.0
    a.inventory["clay_tablet"] = 1
    ins = Instinct()
    for t in range(240, 240 * 4, 7):
        w.tick = t
        steps = ins.plan(w, a)["steps"]
        assert not any(s.get("what") == kk for s in steps if s.get("do") in ("teach", "write")), steps


def test_instinct_counts_an_idea_build_by_the_ideas_own_materials():
    from chits.brain.instinct import _Hands

    w, a, _ = _world()
    _hall(w, a)
    a.inventory = {"wood": 9, "fiber": 4}
    h = _Hands(w, a)
    h.run({"do": "build", "what": "Wind Hall"})
    assert h.held.get("wood", 0) == 0 and h.held.get("fiber", 0) == 0


def test_an_invented_building_is_mended_with_its_own_materials():
    w, a, _ = _world()
    a.inventory = {"stone": 2, "wood": 2}
    run(w, a, {"do": "invent", "with": ["stone", "stone", "wood", "wood"], "name": "Stone Hut", "purpose": "a hut"})
    idea = next(iter(w.building_ideas.values()))
    assert list(idea["materials"]) == ["stone", "wood", "fiber"]
    a.inventory = dict(idea["materials"])
    run(w, a, {"do": "build", "what": "Stone Hut"})
    st = next(s for s in w.structures.values() if s.idea)
    st.durability = 30.0
    a.inventory = {"stone": 1}  # (a stone hut is patched with stone; a plain hut is not)
    run(w, a, {"do": "repair", "target": st.id})
    assert st.durability > 30 and not a.inventory.get("stone"), a.last_result


def test_the_observer_and_others_see_its_name_and_with_the_switch_off_just_its_base(monkeypatch):
    w, a, b = _world()
    _hall(w, a)
    a.inventory = {"wood": 9, "fiber": 4}
    run(w, a, {"do": "build", "what": "Wind Hall"})
    st = next(s for s in w.structures.values() if s.idea)
    assert views.agent_detail(w, a)["home"]["name"] == "Wind Hall"
    monkeypatch.setattr(IDEAS, "INVENTED_BUILDINGS", False)
    assert views.structure_view(st, w)["name"] == "hut" and "title" not in views.structure_view(st, w)
    seen = P.scene(w, b)
    line = next(l for l in seen.splitlines() if f" {st.id} " in l)
    assert "Wind Hall" not in line and "you don't know how to build this" not in line, line


def test_a_planned_home_upgrade_is_not_turned_into_a_new_invented_building():
    from chits.sim import buildings as BLD

    w, a, b = _world()
    a.inventory = {"wood": 8, "fiber": 4}
    run(w, a, {"do": "build", "what": "hut"})
    assert a.home
    b.learn("design:brick_house", "insight", w.tick)
    a.learn("design:brick_house", "insight", w.tick)
    a.inventory = {"brick": 2, "wood": 2}
    run(w, a, {"do": "invent", "with": ["brick", "brick", "wood", "wood"], "name": "Clay Hall", "purpose": "a hall"})
    idea = next(iter(w.building_ideas.values()))
    assert idea["base"] == "brick_house", a.last_result
    a.inventory = {"brick": 12, "wood": 8}
    step = {"do": "build", "what": "brick house"}
    assert BLD.upgrade_instead(w, a, "brick_house", step)
    assert all(IDEAS.instead(w, a, [step])[0]["what"] == "brick house" for w.tick in range(w.tick, w.tick + 60))
