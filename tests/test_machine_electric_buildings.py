"""The Machine and Electric Ages build what they know (issue #12). Both live worlds reached the Machine Age and stood
nothing new after it: the factory was the only thing an engine was for, and gears, paper, wire and lightbulbs had
no building at all. Each new building does what its blurb says, and instinct builds it where it helps."""

import random

from chits.brain import builder as BI
from chits.sim import actions
from chits.sim import animals as AN
from chits.sim import buildings as BLD
from chits.sim import lore
from chits.sim.items import DESIGNS
from test_buildings import _farm, _night, grass, put, village

MACHINE = ("steam_pump", "sawmill", "printing_press")
ELECTRIC = ("power_station", "street_lamp")


def test_each_new_building_is_an_idea_its_age_brings():
    for k in MACHINE + ELECTRIC:
        assert DESIGNS[k].blurb and DESIGNS[k].prereqs and DESIGNS[k].work > 0, k
    w, (a, _) = village()
    for k in ("recipe:engine", "design:well"):
        a.learn(k, "discovered", w.tick)
    w.check_insights(a)
    assert a.knows_design("steam_pump") and a.knows_design("sawmill") and not a.knows_design("power_station")
    a.learn("recipe:dynamo", "discovered", w.tick)
    w.check_insights(a)
    assert a.knows_design("power_station")


def test_a_steam_pump_waters_farms_within_10_tiles_through_a_drought():
    w, (a, _) = village()
    grass(w, a, 30)
    pump = put(w, "steam_pump", a)
    near = _farm(w, a, (pump.x + 4, pump.y))
    far = _farm(w, a, (pump.x + 22, pump.y))
    assert BLD.watered(w, near) and not BLD.watered(w, far)
    assert BLD.growth_mult(w, near) == BLD.PUMP_GROWTH * BLD.growth_mult(w, far)


def test_a_sawmill_doubles_the_wood_from_each_log():
    def first_chop(mill):
        w, (a, _) = village()
        if mill:
            put(w, "sawmill", a)
        res = actions.RUNNING
        s = {}
        for _ in range(3000):
            w.tick += 1
            res = actions._do_gather(w, a, {"do": "gather", "what": "wood", "qty": 1}, s)
            if a.has("wood") or res not in (actions.RUNNING,):
                break
        return a.inventory.get("wood", 0)

    plain, sawn = first_chop(False), first_chop(True)
    assert plain >= 1 and sawn == 2 * plain, (plain, sawn)


def test_a_power_station_speeds_work_at_a_station_but_not_by_hand():
    w, (a, _) = village()
    assert BLD.craft_speed(w, a, "brick") == 1.0
    put(w, "power_station", a)
    w.tick += 1  # (the working buildings are looked up once a tick)
    assert BLD.craft_speed(w, a, "brick") == BLD.POWER_SPEED  # (a kiln's work)
    assert BLD.craft_speed(w, a, "cord") == 1.0  # (made by hand anywhere)


def test_no_wolf_bites_in_a_street_lamps_light():
    for lamp in (False, True):
        w, (a, _) = village()
        grass(w, a, 12)
        w.animals.clear()
        if lamp:
            lp = put(w, "street_lamp", a)
            a.x, a.y = next(iter(w.stand_tiles_for_structure(lp)))
        _night(w)
        wolf = AN._add(w, "wolf", a.x + 1, a.y)
        a.health = 80.0
        AN.attacks(w)
        assert (a.health == 80.0) if lamp else (a.health < 80.0), lamp


def _press_village(paper):
    w, (a, b) = village()
    lib = put(w, "library", a)
    press = put(w, "printing_press", a, near=(lib.x + 4, lib.y))
    pile = put(w, "stockpile", a, near=(press.x + 2, press.y))
    if paper:
        pile.storage["paper"] = paper
    for o in (a, b):
        o.knows.pop("recipe:steel", None)
    a.learn("recipe:steel", "discovered", w.tick)
    w.first["recipe:steel"] = {"tick": w.tick, "by": a.id}
    assert len(lore.keepers(w)["recipe:steel"]) == 1
    return w, lib, pile


def test_a_printing_press_prints_what_only_a_few_know_into_the_library_on_paper():
    w, lib, pile = _press_village(paper=2)
    BLD._presses(w)
    printed = [w.tablets[t] for t in lib.shelf if t in w.tablets and w.tablets[t].knowledge == "recipe:steel"]
    assert printed and pile.storage.get("paper", 0) == 1
    BLD._presses(w)  # (once it can be read, it isn't printed again)
    assert sum(1 for t in w.tablets.values() if t.knowledge == "recipe:steel") == 1


def test_without_paper_the_press_prints_nothing_and_instinct_makes_some():
    w, lib, pile = _press_village(paper=0)
    BLD._presses(w)
    assert not any(t.knowledge == "recipe:steel" for t in w.tablets.values())
    a = next(iter(w.agents.values()))
    put(w, "workshop", a)  # (paper is made at a workshop)
    a.learn("recipe:paper", "discovered", w.tick)
    a.inventory.update({"fiber": 6})
    w.tick = 4 * 240 + 120  # (midday: nothing is started in the dark)
    plans = [p for _, p in BI.building_options(w, a, random.Random(1))]
    assert any(p["goal"] == "make paper for the press" for p in plans)


def test_instinct_builds_a_steam_pump_among_its_fields():
    w, ags = village(n=16, size=96)
    a = ags[0]
    grass(w, a, 30)
    for dx in (0, 5):
        _farm(w, a, (a.x + dx, a.y + 3))
    a.learn("recipe:engine", "discovered", w.tick)
    a.learn("design:well", "discovered", w.tick)
    w.check_insights(a)
    a.inventory.update({"brick": 8, "steel": 2, "engine": 1})
    w.tick = 4 * 240 + 120  # (midday: nothing is started in the dark)
    plans = [p for _, p in BI.building_options(w, a, random.Random(1))]
    assert any(p["goal"] == "build a steam pump" for p in plans)


def test_two_presses_on_the_same_day_dont_print_the_same_thing_twice():
    w, lib, pile = _press_village(paper=4)
    a = next(iter(w.agents.values()))
    put(w, "printing_press", a, near=(pile.x + 3, pile.y))
    w.tick += 1
    BLD._presses(w)
    assert sum(1 for t in w.tablets.values() if t.knowledge == "recipe:steel") == 1
