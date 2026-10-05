"""Daughter villages: a village of VILLAGE_CAP chits sends pioneers to found a new village a day's walk away. The
world as a whole still holds POP_CAP, which is what limits births."""

import math
import random

from chits.brain import pioneers as BP
from chits.brain import prompt as P
from chits.sim import pioneers as PI
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import BOND_TO_BREED, World


def _full_village(n=44):
    """A world whose chits all live in one village of huts, two to a hut."""
    w = World("A", "A", 5, "direct", 128, n)
    ags = list(w.agents.values())
    for o in ags:
        o.hunger = o.energy = o.warmth = o.health = 95.0
    cx, cy = ags[0].x, ags[0].y
    for i in range(0, len(ags), 2):
        hut = w.place_site("hut", *w.find_site("hut", cx, cy, 16, reach=(cx, cy)), ags[i])
        w.complete_structure(hut, ags[i])
        for o in ags[i:i + 2]:
            o.home = hut.id
    w.tick = PI.START_DAY * TICKS_PER_DAY
    [v] = PI.villages(w)
    assert (len(v.residents) >= PI.VILLAGE_CAP) == (n >= PI.VILLAGE_CAP)
    return w, v


def test_a_full_village_sends_pioneers_to_found_a_new_one():
    w, v = _full_village()
    w.tick = (PI.START_DAY - 1) * TICKS_PER_DAY
    PI.daily(w)
    assert not w.civic.get("emigration")  # too early
    w.tick = PI.START_DAY * TICKS_PER_DAY
    PI.daily(w)
    em = w.civic["emigration"]
    assert len(em["members"]) == PI.PARTY and set(em["members"]) <= set(v.residents) and em["from"] == v.id
    assert PI.FAR_MIN - 1 <= math.hypot(em["x"] - v.x, em["y"] - v.y) <= PI.FAR_MAX + 1
    assert w.same_land_xy(w.agents[em["members"][0]], em["x"], em["y"])
    assert any(e.kind == "pioneers" for e in w.events)
    before = dict(em)
    PI.daily(w)
    assert w.civic["emigration"] == before  # one party at a time
    # somewhere else next time: never within APART of anything built
    w.civic["emigration"] = None
    camp = w.place_site("outpost", *w.find_site("outpost", em["x"], em["y"], 4), w.agents[em["members"][0]])
    w.complete_structure(camp, w.agents[em["members"][0]])
    PI.daily(w)
    em2 = w.civic["emigration"]
    assert all(max(abs(s.center()[0] - em2["x"]), abs(s.center()[1] - em2["y"])) >= PI.APART for s in w.structures.values())


def test_a_village_with_room_sends_nobody_and_the_new_day_asks():
    w, v = _full_village(30)
    PI.daily(w)
    assert not w.civic.get("emigration")
    w, v = _full_village()
    w._new_day()
    assert w.civic.get("emigration")


def test_a_pioneer_lights_the_first_fire_then_builds_a_home_there_and_moves_in():
    w, v = _full_village()
    PI.daily(w)
    em = w.civic["emigration"]
    a = w.agents[em["members"][0]]
    a.inventory.update({"wood": 20, "stone": 4, "fiber": 8})
    other = next(o for o in w.agents.values() if o.id not in em["members"])
    w.tick += 60  # morning
    assert BP.plan(w, other) is None
    p = BP.plan(w, a)
    assert p["steps"][-1] == {"do": "build", "what": "campfire", "near": f"{em['x']},{em['y']}"}
    assert "You are one of the pioneers" in P.scene(w, a) and "pioneers" not in P.scene(w, other)
    fire = w.place_site("campfire", *w.find_site("campfire", em["x"], em["y"], 6), a)
    w.complete_structure(fire, a)
    assert BP.plan(w, a)["steps"][-1]["what"] == "hut"
    old = a.home
    hut = w.place_site("hut", *w.find_site("hut", em["x"], em["y"], 8), a)
    hut.builders[a.id] = 1.0
    w.complete_structure(hut, a)
    assert a.home == hut.id != old  # it had a home, and moved into the one it built out here
    assert BP.plan(w, a) is None  # settled in


def test_when_the_new_village_stands_it_is_a_daughter_of_the_old():
    w, v = _full_village()
    PI.daily(w)
    em = w.civic["emigration"]
    fire = w.place_site("campfire", *w.find_site("campfire", em["x"], em["y"], 6), w.agents[em["members"][0]])
    w.complete_structure(fire, w.agents[em["members"][0]])
    for aid in em["members"][:4:2]:
        hut = w.place_site("hut", *w.find_site("hut", em["x"], em["y"], 8), w.agents[aid])
        w.complete_structure(hut, w.agents[aid])
        w.agents[aid].home = hut.id
    w.tick += 1
    PI.daily(w)
    assert w.civic["emigration"] is None and w.civic["daughters"][0]["from"] == v.name
    assert any(e.kind == "daughter_village" for e in w.events)


class Always(random.Random):
    def random(self):
        return 0.0


def test_a_full_village_still_has_children_the_world_cap_is_the_limit():
    """(Stopping births in a full village cost 19 chits by day 30 across 12 seeds: a village's size only sends the
    pioneers out.)"""
    w, v = _full_village(42)
    a, b = (w.agents[i] for i in v.residents[:2])
    a.home = b.home
    for x, y in ((a, b), (b, a)):
        x.like(y.id, BOND_TO_BREED + 5)
        x.last_birth_tick = -10 ** 6
    b.x, b.y = a.x, a.y
    rng = Always(1)
    w.rng_for = lambda name, key=None: rng
    n = len(w.agents)
    w._births()
    assert len(w.agents) == n + 1


def test_a_village_by_the_edge_of_the_map_finds_a_site_without_looking_off_it(monkeypatch):
    """Two 30-day runs crashed: a candidate 8 tiles from the bottom of the map was looked about 8 tiles further."""
    from types import SimpleNamespace

    from chits.sim import terrain as T

    w, v = _full_village()
    a = w.agents[v.residents[0]]
    n = w.w * w.h
    for i in range(n):  # grass to the very edge, so candidates there exist
        w.tiles[i] = T.GRASS
    monkeypatch.setattr(w, "_components", lambda: [1] * n)
    w.structures.clear()
    w.occupied.clear()
    for x, y in ((w.w // 2, w.h - 43), (w.w - 43, w.h // 2)):  # a ring point lands 8 tiles from the edge
        site = PI.pick_site(w, SimpleNamespace(x=x, y=y, residents=[a.id]))
        assert site is None or (8 <= site[0] < w.w - 8 and 8 <= site[1] < w.h - 8)


def test_a_new_village_is_never_sited_near_anything_built(monkeypatch):
    w, v = _full_village()
    assert PI.pick_site(w, v) is not None
    monkeypatch.setattr(PI, "APART", 10 ** 4)  # everything is too near something built
    assert PI.pick_site(w, v) is None


def _go(w, a, step, n=4000):
    from chits.sim import actions

    for _ in range(n):
        w.tick += 1
        a.hunger = a.energy = a.warmth = 95.0
        res = actions.advance(w, a, step)
        if res != actions.RUNNING:
            return res
    return "timed out"


def test_pioneers_really_light_the_fire_and_build_their_homes_out_there():
    """(The review found both refused: a hut by a chit with a home, and a fire where one already burns near it.)"""
    from chits.brain.prompt import village_lines

    w, v = _full_village()
    near_home = w.place_site("campfire", *w.find_site("campfire", int(v.x), int(v.y), 8), w.agents[v.residents[0]])
    w.complete_structure(near_home, w.agents[v.residents[0]])  # a fire already burns in the old village
    PI.daily(w)
    em = w.civic["emigration"]
    a = w.agents[em["members"][0]]
    w.place_site("campfire", *w.find_site("campfire", a.x, a.y, 8), a)  # ...and another is half built beside the pioneer
    from chits.sim import projects

    projects.start(w, "build", "stockpile", "test", None, "need")
    assert village_lines(w, a)[0].startswith("You are one of the pioneers")  # first, so a compact prompt keeps it
    a.inventory.update({"wood": 20, "stone": 6, "fiber": 8})
    morning = lambda: (w.tick // TICKS_PER_DAY + 1) * TICKS_PER_DAY + 100  # (pioneers don't set out in the dark)
    w.tick = morning()
    for step in BP.plan(w, a)["steps"]:
        assert _go(w, a, dict(step)) == "done" or step["do"] != "build", step
    assert any(s.design == "campfire" and s.complete and s.dist(em["x"], em["y"]) <= 10 for s in w.structures.values())
    w.tick = morning()
    for step in BP.plan(w, a)["steps"]:
        assert _go(w, a, dict(step)) == "done" or step["do"] != "build", step
    home = w.structures[a.home]
    assert home.dist(em["x"], em["y"]) <= 12 and BP.plan(w, a) is None


def test_a_village_that_cant_talk_sends_no_pioneers():
    w, v = _full_village()
    w.culture, w.flags = "stigmergy", {"say": False, "teach": False, "write": False}
    PI.daily(w)
    assert not w.civic.get("emigration")
