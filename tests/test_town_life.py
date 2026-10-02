"""Town life: what a town has that a village doesn't. A tavern (and the ale brewed for it from surplus grain), a
bakery whose oven makes two for one, a healer's house, a tailor's loom for warm clothes, a park planted from surplus
seed, and apartment blocks for twelve. Each needs the idea of a town hall first, so worlds without towns play as
before."""

import random

from chits.brain import builder as BI
from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS, RECIPES
from test_buildings import put, village
from test_towns import town

LIFE = ("tavern", "bakery", "healer", "tailor", "park", "apartment")


def test_town_life_waits_for_the_idea_of_a_town_hall():
    for d in LIFE:
        assert ("design", "town_hall") in DESIGNS[d].prereqs and DESIGNS[d].blurb, d


def test_an_evening_at_the_tavern_cheers_more_with_ale_and_uses_it_up():
    for ale in (0, 20):
        w, ags = village(n=4)
        a = ags[0]
        tv = put(w, "tavern", a)
        pile = put(w, "stockpile", a, near=(tv.x + 3, tv.y))
        pile.storage["ale"] = ale
        w.tick += 1
        near = [o for o in w.agents.values() if tv.dist(o.x, o.y) <= BLD.TAVERN_RADIUS]
        assert len(near) >= 2
        for o in near:
            o.mood = 50.0
        BLD._tavern(w)
        want = BLD.TAVERN_MOOD + (BLD.ALE_MOOD if ale else 0)
        assert all(abs(o.mood - 50.0 - want) < 1e-6 for o in near), (ale, [o.mood for o in near])
        assert pile.storage.get("ale", 0) == max(0, ale - len(near))


def _bake(design):
    w, (a, _) = village()
    st = put(w, design, a)
    a.learn("recipe:bread", "discovered", w.tick)
    a.x, a.y = next(iter(w.stand_tiles_for_structure(st)))
    a.inventory.update({"grain": 2})
    if design == "campfire":
        st.fuel = 50.0
    w.tick += 1
    s = {}
    for _ in range(200):
        actions._do_craft(w, a, {"do": "craft", "what": "bread"}, s)
        if a.has("bread"):
            break
    return a.inventory.get("bread", 0)


def test_a_bakery_bakes_two_for_one():
    assert _bake("campfire") == 1 and _bake("bakery") == 2


def test_the_hurt_heal_three_times_as_fast_by_a_healer():
    def healed(with_healer):
        w, (a, _) = village()
        if with_healer:
            h = put(w, "healer", a)
            a.x, a.y = next(iter(w.stand_tiles_for_structure(h)))
        w.tick += 1
        a.health, a.hunger, a.warmth = 40.0, 90.0, 90.0
        w._needs(a, 0.6)
        return a.health - 40.0

    assert abs(healed(True) - BLD.HEALER_MULT * healed(False)) < 1e-6


def test_warm_clothes_are_woven_at_a_tailors_loom():
    w, (a, _) = village()
    tl = put(w, "tailor", a)
    assert RECIPES["clothes"].station == "loom" and "loom" in tl.stations()
    a.learn("recipe:clothes", "discovered", w.tick)
    a.x, a.y = next(iter(w.stand_tiles_for_structure(tl)))
    a.inventory.update({"fiber": 4, "cord": 1})
    w.tick += 1
    s = {}
    for _ in range(200):
        actions._do_craft(w, a, {"do": "craft", "what": "clothes"}, s)
        if a.has("clothes"):
            break
    assert a.has("clothes")


def test_a_park_cheers_those_near_it():
    w, (a, _) = village()
    p = put(w, "park", a)
    w.tick += 10
    joy = w._zones()[1]
    assert (p.y * w.w + p.x) in joy and ((p.y + 20) * w.w + p.x + 20) not in joy


def test_a_crowded_two_storey_house_can_become_an_apartment_block_for_twelve():
    assert "apartment" in BLD.UPGRADES["two_storey_house"] and BLD.HOME_CAP["apartment"] == 12
    assert "apartment" in BLD.HOMES and "apartment" in BLD.WARM_HOMES


def test_a_town_builds_what_it_lacks_and_keeps_it_in_use():
    w, a, hall = town()
    w.tick = 4 * TICKS_PER_DAY + 120  # (midday)
    for k in ("design:tavern", "recipe:ale", "design:healer"):
        a.learn(k, "taught", w.tick)
    a.inventory.update({"wood": 12, "brick": 6, "stone": 10, "pot": 2})
    goals = {p["goal"] for _, p in BI.town_life_options(w, a)}
    assert "build a tavern" in goals and "build a healer's house" in goals
    tv = put(w, "tavern", a, near=(hall.x, hall.y), radius=12)
    pile = put(w, "stockpile", a, near=(tv.x, tv.y), radius=8)
    pile.storage.update({"grain": 10, "berries": 6})
    put(w, "workshop", a, near=(tv.x, tv.y), radius=8)
    w.tick += 1
    goals = {p["goal"] for _, p in BI.town_life_options(w, a)}
    assert "brew ale for the tavern" in goals
    h = next(s for s in w.structures.values() if s.design == "healer") if any(
        s.design == "healer" for s in w.structures.values()) else put(w, "healer", a, near=(hall.x, hall.y), radius=12)
    a.health = 30.0
    a.x, a.y = h.x + 12, h.y
    w.tick += 1
    plans = {p["goal"]: p for _, p in BI.town_life_options(w, a)}
    assert plans["rest at the healer's"]["steps"][-1] == {"do": "rest"}


def test_a_town_tries_brewing_with_grain_and_berries_from_its_stores():
    # only a chit that happened to carry both ever tried, and no tavern rose in 20-day runs
    w, a, hall = town()
    a.learn("design:town_hall", "taught", w.tick)
    a.inventory.clear()
    ws = put(w, "workshop", a, near=(a.x, a.y), radius=12)
    a.x, a.y = next(iter(w.stand_tiles_for_structure(ws)))
    pile = put(w, "stockpile", a, near=(hall.x, hall.y), radius=10)
    w.tick = 4 * TICKS_PER_DAY + 120
    assert not any(p["goal"] == "try brewing" for _, p in BI.town_life_options(w, a))  # nothing to brew with
    pile.storage.update({"grain": 4, "berries": 2})
    w.tick += 1
    plan = next(p for _, p in BI.town_life_options(w, a) if p["goal"] == "try brewing")
    assert plan["steps"][:2] == [{"do": "take", "what": "grain", "qty": 2}, {"do": "take", "what": "berries", "qty": 1}]


def test_a_shift_at_a_bakery_stores_counts_and_reports_every_loaf():
    # a bakery's batch is two for one, and the shift counted, reported and delivered one per batch: half the bread
    # stayed in the baker's arms and the station's tally read half (Codex, #33)
    from test_production import _build, _run, _world

    w, a = _world()
    evs = []
    w.listeners.append(evs.append)
    bk = _build(w, a, "bakery", 5)
    pile = _build(w, a, "stockpile", -4, 0, {"grain": 30})
    w.learned(a, "recipe:bread", "taught")
    r = _run(w, a, {"do": "work", "at": "bakery"})
    assert r == actions.DONE
    bread = pile.storage.get("bread", 0)
    assert bread >= 4 and bread % BLD.BAKERY_MULT == 0, pile.storage
    assert not a.inventory.get("bread") and bk.produced == {"bread": bread} and a.stats["produced_bread"] == bread
    ev = [e for e in evs if e.kind == "produced"][-1]
    assert actions._count_words(w, "bread", bread) in ev.text
