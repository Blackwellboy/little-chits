"""The space programme (sim/space.py, world.SPACE_PROGRAMME): after the first launch a rocket put together at the
launch pad flies again, each launch the next mission (a satellite, the Moon, a station in orbit, then expeditions),
and a village with a pad and someone who knows the rocket takes on making the next one."""

import pytest

from chits import views
from chits.brain import civic
from chits.brain import launches as LAUNCH
from chits.brain import prompt as P
from chits.brain.parse import normalize_step, parse_plan
from chits.sim import actions as ACT
from chits.sim import buildings as BLD
from chits.sim import food, projects, space
from chits.sim import world as W
from chits.sim.items import ITEMS, RECIPES
from chits.sim.world import World


@pytest.fixture(autouse=True)
def _programme_on(monkeypatch):
    monkeypatch.setattr(W, "SPACE_PROGRAMME", True)


def _world(n=3, seed=5):
    w = World("A", "A", seed, "direct", 64, n)
    ags = list(w.agents.values())
    a = ags[0]
    for o in ags:
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.mood = 50.0
        o.inventory.clear()
        o.plan = []
        o.born = min(o.born, w.tick - 10 * 240)  # (grown-ups)
    return w, ags


def _build(w, a, design, dx, dy=0, builders=None):
    xy = w.find_site(design, a.x + dx, a.y + dy, 8, reach=(a.x, a.y))
    s = w.place_site(design, xy[0], xy[1], a)
    s.builders.update(builders or {a.id: 10.0})
    w.complete_structure(s, a)
    return s


def _pad(w, ags):
    return _build(w, ags[0], "launch_pad", 3, builders={ags[0].id: 10.0, ags[1].id: 5.0})


def _run(w, a, step, ticks=900):
    r = ACT.RUNNING
    for _ in range(ticks):
        r = ACT.advance(w, a, step)
        if r != ACT.RUNNING:
            return r
        w.tick += 1
    return r


def test_the_first_launch_teaches_its_crew_and_builders_the_rocket():
    w, ags = _world()
    pad = _pad(w, ags)
    launch = [e for e in w.events if e.kind == "launch"]
    assert len(launch) == 1 and "rode the first rocket" in launch[0].text
    assert w.space == {"launches": 1}
    assert ags[0].knows_recipe("rocket") and ags[1].knows_recipe("rocket") and not ags[2].knows_recipe("rocket")
    assert ags[0].astronaut and pad.stations() == {"pad"}


def test_a_rocket_is_put_together_at_the_launch_pad_from_its_sections_and_fuel():
    w, ags = _world()
    a = ags[0]
    r = RECIPES["rocket"]
    assert r.station == "pad" and dict(r.inputs) == {"rocket_part": 2, "fuel": 2}
    assert set(ITEMS["rocket"].props) == {"huge", "shaped", "flies", "heat-proof"} and "at a launch pad" in r.describe()
    pad = _pad(w, ags)
    pile = _build(w, a, "stockpile", -2)
    pile.storage.update({"rocket_part": 2, "fuel": 2})
    assert _run(w, a, {"do": "work", "at": "pad", "what": "rocket"}) == ACT.DONE, a.last_result  # (as civic plans it)
    assert pile.storage.get("rocket", 0) + a.inventory.get("rocket", 0) == 1
    assert not pile.storage.get("rocket_part") and pad.produced.get("rocket") == 1
    # stores with no room for it: the rocket waits in hand for its launch
    pile.storage.clear()
    pile.storage.update({"stone": 10_000, "rocket_part": 2, "fuel": 2})
    a.inventory.clear()
    assert ACT.stockpile_room(pile, "rocket") == 0
    assert _run(w, a, {"do": "work", "at": "pad", "what": "rocket"}) == ACT.DONE, a.last_result
    assert a.inventory.get("rocket") == 1 and pad.produced.get("rocket") == 2
    # ...and nowhere else
    a.inventory.clear()
    w.structures.pop(pad.id)
    a.add("rocket_part", 2)
    a.add("fuel", 2)
    assert _run(w, a, {"do": "craft", "what": "rocket"}) != ACT.DONE and not a.has("rocket")


def test_a_launch_spends_the_rocket_and_advances_the_ladder():
    w, ags = _world()
    a, b = ags[0], ags[2]
    pad = _pad(w, ags)
    msg = _run(w, a, {"do": "launch"})
    assert msg.startswith("I have no rocket") and w.space["launches"] == 1
    a.add("rocket")
    assert _run(w, a, {"do": "launch"}) == ACT.DONE
    assert not a.has("rocket") and w.space["launches"] == 2 and w.space["satellites"] == 1
    ev = [e for e in w.events if e.kind == "space"][-1]
    assert ev.data["mission"] == "satellite" and "set the first satellite circling" in ev.text and ev.importance == 4
    assert a.id in ev.data["crew"] and b.id in ev.data["crew"] and len(ev.data["crew"]) <= space.CREW
    assert b.astronaut and a.name in ev.text
    assert ev.data["structure"] == pad.id and space.next_mission(w) == "moon"
    pad.durability = 0.0  # (in ruins)
    a.add("rocket")
    assert _run(w, a, {"do": "launch", "target": pad.id}) == "there is no working launch pad nearby" and a.has("rocket")
    w.structures.pop(pad.id)
    assert _run(w, a, {"do": "launch"}) == "there is no working launch pad nearby" and a.has("rocket")


def test_a_satellite_and_a_station_make_study_go_further_all_over_the_island():
    w, ags = _world()
    a = ags[0]
    pad = _pad(w, ags)
    assert BLD.study_mult(w, a) == 1.0
    space.launch(w, a, pad)  # a satellite
    assert BLD.study_mult(w, a) == pytest.approx(1.25)
    space.launch(w, a, pad)  # the Moon
    assert BLD.study_mult(w, a) == pytest.approx(1.25)
    space.launch(w, a, pad)  # a station in orbit
    assert BLD.study_mult(w, a) == pytest.approx(1.25 * 1.25)
    assert space.view(w)["station_day"] == w.tick // 240 + 1 and space.view(w)["next"] == "expedition"
    a.mood = 50.0
    space.daily(w)
    assert a.mood == pytest.approx(50.0 + space.STATION_MOOD)  # (and a small lift each day)


def test_the_moon_landing_is_a_wonder_everyone_remembers():
    w, ags = _world(n=4)
    a = ags[0]
    pad = _pad(w, ags)
    far = ags[3]
    far.x, far.y = a.x + 30, a.y
    space.launch(w, a, pad)
    for o in w.agents.values():
        o.mood = 50.0
    done = space.launch(w, a, pad)
    assert done["mission"] == "moon" and w.space["moon"] == w.tick
    ev = [e for e in w.events if e.kind == "space"][-1]
    assert ev.importance == 5 and ev.text.endswith("walked on the Moon — the whole island watched")
    for o in w.agents.values():
        assert o.mood == pytest.approx(50.0 + space.MOON_MOOD)
        assert any("Moon" in m.text and m.kind == "wonder" for m in o.memories), o.name
    assert far.id not in done["crew"]
    space.launch(w, a, pad)  # the station
    for o in w.agents.values():
        o.mood = 50.0
    done = space.launch(w, a, pad)  # then expeditions
    assert done["mission"] == "expedition" and "flew expedition 1 " in done["text"] and w.space["expeditions"] == 1
    assert all(o.mood == pytest.approx(50.0 + space.EXPEDITION_MOOD) for o in w.agents.values())


def test_the_programme_is_saved_with_the_world_and_only_when_there_is_one():
    w, ags = _world()
    assert "space" not in w.to_dict()  # (a world with no programme saves as it always did)
    pad = _pad(w, ags)
    space.launch(w, ags[0], pad)
    space.launch(w, ags[0], pad)
    d = w.to_dict()
    assert d["space"] == {"launches": 3, "satellites": 1, "moon": w.tick}
    w2 = World.from_dict(d)
    assert w2.space == w.space and space.next_mission(w2) == "station"
    sp = views.progress(w2, [])["space"]  # (the Progress panel)
    assert sp["launches"] == 3 and sp["satellites"] == 1 and sp["moon_day"] == w.tick // 240 + 1 and sp["next"] == "station"
    assert World.from_dict({k: v for k, v in d.items() if k != "space"}).space == {}  # an older save


def test_an_older_save_whose_pad_stood_before_the_programme_joins_it():
    w, ags = _world()
    pad = _pad(w, ags)
    w.space = {}
    for o in ags:
        o.knows.pop("recipe:rocket", None)
    assert space.launches(w) == 1  # (its first launch counts)
    w._new_day()  # (the day's turn)
    assert w.space == {"launches": 1} and ags[1].knows_recipe("rocket") and pad.id in w.structures
    # its builders long dead: the grown-ups living by it work out how the rocket went together
    w.space, pad.builders = {}, {}
    for o in ags:
        o.knows.pop("recipe:rocket", None)
    space.daily(w)
    assert w.space == {"launches": 1} and sum(o.knows_recipe("rocket") for o in ags) == min(len(ags), space.CREW)


def test_a_village_with_a_pad_and_the_rocket_makes_the_next_one_materials_first():
    w, ags = _world(n=5)
    a = ags[0]
    sc = projects._default(w)
    rocket_c = lambda: [c for c in projects.candidates(w, sc) if c[3] == "the space programme"]
    ags[0].learn("recipe:rocket", "taught", w.tick)
    for o in ags:
        o.learn("recipe:rocket_part", "taught", w.tick)
        o.learn("recipe:fuel", "taught", w.tick)
    pile = _build(w, a, "stockpile", -2)
    _build(w, a, "factory", 0, 4)
    assert not rocket_c()  # no pad
    _pad(w, ags)
    c = rocket_c()
    assert [(k, key, ex) for _, k, key, _, ex in c] == [("make", "fuel", {"n": 2, "launch": 1})]
    assert c[0][0] == projects.ROCKET
    pile.storage.update({"fuel": 2})
    c = rocket_c()
    assert [(k, key, ex) for _, k, key, _, ex in c] == [("make", "rocket_part", {"n": 2, "launch": 1})]
    p = projects.start(w, "make", "rocket_part", c[0][3], None, "need", c[0][4], sc)
    assert projects.title(p) == "make 2 rocket sections for the next launch"
    projects._put(w, sc, None)
    for o in ags:  # a section's own made parts first, where the village can make them
        o.learn("recipe:alloy", "taught", w.tick)
    assert [(key, ex) for _, _, key, _, ex in rocket_c()] == [("alloy", {"n": 4, "launch": 1})]
    pile.storage["alloy"] = 3  # (two sections take four)
    assert [(key, ex) for _, _, key, _, ex in rocket_c()] == [("alloy", {"n": 4, "launch": 1})]
    pile.storage["alloy"] = 4
    assert [key for _, _, key, _, _ in rocket_c()] == ["rocket_part"]  # (the engine: nobody here makes one)
    pile.storage.update({"rocket_part": 2})
    c = rocket_c()
    assert [(k, key, ex) for _, k, key, _, ex in c] == [("make", "rocket", {"n": 1, "launch": 1})]
    p = projects.start(w, "make", "rocket", c[0][3], None, "need", c[0][4], sc)
    assert projects.title(p) == "make a rocket for the next launch" == projects._heard(p)
    plan = civic.make_plan(w, a, p)
    assert plan["steps"][-1] == {"do": "work", "at": "pad", "what": "rocket", "qty": 1}  # (kept in hand to fly)
    pile.storage["rocket"] = 1
    projects._track_one(w, sc, p)  # the rocket is made: done
    done = [e for e in w.events if e.kind == "project_done"][-1]
    assert done.text.startswith("Village project done: a rocket is ready for the next launch")
    assert not rocket_c()  # (one waits for its launch)
    del pile.storage["rocket"]
    for o in ags:
        o.knows.pop("recipe:rocket", None)
    assert not rocket_c()  # nobody knows the rocket


def test_a_chit_near_the_pad_with_a_rocket_in_reach_takes_it_and_flies_it(monkeypatch):
    w, ags = _world()
    a = ags[0]
    pad = _pad(w, ags)
    pile = _build(w, a, "stockpile", -2)
    pile.storage["bread"] = 40  # (food in store)
    assert not food.short(w, a)
    assert LAUNCH.options(w, a) == []  # no rocket anywhere
    pile.storage["rocket"] = 1
    (wt, plan), = LAUNCH.options(w, a)
    assert [s["do"] for s in plan["steps"]] == ["take", "launch"] and plan["steps"][-1]["target"] == pad.id
    assert wt < 3.0  # (low-ish: it waits on other work)
    born = a.born
    a.born = w.tick
    assert LAUNCH.options(w, a) == []  # (a child flies nothing)
    a.born = born
    monkeypatch.setattr(food, "short", lambda world, who: True)
    assert LAUNCH.options(w, a) == []  # never while food is short
    monkeypatch.undo()
    monkeypatch.setattr(W, "SPACE_PROGRAMME", True)
    a.plan = [dict(s) for s in plan["steps"]]
    for _ in range(600):
        ACT.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    assert w.space["launches"] == 2 and not pile.storage.get("rocket") and not a.has("rocket"), a.last_result
    a.add("rocket")
    (_, plan), = LAUNCH.options(w, a)
    assert [s["do"] for s in plan["steps"]] == ["launch"]


def test_the_launch_verb_is_told_only_to_a_chit_that_knows_the_rocket_and_parses():
    w, ags = _world()
    a, c = ags[0], ags[2]
    assert '"do":"launch"' not in P.verb_guide(w, a) and "launch" not in P.compact_system_prompt(w, a).split("Verbs: ")[1]
    c.learn("recipe:rocket", "taught", w.tick)
    assert '"do":"launch"' not in P.verb_guide(w, c)  # (it knows the rocket, but no pad stands)
    c.knows.pop("recipe:rocket")
    _pad(w, ags)
    assert '"do":"launch"' in P.verb_guide(w, a) and '"do":"launch"' in P.system_prompt(w, a)
    assert "launch" in P.compact_system_prompt(w, a).split("Verbs: ")[1]
    assert '"do":"launch"' not in P.verb_guide(w, c) and '"do":"launch"' not in P.verb_guide(w)
    for raw in ({"do": "lift off"}, {"do": "blast off"}, {"do": "launch", "what": "rocket"}, "launch the rocket", "blast off"):
        assert normalize_step(raw)["do"] == "launch", raw
    assert parse_plan('{"goal":"fly","plan":[{"do":"launch","target":"s1"}]}')["steps"][0] == {"do": "launch", "target": "s1"}


def test_switched_off_the_pad_is_the_one_launch_as_before(monkeypatch):
    monkeypatch.setattr(W, "SPACE_PROGRAMME", False)
    w, ags = _world()
    a = ags[0]
    pad = _pad(w, ags)
    launch = [e for e in w.events if e.kind == "launch"]
    assert len(launch) == 1 and "rode the first rocket into the sky" in launch[0].text and ags[0].astronaut
    assert w.space == {} and "space" not in w.to_dict() and not any(o.knows_recipe("rocket") for o in ags)
    assert pad.stations() == set() and BLD.study_mult(w, a) == 1.0 and space.view(w) is None
    a.add("rocket")
    assert _run(w, a, {"do": "launch"}) != ACT.DONE and a.has("rocket") and w.space == {}
    assert LAUNCH.options(w, a) == []
    a.learn("recipe:rocket", "taught", w.tick)
    assert '"do":"launch"' not in P.verb_guide(w, a)
    assert not [c for c in projects.candidates(w) if c[3] == "the space programme"]
    space.daily(w)
    assert w.space == {}


def test_nothing_finds_the_rocket_so_no_idea_feedback_or_clue_counts_it():
    from chits.sim import research

    w, ags = _world()
    a = ags[0]
    a.familiar.update({"rocket_part", "fuel"})
    assert "rocket" not in research.candidates(w, a)  # (a scholar's idea for it would wait for ever)
    assert research.clue("rocket_part") == "heat-proof"  # (the clue it had before there were rockets)
    assert ACT._experiment_hint({"rocket_part": 1, "fuel": 1}, set()) == ""  # (nor does it feel close)
