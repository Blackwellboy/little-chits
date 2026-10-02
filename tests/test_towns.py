"""Towns and cities. Villages were clusters of buildings with no heart: a village of 50 looked like a village of 10
with more huts, its public buildings went up wherever their builder stood, and roads were laid one tile at a time
beside whoever had stone. Now a village of 20 with a town hall is a town, its public buildings go up around the hall,
it lays a square, and it paves the paths its people wear; a town of 40 with five kinds of public building around its
hall and paved streets is a city."""

import random

from chits.brain import builder as BI
from chits.brain import prompt as P
from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import pioneers as PI
from chits.sim import settlements as SE
from chits.sim.agent import TICKS_PER_DAY
from test_pioneers import _full_village


def put(w, design, a, near, radius=10):
    st = w.place_site(design, *w.find_site(design, near[0], near[1], radius), a)
    w.complete_structure(st, a)
    return st


def town(n=24):
    w, v = _full_village(n)
    a = w.agents[v.residents[0]]
    hall = put(w, "town_hall", a, (int(v.x), int(v.y)))
    w.tick += 1
    return w, a, hall


def village_of(w, a):
    return next(v for v in PI.villages(w) if a.home in v.structures)


def test_a_big_village_is_a_village_until_it_builds_a_hall_then_a_town():
    w, v = _full_village(24)
    assert v.rank == "village" and not v.hall
    a = w.agents[v.residents[0]]
    hall = put(w, "town_hall", a, (int(v.x), int(v.y)))
    w.tick += 1
    v = village_of(w, a)
    assert v.rank == "town" and v.hall == hall.id
    assert (v.x, v.y) == hall.center()  # its heart is the hall
    assert v.to_dict()["rank"] == "town"


def test_a_small_place_with_a_hall_is_still_no_town():
    w, v = _full_village(10)
    a = w.agents[v.residents[0]]
    put(w, "town_hall", a, (int(v.x), int(v.y)))
    w.tick += 1
    assert village_of(w, a).rank == "village"


def test_a_town_becomes_a_city_with_people_public_buildings_and_streets():
    w, v = _full_village(44)
    a = w.agents[v.residents[0]]
    hall = put(w, "town_hall", a, (int(v.x), int(v.y)))
    for d in ("market", "library", "school", "well", "granary"):
        put(w, d, a, (hall.x, hall.y), 20)
    w.tick += 1
    assert village_of(w, a).rank == "town"  # no streets yet
    paved = 0
    for y in range(hall.y - 15, hall.y + 16):
        for x in range(hall.x - 15, hall.x + 16):
            i = y * w.w + x
            if paved < SE.CITY_STREETS and i not in w.occupied and w.passable(x, y):
                w.roads.add(i)
                paved += 1
    w.tick += 1
    assert village_of(w, a).rank == "city"


def test_becoming_a_town_is_announced_once():
    w, a, hall = town()
    w.update_settlements()
    w.update_settlements()
    said = [e for e in w.events if e.kind == "town_rank"]
    assert len(said) == 1 and "has become a town" in said[0].text


def test_a_towns_public_buildings_go_up_around_its_hall():
    w, a, hall = town()
    b = next(o for o in w.agents.values() if o is not a and not o.is_child(w.tick))
    b.learn("design:market", "taught", w.tick)
    b.inventory.update({"wood": 8, "stone": 4, "cord": 2})
    b.x, b.y = hall.x + 22, hall.y  # the builder stands well away from the hall
    s = {}
    actions._do_build(w, b, {"do": "build", "what": "market"}, s)
    site = w.structures[s["site"]]
    assert BLD.gap(site, hall) <= 8, (site.x, site.y, hall.x, hall.y)


def test_the_square_gathers_neighbours_in_the_evening():
    w, a, hall = town()
    sq = put(w, "plaza", a, (hall.x, hall.y + 4))
    w.tick += 1
    near = [o for o in w.agents.values() if sq.dist(o.x, o.y) <= BLD.PLAZA_RADIUS and not o.is_child(w.tick)]
    assert len(near) >= 3
    for o in near:
        o.mood = 50.0
    b, c = near[0], near[1]
    before = b.affinity.get(c.id, 0.0) if hasattr(b, "affinity") else None
    BLD._plaza(w)
    assert all(o.mood > 50.0 for o in near)
    assert any(e.kind == "plaza" for e in w.events)
    if before is not None:
        assert b.affinity.get(c.id, 0.0) > before


def test_a_town_paves_its_most_walked_path():
    w, a, hall = town()
    a.learn("design:road", "taught", w.tick)
    a.inventory.update({"stone": 2})
    worn = None
    for d in range(6, 12):
        x, y = hall.x + d, hall.y + hall.h + 3
        i = y * w.w + x
        if i not in w.occupied and w.passable(x, y):
            w.traffic[i] = 40.0 + d  # a worn trail, the farther tiles walked more
            worn = (x, y)
    assert worn is not None
    assert BI._street_to_pave(w, hall) == worn
    w.tick = 4 * TICKS_PER_DAY + 120  # (midday)
    plans = [p for _, p in BI.town_options(w, a)]
    pave = next(p for p in plans if p["goal"] == "pave a street")
    assert pave["steps"][-1] == {"do": "build", "what": "road", "at": f"{worn[0]},{worn[1]}"}


def test_a_village_of_twenty_plans_its_town_hall():
    w, v = _full_village(24)
    a = w.agents[v.residents[0]]
    for k in ("recipe:clay_tablet", "recipe:brick", "recipe:glass"):
        a.learn(k, "taught", w.tick)
    w.check_insights(a)
    assert a.knows_design("town_hall")
    a.inventory.update({"brick": 16, "wood": 10, "stone": 10, "glass": 2})
    plans = [p for _, p in BI.town_options(w, a)]
    assert any(p["goal"] == "build a town hall" for p in plans)


def test_chits_say_they_live_in_a_town():
    w, a, hall = town()
    assert f"town of {village_of(w, a).name}" in P.scene(w, a)


def test_a_building_bigger_than_a_load_is_started_and_supplied_from_the_stores():
    # a town hall is 38 things and a chit carries 12: fetching it all first failed before the site was started
    w, v = _full_village(24)
    a = w.agents[v.residents[0]]
    for k in ("recipe:clay_tablet", "recipe:brick", "recipe:glass"):
        a.learn(k, "taught", w.tick)
    w.check_insights(a)
    a.inventory.clear()
    plan = BI._build(w, a, "town_hall", 1, "x", near=(int(v.x), int(v.y)))
    assert plan is None  # no brick or glass anywhere: nothing to build it from
    pile = put(w, "stockpile", a, (a.x, a.y), 6)
    pile.storage.update({"brick": 16, "glass": 2})
    plan = BI._build(w, a, "town_hall", 1, "x", near=(int(v.x), int(v.y)))
    assert plan["steps"] == [{"do": "build", "what": "town_hall", "_cap": 1, "near": f"{int(v.x)},{int(v.y)}"}]
    small = BI._build(w, a, "well", 3, "x") if a.knows_design("well") else None
    assert small is None or small["steps"][-1]["what"] == "well"  # (small buildings plan as before)
