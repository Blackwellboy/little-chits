"""Trade over the sea (upgrade idea 10): a village with a surplus and a boat sends a trader; abroad it barters its load
at the stores for goods of the same worth and sails home in the boat it came in, to the home it left."""

import asyncio
import random

from chits.brain import voyages as VOY
from chits.sim import actions
from chits.sim.items import base_value


def _rivals(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="rivals")
    for w in rt.worlds.values():
        w.contact = True  # (the runtime sets this each step)
        for o in w.agents.values():
            o.hunger = o.energy = o.warmth = 95.0
    return rt


def _close(rt):
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def _put(w, a, design, near):
    st = w.place_site(design, *w.find_site(design, near[0], near[1], 8, reach=(a.x, a.y)), a)
    w.complete_structure(st, a)
    return st


def _do(w, a, step, limit=900):
    for _ in range(limit):
        w.tick += 1
        res = actions.advance(w, a, step)
        if res != actions.RUNNING:
            return res
    return "timed out"


def _village(w):
    """An adult with a hut, a stockpile beside it and a boat on the shore."""
    a = next(x for x in w.agents.values() if not x.is_child(w.tick))
    hut = _put(w, a, "hut", (a.x, a.y))
    a.home = hut.id
    pile = _put(w, a, "stockpile", (hut.x + 3, hut.y))
    return a, hut, pile


def test_a_trader_takes_the_surplus_over_barters_it_fairly_and_comes_home_with_the_boat(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    a, hut, pile = _village(wa)
    pile.storage["wood"] = 30
    boat = _put(wa, a, "boat", (a.x, a.y))
    [(_, plan)] = VOY.options(wa, a, random.Random(1))
    assert [s["do"] for s in plan["steps"]] == ["take", "sail"] and plan["steps"][1]["intent"] == "trade"
    for step in plan["steps"]:
        assert _do(wa, a, step) == actions.DONE
    assert a.id not in wa.agents and boat.id not in wa.structures and pile.storage["wood"] == 30 - VOY.CARGO
    [voyage] = wa.outbox
    assert voyage["agent"]["voyage_intent"] == "trade" and voyage["agent"]["voyage_home"] == hut.id
    assert VOY.send_plan(wa, next(iter(wa.agents.values()))) is None  # one trader at a time

    wa.tick = voyage["arrive_tick"]
    rt._deliver_boats()
    other = next(iter(wa.agents.values()))
    _put(wa, other, "boat", (other.x, other.y))
    assert not wa.outbox and VOY.send_plan(wa, other) is None  # the next trader waits a few days
    t = next(x for x in wb.agents.values() if x.origin == "A")
    host = next(x for x in wb.agents.values() if not x.origin)
    t.x, t.y = host.x, host.y  # (the boat lands anywhere on the coast; walk it to the village for the test)
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"stone": 20, "fiber": 20, "wood": 5})
    [(w, plan)] = VOY.options(wb, t, random.Random(1))
    assert w == VOY.ABROAD_W and plan["steps"] == [{"do": "trade", "at": "stores"}]
    assert _do(wb, t, plan["steps"][0]) == actions.DONE
    got = {k: n for k, n in t.inventory.items() if k in ("stone", "fiber")}
    assert not t.inventory.get("wood") and stores.storage["wood"] == 5 + VOY.CARGO
    assert got and sum(got.values()) <= actions.BARTER_LOAD
    assert sum(base_value(k) * n for k, n in got.items()) <= VOY.CARGO * base_value("wood")  # never more than it gave
    [ev] = [e for e in wb.events if e.kind == "trade" and e.data.get("overseas")]
    assert wb.relations["A"]["trades"] == 1 and wa.relations["B"]["trades"] == 1
    assert "time to sail home" in actions.advance(wb, t, {"do": "trade", "at": "stores"})  # once a trip

    [(_, plan)] = VOY.options(wb, t, random.Random(1))
    assert plan["steps"] == [{"do": "sail", "intent": "home"}]
    assert _do(wb, t, plan["steps"][0]) == actions.DONE and t.id not in wb.agents
    [back] = wb.outbox
    boats = sum(1 for s in wa.structures.values() if s.design == "boat" and s.functional)
    wb.tick = back["arrive_tick"]
    rt._deliver_boats()
    a2 = wa.agents[a.id]
    assert a2.origin == "" and a2.home == hut.id and a2.voyage_intent == "home"
    assert {k: a2.inventory.get(k) for k in got} == got
    assert sum(1 for s in wa.structures.values() if s.design == "boat" and s.functional) == boats + 1  # kept
    assert not a2.stats.get("boat_abroad") and not a2.stats.get("traded_trip")
    _close(rt)


def test_a_village_with_a_surplus_and_no_boat_builds_one(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wa = rt.worlds["A"]
    a, hut, pile = _village(wa)
    a.learn("design:boat", "insight", wa.tick)
    a.inventory.update({"wood": 10, "cord": 4})
    assert VOY.options(wa, a, random.Random(1)) == []  # nothing to spare
    wa._noboat.clear()
    pile.storage["stone"] = 25
    [(_, plan)] = VOY.options(wa, a, random.Random(1))
    assert plan["steps"][-1]["do"] == "build" and plan["steps"][-1]["what"] == "boat"
    _put(wa, a, "boat", (a.x, a.y))
    [(_, plan)] = VOY.options(wa, a, random.Random(1))
    assert plan["steps"][-1] == {"do": "sail", "target": plan["steps"][-1]["target"], "intent": "trade"}
    _close(rt)


def test_no_trade_without_contact_and_a_trader_with_nothing_to_trade_for_goes_home(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    a, hut, pile = _village(wa)
    pile.storage["wood"] = 30
    _put(wa, a, "boat", (a.x, a.y))
    wa.contact = False
    assert VOY.options(wa, a, random.Random(1)) == []
    assert "only a trader" in actions.advance(wa, a, {"do": "trade", "at": "stores"})

    host = next(x for x in wb.agents.values() if not x.origin)
    t = next(x for x in wb.agents.values() if x is not host)
    t.origin, t.voyage_intent, t.stats["boat_abroad"] = "A", "trade", 1
    t.inventory = {"wood": 8}
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"wood": 30})  # nothing here but what it brought
    for st in list(wb.structures.values()):
        if st.design in ("stockpile", "outpost") and st is not stores:
            st.storage.clear()
    assert "time to sail home" in _do(wb, t, {"do": "trade", "at": "stores"})
    [(_, plan)] = VOY.options(wb, t, random.Random(1))
    assert plan["steps"] == [{"do": "sail", "intent": "home"}]
    _close(rt)


def test_a_chit_comes_home_under_the_id_it_left_with_and_the_trade_wait_is_saved():
    import json

    from chits.sim.world import World

    wa, wb = World("A", "A", 5, "direct", 64, 3), World("B", "B", 5, "direct", 64, 3)
    wa.contact = wb.contact = True
    a = next(iter(wa.agents.values()))
    wa.agents.pop(a.id)
    a.id = "a1-x"  # renamed by a clash at home long ago: its children know it by this id
    wa.agents[a.id] = a
    host = next(iter(wb.agents.values()))
    wb.agents.pop(host.id)
    host.id = "a1-x"  # someone over the sea already goes by that id
    wb.agents[host.id] = host
    wa.depart(a)
    there = wb.arrive(wa.outbox.pop()["agent"], "A")
    assert there.id == "a1-x-x"
    wb.depart(there)
    back = wa.arrive(wb.outbox.pop()["agent"], "B")
    assert back.id == "a1-x" and back.origin == ""
    VOY.sent(wa)
    assert World.from_dict(json.loads(json.dumps(wa.to_dict()))).civic["trader_sent"] == wa.tick
