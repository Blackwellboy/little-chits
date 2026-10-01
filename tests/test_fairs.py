"""Trade fairs: in a versus game the islands never meet, except for a few days each month when boats can cross. Play
games only; an experiment keeps its worlds apart."""

import asyncio
import random

from chits.brain import voyages as VOY
from chits.sim import actions
from chits.sim.agent import TICKS_PER_DAY


def _game(tmp_path, monkeypatch, mode="versus", contract=None):
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode=mode, contract=contract)
    for w in rt.worlds.values():
        for o in w.agents.values():
            o.hunger = o.energy = o.warmth = 95.0
    return rt


def _close(rt):
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def _at(rt, day, before=False):
    for w in rt.worlds.values():
        w.tick = day * TICKS_PER_DAY - (1 if before else 0) + (0 if before else 10)


def test_a_fair_opens_for_three_days_each_month_in_a_versus_game(tmp_path, monkeypatch):
    rt = _game(tmp_path, monkeypatch)
    seen = {}
    for d in (1, 29, 30, 32, 33, 59, 60):
        _at(rt, d)
        seen[d] = rt.fair()
    assert seen == {1: (0, 29), 29: (0, 1), 30: (3, 0), 32: (1, 0), 33: (0, 27), 59: (0, 1), 60: (3, 0)}
    _close(rt)
    for mode, contract in (("rivals", None), ("culture", None), ("versus", "experiment")):
        rt = _game(tmp_path / f"{mode}{contract}", monkeypatch, mode, contract)
        _at(rt, 30)
        assert rt.fair() == (0, 0), (mode, contract)
        _close(rt)


def test_the_sea_opens_and_closes_with_the_fair_and_both_worlds_hear_of_it(tmp_path, monkeypatch):
    rt = _game(tmp_path, monkeypatch)
    _at(rt, 30, before=True)
    rt.step_worlds(1)  # into day 30: the fair opens
    rt.step_worlds(1)
    assert all(w.contact and w.fair_days == 3 for w in rt.worlds.values())
    assert all(any(e.kind == "fair" and "trade fair is on" in e.text for e in w.events) for w in rt.worlds.values())
    _at(rt, 33, before=True)
    rt.step_worlds(1)
    rt.step_worlds(1)
    assert not any(w.contact for w in rt.worlds.values())
    assert all(any(e.kind == "fair" and "over" in e.text for e in w.events) for w in rt.worlds.values())
    _at(rt, 25)
    rt.step_worlds(1)
    assert all(w.fair_soon for w in rt.worlds.values())
    _close(rt)


def test_boats_at_sea_when_the_fair_ends_still_land_and_a_trader_can_go_home(tmp_path, monkeypatch):
    rt = _game(tmp_path, monkeypatch)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    _at(rt, 33)  # the fair is over
    a = next(iter(wa.agents.values()))
    wa.depart(a)
    wa.outbox[-1]["arrive_tick"] = wa.tick
    rt.step_worlds(1)
    t = next(x for x in wb.agents.values() if x.origin == "A")
    t.voyage_intent, t.stats["boat_abroad"] = "trade", 1
    assert not wb.contact
    assert actions.advance(wb, t, {"do": "sail", "intent": "home"}) == actions.DONE and t.id not in wb.agents
    _close(rt)


def test_a_village_builds_its_boat_before_the_fair(tmp_path, monkeypatch):
    rt = _game(tmp_path, monkeypatch)
    w = rt.worlds["A"]
    a = next(iter(w.agents.values()))
    hut = w.place_site("hut", *w.find_site("hut", a.x, a.y, 6), a)
    w.complete_structure(hut, a)
    a.home = hut.id
    pile = w.place_site("stockpile", *w.find_site("stockpile", a.x + 3, a.y, 6), a)
    w.complete_structure(pile, a)
    pile.storage["stone"] = 30
    a.learn("design:boat", "insight", w.tick)
    a.inventory.update({"wood": 10, "cord": 4})
    w.contact, w.fair_soon = False, False
    assert VOY.boat_plan(w, a) is None
    w._noboat = {}
    w.fair_soon = True
    assert VOY.boat_plan(w, a)["steps"][-1]["what"] == "boat"
    _close(rt)
