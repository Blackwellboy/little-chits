"""Sand pits. Sand lies only by coasts and lakes, and "no sand anywhere nearby" was the commonest failure in late-game
runs (41-49 in ten days) while bricks and glass both need it. A pit dug by the water gives sand back every day, the way
a mine gives ore, and a chit that finds no sand within reach digs one."""

import random

from chits.brain import builder as BI
from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import terrain as T
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def shore_village():
    """A chit standing a few tiles from a shore."""
    w = World("A", "A", 5, "direct", 128, 2)
    a = next(iter(w.agents.values()))
    a.hunger = a.energy = a.warmth = a.health = 95.0
    a.inventory.clear()
    cx, cy = w.w // 2, w.h // 2
    shore = min(((x, y) for y in range(w.h) for x in range(w.w) if w.coastal(x, y) and w.tile_free(x, y)),
                key=lambda p: (abs(p[0] - cx) + abs(p[1] - cy), p))
    a.x, a.y = shore
    return w, a


def no_sand(w):
    while True:
        pos = w.nearest_resource(w.w // 2, w.h // 2, "sand", 200)
        if pos is None:
            return
        w.res_amt[pos[1] * w.w + pos[0]] = 0


def test_a_sand_pit_stands_by_the_water_and_fills_every_day():
    w, a = shore_village()
    sx, sy = a.x, a.y  # inland a way: the pit must still go by the water, not where the chit stands
    a.x, a.y = min(((x, y) for y in range(sy - 10, sy + 11) for x in range(sx - 10, sx + 11)
                    if w.inb(x, y) and w.tile_free(x, y) and not any(
                        w.inb(x + dx, y + dy) and w.coastal(x + dx, y + dy) for dx in range(-3, 4) for dy in range(-3, 4))),
                   key=lambda p: (abs(p[0] - sx) + abs(p[1] - sy), p))
    pos = w.find_site("sand_pit", a.x, a.y, 8)
    assert pos is not None and any(w.coastal(x, y) for x in range(pos[0], pos[0] + 2) for y in range(pos[1], pos[1] + 2))
    pit = w.place_site("sand_pit", *pos, a)
    w.complete_structure(pit, a)
    BLD._mines(w)
    assert pit.storage["sand"] == BLD.PIT_PER_DAY
    for _ in range(10):
        BLD._mines(w)
    assert pit.storage["sand"] == BLD.PIT_HOLD


def test_with_no_sand_left_a_chit_digs_it_from_the_pit():
    w, a = shore_village()
    no_sand(w)
    pit = w.place_site("sand_pit", *w.find_site("sand_pit", a.x, a.y, 8), a)
    w.complete_structure(pit, a)
    pit.storage["sand"] = 6
    a.x, a.y = next(iter(w.stand_tiles_for_structure(pit)))
    s = {}
    res = actions.RUNNING
    for _ in range(400):
        w.tick += 1
        res = actions._do_gather(w, a, {"do": "gather", "what": "sand", "qty": 3}, s)
        if res != actions.RUNNING:
            break
    assert res == actions.DONE and a.inventory.get("sand") == 3 and pit.storage["sand"] == 3


def test_a_chit_that_found_no_sand_plans_a_pit():
    w, a = shore_village()
    a.learn("design:sand_pit", "taught", w.tick)
    a.inventory.update({"wood": 4, "stone": 2})
    w.tick = 4 * TICKS_PER_DAY + 120  # (midday)
    assert not any(p["goal"] == "build a sand pit" for _, p in BI.building_options(w, a, random.Random(1)))
    a.reflex_rest["scarce:sand"] = w.tick + TICKS_PER_DAY  # (as a failed "gather sand" leaves it)
    assert any(p["goal"] == "build a sand pit" for _, p in BI.building_options(w, a, random.Random(1)))
