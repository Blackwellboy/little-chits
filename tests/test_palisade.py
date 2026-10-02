"""Walls for wolves (F28; docs/UPGRADE_PLAN.md: "walls and a watchtower (for wolves)"). A palisade round a town: no
wolf bites anywhere within 22 tiles of its gate, and a town with wolves about builds one."""

from chits.brain import builder as BI
from chits.sim import animals as AN
from chits.sim import buildings as BLD
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS
from test_buildings import _night, grass
from test_towns import put, town


def test_no_wolf_bites_inside_a_palisade():
    for walled in (False, True):
        w, a, hall = town()
        grass(w, a, 30)
        w.animals.clear()
        if walled:
            put(w, "palisade", a, (hall.x, hall.y), 12)
        a.x, a.y = hall.x + 15, hall.y  # well inside the wall, far from any tower
        _night(w)
        wolf = AN._add(w, "wolf", a.x + 1, a.y)
        a.health = 80.0
        AN.attacks(w)
        assert (a.health == 80.0) if walled else (a.health < 80.0), walled


def test_a_town_with_wolves_about_walls_itself_in():
    w, a, hall = town()
    assert ("design", "town_hall") in DESIGNS["palisade"].prereqs
    a.learn("design:palisade", "taught", w.tick)
    pile = put(w, "stockpile", a, (hall.x, hall.y), 12)
    pile.storage.update({"wood": 30, "stone": 10, "cord": 6})
    w.tick = 4 * TICKS_PER_DAY + 120
    assert BI.palisade_option(w, a) == []  # no wolves: no wall
    AN._add(w, "wolf", a.x + 8, a.y)
    plan = BI.palisade_option(w, a)
    assert plan and plan[0][1]["goal"] == "build a palisade"
    import random
    assert any(p["goal"] == "build a palisade" for _, p in BI.building_options(w, a, random.Random(1)))


def test_a_wolf_outside_the_wall_cant_bite_those_inside():
    # only the wolf's place was checked: one standing just outside the wall bit a chit just inside it (Codex, #47)
    w, a, hall = town()
    grass(w, a, 40)
    w.animals.clear()
    pal = put(w, "palisade", a, (hall.x, hall.y), 12)
    x = next(x for x in range(pal.x, w.w - 2) if BLD.walled(w, x, pal.y) is not None and BLD.walled(w, x + 1, pal.y) is None)
    a.x, a.y = x, pal.y
    _night(w)
    AN._add(w, "wolf", x + 1, pal.y)
    a.health = 80.0
    AN.attacks(w)
    assert a.health == 80.0


def test_another_towns_wall_doesnt_count_against_this_one():
    # the cap was a share of the world's people: one palisade anywhere kept a 24-chit world's second town unwalled
    w, a, hall = town()
    a.learn("design:palisade", "taught", w.tick)
    pile = put(w, "stockpile", a, (hall.x, hall.y), 12)
    pile.storage.update({"wood": 30, "stone": 10, "cord": 6})
    w.tick = 4 * TICKS_PER_DAY + 120
    AN._add(w, "wolf", a.x + 8, a.y)
    other = next((x, y) for x, y in ((hall.x + 40, hall.y), (hall.x - 40, hall.y), (hall.x, hall.y + 40), (hall.x, hall.y - 40))
                 if 4 <= x < w.w - 4 and 4 <= y < w.h - 4 and w.find_site("palisade", x, y, 6))
    put(w, "palisade", a, other, 6)
    assert len(w.agents) // 20 <= 1
    plan = BI.palisade_option(w, a)
    assert plan and plan[0][1]["goal"] == "build a palisade"
