"""World laws: gathering, crafting, discovery, building, cooperation, culture channels, persistence."""

import json

import pytest

from chits.sim import actions
from chits.sim.items import RECIPES, match_recipe
from chits.sim.world import World


def run_step(w: World, a, step, max_ticks=600):
    a.plan = [step]
    for _ in range(max_ticks):
        if not a.plan:
            break
        w.tick += 1
        actions.run(w, a)
    return a.last_result


@pytest.fixture
def world():
    return World("A", "Test", 1234, "direct", 128, 6)


@pytest.fixture
def chit(world):
    a = next(iter(world.agents.values()))
    a.hunger = a.energy = a.warmth = 100
    return a


def test_twin_worlds_start_identical():
    a = World("A", "A", 77, "direct", 96, 8)
    b = World("B", "B", 77, "stigmergy", 96, 8)
    assert bytes(a.tiles) == bytes(b.tiles)
    assert [(x.name, x.x, x.y, x.traits) for x in a.agents.values()] == [(x.name, x.x, x.y, x.traits) for x in b.agents.values()]
    assert a.flags["say"] and not b.flags["say"]


def test_recipes_are_unambiguous():
    seen = set()
    for r in RECIPES.values():
        key = (r.input_bag, r.station)
        assert key not in seen, r.key
        seen.add(key)
    assert match_recipe({"stone": 2}, None).key == "sharp_stone"
    assert match_recipe({"stone": 2}, "fire").key == "sharp_stone"  # stationless works anywhere
    assert match_recipe({"clay": 1}, None) is None
    assert match_recipe({"clay": 1}, "kiln").key == "pot"


def test_gather_moves_and_collects(world, chit):
    res = run_step(world, chit, {"do": "gather", "what": "wood", "qty": 3})
    assert chit.inventory.get("wood", 0) >= 3, res
    assert "wood" in chit.familiar


def test_ore_needs_a_pick(world, chit):
    res = run_step(world, chit, {"do": "gather", "what": "ore", "qty": 1})
    assert "pick" in res
    assert not chit.has("ore")


def test_experiment_discovers_and_teaches_world(world, chit):
    chit.inventory = {"stone": 2}
    events = []
    world.listeners.append(events.append)
    run_step(world, chit, {"do": "experiment", "with": ["stone", "stone"]})
    assert chit.knows_recipe("sharp_stone")
    assert chit.has("sharp_stone")
    assert any(e.kind == "discovery" for e in events)
    assert "recipe:sharp_stone" in world.first


def test_failed_experiment_is_remembered_with_hint(world, chit):
    chit.inventory = {"fish": 1}
    run_step(world, chit, {"do": "experiment", "with": ["fish"]})
    assert not chit.knows_recipe("cooked_fish")
    assert any("heat" in m.text for m in chit.memories)
    assert chit.failed_experiments


def test_craft_requires_knowledge(world, chit):
    chit.inventory = {"fiber": 2}
    res = run_step(world, chit, {"do": "craft", "what": "cord"})
    assert "don't know" in res
    chit.knows["recipe:cord"] = {"how": "test", "tick": 0, "from": None}
    run_step(world, chit, {"do": "craft", "what": "cord"})
    assert chit.has("cord")


def test_insight_unlocks_design_from_knowledge(world, chit):
    assert not chit.knows_design("stockpile")
    chit.inventory = {"fiber": 2}
    chit.knows["recipe:cord"] = {"how": "test", "tick": 0, "from": None}
    world.check_insights(chit)
    assert chit.knows_design("stockpile")


def test_building_together(world):
    a, b = list(world.agents.values())[:2]
    for c in (a, b):
        c.hunger = c.energy = c.warmth = 100
    a.inventory = {"wood": 2, "stone": 2}
    b.inventory = {"wood": 1}
    b.x, b.y = a.x, a.y
    run_step(world, a, {"do": "build", "what": "campfire"})
    site = next(s for s in world.structures.values() if s.design == "campfire")
    assert not site.complete and site.needs == {"wood": 1}
    run_step(world, b, {"do": "help", "site": site.id})
    assert site.complete
    assert set(site.builders) == {a.id, b.id}
    assert a.affinity.get(b.id, 0) > 0


def test_culture_channels_differ():
    wa = World("A", "A", 5, "direct", 96, 4)
    wb = World("B", "B", 5, "stigmergy", 96, 4)
    for w in (wa, wb):
        t, s = list(w.agents.values())[:2]
        s.x, s.y = t.x, t.y
        t.knows["recipe:cord"] = {"how": "test", "tick": 0, "from": None}
        run_step(w, t, {"do": "teach", "to": s.name, "what": "cord"})
    ta, sa = list(wa.agents.values())[:2]
    tb, sb = list(wb.agents.values())[:2]
    assert sa.knows_recipe("cord")
    assert sa.knows["recipe:cord"]["how"] == "taught"
    assert not sb.knows_recipe("cord")
    assert "cannot teach" in tb.last_result
    res = run_step(wb, tb, {"do": "say", "to": "all", "text": "hello"})
    assert "cannot talk" in res


def test_stigmergy_learns_by_inspecting(monkeypatch):
    w = World("B", "B", 9, "stigmergy", 96, 4)
    a, b = list(w.agents.values())[:2]
    a.inventory = {"wood": 3, "stone": 2}
    run_step(w, a, {"do": "build", "what": "campfire"})
    assert any(s.complete for s in w.structures.values())
    b.knows.pop("design:campfire", None)
    monkeypatch.setattr(w.rng, "random", lambda: 0.0)  # studying always succeeds for this test
    run_step(w, b, {"do": "inspect", "target": "campfire"})
    assert b.knows_design("campfire")
    assert b.knows["design:campfire"]["how"] == "inspected"


def test_hunger_reflex_interrupts(world, chit):
    chit.hunger = 5
    chit.inventory = {"berries": 2}
    chit.plan = [{"do": "explore", "dir": "N"}]
    actions.reflexes(world, chit)
    assert chit.plan[0]["do"] == "eat" and chit.plan[0]["_reflex"]


def test_unknown_verbs_fail_safely(world, chit):
    res = run_step(world, chit, {"do": "teleport", "to": "moon"})
    assert "not something" in res
    res = run_step(world, chit, {"do": "build", "what": "spaceship"})
    assert "not a kind of structure" in res


def test_snapshot_roundtrip(world):
    for _ in range(300):
        world.step()
    d = json.loads(json.dumps(world.to_dict()))
    w2 = World.from_dict(d)
    assert w2.tick == world.tick
    assert [a.name for a in w2.agents.values()] == [a.name for a in world.agents.values()]
    assert w2.res_amt == world.res_amt
    w2.step()  # restored world keeps running


def test_crafting_a_structure_builds_it():
    """Models often "craft" a campfire (33 times in one session): build it instead of refusing."""
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    s = {}
    actions._do_craft(w, a, {"do": "craft", "what": "campfire"}, s)
    site = w.structures.get(s.get("site", ""))
    assert site is not None and site.design == "campfire" and a.id in site.builders
    assert actions._do_craft(w, a, {"do": "craft", "what": "spaceship"}, {}) == "'spaceship' is not something that can be crafted"


def test_no_second_hut_beside_your_own():
    """Models kept starting a new hut while their own stood fine (53 huts for 26 chits)."""
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.learn("design:hut", "taught", w.tick)
    pos = w.find_site("hut", a.x, a.y)
    hut = w.place_site("hut", pos[0], pos[1], a)
    w.complete_structure(hut, a)
    a.home = hut.id
    msg = actions._do_build(w, a, {"do": "build", "what": "hut"}, {})
    assert f"already have a home (hut {hut.id})" in msg
    hut.durability = 0  # a ruined home may be replaced
    assert "already have a home" not in actions._do_build(w, a, {"do": "build", "what": "hut"}, {})


def test_a_chief_needs_real_support():
    """"Pin was elected chief with 1 of 18 votes": a fifth of the adults (and at least 2) must back the winner."""
    w = World("A", "A", 3, "direct", 64, 10)
    ags = list(w.agents.values())
    for i, a in enumerate(ags):
        a.born, a.affinity = -240 * (10 + i), {}
    ags[1].affinity[ags[0].id] = 40.0  # one lone vote
    w.choose_leader("test")
    assert w.leader == ""
    ags[2].affinity[ags[0].id] = 40.0  # two of ten adults: enough
    w.choose_leader("test")
    assert w.leader == ags[0].id


def test_a_starving_chit_eats_what_it_carries_before_gathering_more():
    """Chits starved at hunger 8 with berries in hand because their plan said "gather berries"."""
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.plan = [{"do": "gather", "what": "berries", "qty": 5}]
    a.inventory["berries"] = 2
    a.hunger = 20.0  # hungry, not yet desperate: finishing the gathering is fine
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "gather"
    a.hunger = 8.0
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "eat" and a.plan[0].get("_reflex")
    a.plan = [{"do": "gather", "what": "berries", "qty": 5}]
    a.inventory.pop("berries")  # nothing in hand: gathering is the way to food
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "gather"


def test_paths_home_on_a_big_island_search_far_enough():
    """On a 512 island chits 40+ tiles from home got "couldn't reach shelter" forever: the A* budget (9000 nodes)
    was sized for small maps. The default budget now grows with the map."""
    w = World("A", "A", 1, "direct", 512, 2)
    w.block = bytearray(w.w * w.h)  # flat open ground (no terrain costs, no rivers)...
    w._base_cost = [1.0] * (w.w * w.h)
    for y in range(0, 120):  # ...with a wall between start and goal: an ~180-tile detour, like walking round a lake
        w.block[y * w.w + 160] = 1
    start, goal = (150, 40), {(170, 40)}
    assert w.find_path(*start, goal, limit=9000) is None
    path = w.find_path(*start, goal)
    assert path and path[-1] == (170, 40)
