"""Cities: what only a city can raise, and a harbour for a town by the water. A university (grown-ups learn from each
other what any of them has made work, against the knowledge that died with its last keepers), a theatre (an evening
show), and a harbour (twice the fish). The build itself refuses a university or theatre outside a city."""

import random

from chits.brain import builder as BI
from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import pioneers as PI
from chits.sim import settlements as SE
from chits.sim.agent import TICKS_PER_DAY
from test_pioneers import _full_village
from test_towns import put


def city():
    w, v = _full_village(44)
    a = w.agents[v.residents[0]]
    hall = put(w, "town_hall", a, (int(v.x), int(v.y)))
    for d in ("market", "library", "school", "well", "granary"):
        put(w, d, a, (hall.x, hall.y), 20)
    paved = 0
    for y in range(hall.y - 15, hall.y + 16):
        for x in range(hall.x - 15, hall.x + 16):
            i = y * w.w + x
            if paved < SE.CITY_STREETS and i not in w.occupied and w.passable(x, y):
                w.roads.add(i)
                paved += 1
    w.tick += 1
    assert next(v for v in PI.villages(w) if a.home in v.structures).rank == "city"
    return w, a, hall


def test_only_a_city_can_build_a_university():
    w, v = _full_village(24)
    a = w.agents[v.residents[0]]
    hall = put(w, "town_hall", a, (int(v.x), int(v.y)))
    w.tick += 1
    a.learn("design:university", "taught", w.tick)
    a.x, a.y = hall.x, hall.y + hall.h + 1
    res = actions._do_build(w, a, {"do": "build", "what": "university"}, {})
    assert isinstance(res, str) and "only a city" in res
    w, a, hall = city()
    a.learn("design:university", "taught", w.tick)
    a.x, a.y = hall.x, hall.y + hall.h + 1
    s = {}
    actions._do_build(w, a, {"do": "build", "what": "university"}, s)
    assert s.get("site") in w.structures


def test_grown_ups_at_a_university_learn_from_each_other():
    w, a, hall = city()
    uni = put(w, "university", a, (hall.x, hall.y), 20)
    w.tick += 1
    near = [o for o in w.agents.values() if uni.dist(o.x, o.y) <= BLD.UNI_RADIUS and not o.is_child(w.tick)]
    teacher, pupil = near[0], near[1]
    for o in near:
        o.knows.pop("recipe:glass", None)
        o.activity = ""
    teacher.learn("recipe:glass", "discovered", w.tick)
    teacher.knows["recipe:glass"]["status"] = "worked"
    for _ in range(200):
        w.tick += 1
        BLD._university(w)
        if sum(1 for o in near if "recipe:glass" in o.knows) > 1:
            break
    assert sum(1 for o in near if "recipe:glass" in o.knows) > 1


def test_the_theatre_puts_on_an_evening_show():
    w, a, hall = city()
    th = put(w, "theatre", a, (hall.x, hall.y), 20)
    w.tick += 1
    near = [o for o in w.agents.values() if th.dist(o.x, o.y) <= BLD.THEATRE_RADIUS]
    for o in near:
        o.mood = 50.0
    BLD._theatre(w)
    assert len(near) >= 3 and all(o.mood == 50.0 + BLD.THEATRE_MOOD for o in near)


def test_a_harbour_stands_on_the_shore_and_doubles_the_catch():
    w, a, hall = city()
    pos = w.find_site("harbour", hall.x, hall.y, 10)
    assert pos is not None and any(w.coastal(x, y) for x in range(pos[0], pos[0] + 2) for y in range(pos[1], pos[1] + 2))
    hb = w.place_site("harbour", *pos, a)
    w.complete_structure(hb, a)
    w.tick += 1
    assert BLD.fished(w, hb.x, hb.y) and not BLD.fished(w, hb.x + 40, hb.y + 40)


def test_a_city_plans_its_university():
    w, a, hall = city()
    a.learn("design:university", "taught", w.tick)
    a.inventory.update({"brick": 30, "stone": 20, "glass": 6, "paper": 8})
    w.tick = (w.tick // TICKS_PER_DAY + 1) * TICKS_PER_DAY + 120  # (midday)
    assert any(p["goal"] == "build a university" for _, p in BI.city_options(w, a))


def test_another_citys_university_doesnt_count_against_this_one():
    # one per city (the check round its hall); a share of the world's people let only one city in the world have one
    w, a, hall = city()
    a.learn("design:university", "taught", w.tick)
    a.inventory.update({"brick": 30, "stone": 20, "glass": 6, "paper": 8})
    w.tick = (w.tick // TICKS_PER_DAY + 1) * TICKS_PER_DAY + 120  # (midday)
    other = next((x, y) for x, y in ((hall.x + 45, hall.y), (hall.x - 45, hall.y), (hall.x, hall.y + 45), (hall.x, hall.y - 45))
                 if 4 <= x < w.w - 4 and 4 <= y < w.h - 4 and w.find_site("university", x, y, 6))
    put(w, "university", a, other, 6)
    assert len(w.agents) // 40 <= 1
    assert any(p["goal"] == "build a university" for _, p in BI.city_options(w, a))


def test_a_harbour_is_planned_by_the_fish_it_is_for(monkeypatch):
    w, a, hall = city()
    a.learn("design:harbour", "taught", w.tick)
    fish = (hall.x + 14, hall.y + 3)
    real = w.nearest_resource
    monkeypatch.setattr(w, "nearest_resource", lambda x, y, kind, *r, **k: fish if kind == "fish" else real(x, y, kind, *r, **k))
    seen = []
    monkeypatch.setattr(BI, "_build", lambda world, ag, d, cap, thought, near=None: seen.append((d, cap, near)) or None)
    BI.city_options(w, a)
    assert ("harbour", 1, fish) in seen
