"""Prospectors: a long trip out to find what is gone from around home. Where chits talk, what the prospector finds is
told at home and every hearer knows the place; where they can't, only the prospector does."""

import random

from chits.brain import prospect as PR
from chits.sim import actions
from chits.sim import terrain as T
from chits.sim.actions import remembered_place
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def _far_ore(culture="direct"):
    """One deposit of ore, with the prospector's home 36+ tiles from it and a neighbour at home."""
    w = World("A", "A", 11, culture, 96, 3)
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 95.0
    k = T.RES_INDEX["ore"]
    comp = w._components()
    tiles = [i for i in range(w.w * w.h) if w.res_kind[i] == k and w.res_amt[i] > 0 and w.reachable_edge(i)]
    for ore in tiles:
        ox, oy = ore % w.w, ore // w.w
        lands = {comp[(oy + dy) * w.w + ox + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if 0 <= ox + dx < w.w and 0 <= oy + dy < w.h} - {0}
        spots = [(x, y) for y in range(3, w.h - 3) for x in range(3, w.w - 3)
                 if comp[y * w.w + x] in lands and w.passable(x, y) and 36 <= max(abs(x - ox), abs(y - oy)) <= 44]
        if spots:
            break
    else:
        raise AssertionError("no ore with far land on this map")
    for i in tiles:
        if i != ore:
            w.res_amt[i] = 0
    a, b = list(w.agents.values())[:2]
    a.x, a.y = spots[0]
    home = w.place_site("hut", *w.find_site("hut", a.x, a.y, 6, reach=(a.x, a.y)), a)
    w.complete_structure(home, a)
    a.home = home.id
    b.x, b.y = a.x, a.y
    a.inventory["stone_pick"] = 1
    w.tick = TICKS_PER_DAY + 60  # morning
    return w, a, b, (ox, oy)


def _run(w, a, step, n=4000):
    for _ in range(n):
        w.tick += 1
        res = actions.advance(w, a, step)
        if res != actions.RUNNING:
            return res
    return "timed out"


def test_a_prospector_finds_far_ore_comes_home_and_tells_the_village():
    w, a, b, ore = _far_ore("direct")
    assert remembered_place(w, a, "ore") is None and remembered_place(w, b, "ore") is None
    assert _run(w, a, {"do": "prospect", "what": "ore", "to": f"{ore[0]},{ore[1]}"}) == actions.DONE
    assert remembered_place(w, a, "ore") == ore
    assert max(abs(a.x - b.x), abs(a.y - b.y)) <= 6  # home again
    assert remembered_place(w, b, "ore") == ore  # it heard where
    assert any(e.kind == "speech" and "copper ore at" in e.text for e in w.events)
    assert a.stats.get("prospected") == 1 and w.civic["prospector_until"] > w.tick - 4000


def test_where_chits_cant_talk_only_the_prospector_knows():
    w, a, b, ore = _far_ore("stigmergy")
    assert _run(w, a, {"do": "prospect", "what": "ore", "to": f"{ore[0]},{ore[1]}"}) == actions.DONE
    assert remembered_place(w, a, "ore") == ore
    assert remembered_place(w, b, "ore") is None and not any(e.kind == "speech" for e in w.events)


def test_instinct_sends_one_prospector_when_the_ore_around_home_is_gone():
    w, a, b, ore = _far_ore("direct")
    [(_, plan)] = PR.options(w, a, random.Random(1))
    assert plan["steps"] == [{"do": "prospect", "what": "ore"}]
    assert PR.prospect_plan(w, b) is None or PR.prospect_plan(w, b)["steps"][0]["what"] != "ore"  # no pick: not ore
    w.civic["prospector_until"] = w.tick + 10  # someone is already out there
    assert PR.options(w, a, random.Random(1)) == []
    w.civic["prospector_until"] = 0
    w.tick = TICKS_PER_DAY * 2 - 10  # night
    assert PR.options(w, a, random.Random(1)) == []
    w.tick = TICKS_PER_DAY + 60
    a.remember(w.tick, f"While exploring I found copper ore at ({ore[0]},{ore[1]})", 3, "place")
    assert PR.prospect_plan(w, a) is None or PR.prospect_plan(w, a)["steps"][0]["what"] != "ore"  # it knows a place
