"""Mines: the Iron Age ceiling in the live worlds was an ore ceiling ("no copper ore anywhere nearby" 5,600 times, a
forge nobody could afford for 700 days). A mine dug by rock or hills has a seam that gives ore again every day."""

import random

from chits.brain import builder as BI
from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import terrain as T
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def _by_the_rocks(n=3):
    """A world whose ore deposits are all dug out, and a chit standing near rock or hills."""
    w = World("A", "A", 11, "direct", 96, n)
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 95.0
    k = T.RES_INDEX["ore"]
    for i in range(w.w * w.h):
        if w.res_kind[i] == k:
            w.res_amt[i] = 0
    a = next(iter(w.agents.values()))
    spot = next((x, y) for y in range(3, w.h - 3) for x in range(3, w.w - 3)
                if w.passable(x, y) and w.tile_free(x, y) and w.near_rock(x, y) and w.find_site("mine", x, y, 6, reach=(x, y)))
    a.x, a.y = spot
    a.learn("recipe:copper", "discovered", w.tick)
    a.learn("recipe:stone_pick", "discovered", w.tick)
    a.learn("design:mine", "insight", w.tick)
    w.tick = TICKS_PER_DAY + 100  # daytime
    return w, a


def _mine(w, a):
    m = w.place_site("mine", *w.find_site("mine", a.x, a.y, 6, reach=(a.x, a.y)), a)
    w.complete_structure(m, a)
    return m


def _run(w, a, step, n=600):
    for _ in range(n):
        w.tick += 1
        res = actions.advance(w, a, step)
        if res != actions.RUNNING:
            return res
    return "timed out"


def test_a_mine_is_dug_only_by_rock_or_hills():
    w, a = _by_the_rocks()
    m = _mine(w, a)
    assert w.near_rock(m.x, m.y, m.w, m.h)
    for i in range(w.w * w.h):  # an island with no rock or hills has nowhere to dig one
        if w.tiles[i] in (T.ROCK, T.HILLS):
            w.tiles[i] = T.GRASS
    assert w.find_site("mine", a.x, a.y, 6, reach=(a.x, a.y)) is None


def test_the_seam_fills_again_every_day_up_to_its_depth():
    w, a = _by_the_rocks()
    m = _mine(w, a)
    m.storage.clear()
    w.tick = 5 * TICKS_PER_DAY
    BLD.step(w)
    assert m.storage["ore"] == BLD.MINE_PER_DAY
    for d in range(6, 12):
        w.tick = d * TICKS_PER_DAY
        BLD.step(w)
    assert m.storage["ore"] == BLD.MINE_SEAM
    m.storage["ore"] = BLD.MINE_SEAM - 2
    BLD._mines(w)
    assert m.storage["ore"] == BLD.MINE_SEAM  # never deeper than the seam


def test_with_the_deposits_dug_out_a_chit_digs_ore_from_the_mine_with_a_pick():
    w, a = _by_the_rocks()
    step = {"do": "gather", "what": "ore", "qty": 3}
    msg = actions.advance(w, a, dict(step))
    assert "I need a pick" in msg and "you know how to make a stone pick" in msg
    a.inventory["stone_pick"] = 1
    assert "a mine dug by the rocks would give some" in actions.advance(w, a, dict(step))  # no mine yet
    m = _mine(w, a)
    m.storage["ore"] = 10
    assert _run(w, a, step) == actions.DONE
    assert a.inventory.get("ore") == 3 and m.storage["ore"] == 7 and a.stats.get("mined") == 3


def test_instinct_digs_a_mine_only_when_the_ore_near_home_is_gone():
    w, a = _by_the_rocks(30)  # (a village this size could keep two mines: one near home is enough)
    a.inventory.update({"wood": 8, "stone": 6, "cord": 2})
    plans = [p for _, p in BI.building_options(w, a, random.Random(1))]
    assert any(s.get("what") == "mine" for p in plans for s in p["steps"] if s.get("do") == "build")
    _mine(w, a)
    plans = [p for _, p in BI.building_options(w, a, random.Random(1))]
    assert not any(s.get("what") == "mine" for p in plans for s in p["steps"] if s.get("do") == "build")


def test_with_the_seam_dug_out_for_today_the_mine_is_dug_deeper_three_times_as_slowly():
    # issue #6: mining limited by work, not a daily cap ("the mine's seam is dug out for today" was World B's
    # commonest failure: 214 in ten late-game days)
    def ticks_for_ore(seam):
        w, a = _by_the_rocks()
        a.inventory["stone_pick"] = 1
        m = _mine(w, a)
        m.storage["ore"] = seam
        a.x, a.y = next(iter(w.stand_tiles_for_structure(m)))
        s, step = {}, {"do": "gather", "what": "ore", "qty": 2}
        for t in range(1, 2000):
            w.tick += 1
            a.hunger = a.energy = a.warmth = 95.0
            res = actions._do_gather(w, a, step, s)
            if res != actions.RUNNING:
                assert res == actions.DONE and a.inventory.get("ore", 0) == 2, res
                return t, m.storage.get("ore", 0)
        raise AssertionError("never dug any")

    fast, left = ticks_for_ore(8)
    slow, still = ticks_for_ore(0)
    assert left == 6 and still == 0  # (deep digging takes nothing from the seam)
    assert 2.5 * fast <= slow <= 3.5 * fast, (fast, slow)
