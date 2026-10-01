"""Outpost camps (upgrade #8): founded beside far ore, sand or clay where a chit remembers seeing it; a store to
gather into, a tent to sleep in on long trips, and loads hauled home."""

import random

from chits.brain import outposts as OP
from chits.sim import actions
from chits.sim import terrain as T
from chits.sim.world import World


def _far_ore_world():
    """A 96 map with one deposit of ore, and the chit's home on the same land at least FAR+2 tiles from it."""
    w = World("A", "A", 11, "direct", 96, 3)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 95.0
    k = T.RES_INDEX["ore"]
    comp = w._components()
    tiles = [i for i in range(w.w * w.h) if w.res_kind[i] == k and w.res_amt[i] > 0 and w.reachable_edge(i)]
    for ore in tiles:
        ox, oy = ore % w.w, ore // w.w
        lands = {comp[(oy + dy) * w.w + ox + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if 0 <= ox + dx < w.w and 0 <= oy + dy < w.h} - {0}
        spots = [(x, y) for y in range(2, w.h - 2) for x in range(2, w.w - 2)
                 if comp[y * w.w + x] in lands and w.passable(x, y) and max(abs(x - ox), abs(y - oy)) >= OP.FAR + 2]
        if spots:
            break
    else:
        raise AssertionError("no ore with far land on this map")
    for i in tiles:
        if i != ore:
            w.res_amt[i] = 0
    a.x, a.y = min(spots, key=lambda p: (max(abs(p[0] - ox), abs(p[1] - oy)), p))
    home = w.place_site("hut", *w.find_site("hut", a.x, a.y, 6), a)
    w.complete_structure(home, a)
    a.home = home.id
    a.inventory["stone_pick"] = 1
    a.learn("recipe:cord", "discovered", w.tick)  # (the idea of an outpost comes to those who know cord)
    a.learn("design:outpost", "insight", w.tick)
    return w, a, (ox, oy)


def _put(w, a, design, near):
    st = w.place_site(design, *w.find_site(design, near[0], near[1], 8), a)
    w.complete_structure(st, a)
    return st


def test_an_outpost_is_a_store_that_doesnt_count_against_the_stockpile_cap():
    w, a, spot = _far_ore_world()
    camp = _put(w, a, "outpost", (a.x + 3, a.y))
    assert camp in w.structures_near(a.x, a.y, 10, "stockpile")
    a.inventory["stone"] = 4
    step = {"do": "store", "what": "stone", "target": camp.id}
    for _ in range(200):
        w.tick += 1
        if actions.advance(w, a, step) != actions.RUNNING:
            break
    assert camp.storage.get("stone") == 4 and not a.inventory.get("stone")
    assert sum(1 for s in w.structures.values() if s.design == "stockpile") == 0  # (the cap counts stockpiles only)


def test_a_camp_is_founded_where_the_chit_remembers_the_far_ore():
    w, a, spot = _far_ore_world()
    assert OP.found_plan(w, a) is None  # it has never seen that ore
    assert a.reflex_rest == {} or "nocamp" not in str(a.reflex_rest)  # (the retry memo is not the chit's state)
    w._nocamp = {}
    a.remember(w.tick, f"While exploring I found copper ore at ({spot[0]},{spot[1]}), clay at (1,1)", 3, "place")
    plan = OP.found_plan(w, a)
    assert plan and plan["steps"][-1] == {"do": "build", "what": "outpost", "near": f"{spot[0]},{spot[1]}"}
    # building it puts the camp by the ore
    a.inventory.update({"wood": 8, "stone": 4, "cord": 2})
    step = dict(plan["steps"][-1])
    for _ in range(3000):
        w.tick += 1
        if actions.advance(w, a, step) != actions.RUNNING:
            break
    camps = [s for s in w.structures.values() if s.design == "outpost"]
    assert camps and camps[0].dist(*spot) <= 10


def test_a_camp_is_worked_hauled_home_and_slept_in():
    w, a, spot = _far_ore_world()
    camp = _put(w, a, "outpost", spot)
    plan = OP.work_plan(w, a)
    assert [s["do"] for s in plan["steps"]] == ["go", "gather", "store"] and plan["steps"][-1]["target"] == camp.id
    home = w.structures[a.home]
    pile = _put(w, a, "stockpile", (home.x + 3, home.y))
    camp.storage["ore"] = 10
    haul = OP.haul_plan(w, a)
    assert haul["steps"][0] == {"do": "take", "what": "ore", "qty": 8, "target": camp.id}
    assert haul["steps"][1]["target"] == pile.id
    # far from home and worn out: it sleeps in the camp's tent, which shelters it like a home
    a.x, a.y = next(iter(w.stand_tiles_for_structure(camp)))
    a.energy = 30.0
    s = {}
    for _ in range(40):
        w.tick += 1
        actions.advance(w, a, {"do": "sleep", "_s": s})
    assert s.get("home") == camp.id
    assert a.activity == "sleeping" and camp.dist(a.x, a.y) <= 2  # it didn't walk the long way home
    a.x, a.y = camp.x, camp.y
    assert w.in_home(a) is camp


def test_a_failed_gather_names_the_place_the_chit_remembers():
    w, a, spot = _far_ore_world()
    a.remember(w.tick, f"While exploring I found copper ore at ({spot[0]},{spot[1]})", 3, "place")
    a.plan_source = "instinct"
    res = actions.advance(w, a, {"do": "gather", "what": "ore"})
    for _ in range(5):
        if res != actions.RUNNING:
            break
        res = actions.advance(w, a, {"do": "gather", "what": "ore"})
    assert f"you remember some at ({spot[0]},{spot[1]})" in res and "outpost camp" in res
