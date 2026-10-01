"""InvariantMonitor (research plan item 42): what must never happen, checked as a world runs."""

import pytest

from chits import diag
from chits import invariants as INV
from chits.brain.instinct import Instinct
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def setup():
    w = World("A", "A", 3, "direct", 64, 4)
    return w, next(iter(w.agents.values()))


def kinds(found, level=None):
    return sorted({b["kind"] for b in found if level is None or b["level"] == level})


def test_a_fresh_world_run_on_instinct_breaks_nothing():
    w, _ = setup()
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    for t in range(TICKS_PER_DAY * 3):
        w.step(hook)
    assert INV.check(w, "experiment", "instinct") == [] and INV.enforce(w, "experiment", "instinct") == []


def test_negative_stock_in_hands_or_stores():
    w, a = setup()
    a.inventory["wood"] = -1
    assert kinds(INV.check(w)) == ["negative_stock"]
    a.inventory["wood"] = 0
    st = w.place_site("stockpile", *w.find_site("stockpile", a.x, a.y), a)
    w.complete_structure(st, a)
    st.storage["stone"] = -2
    found = INV.check(w)
    assert kinds(found) == ["negative_stock"] and found[0]["structure"] == st.id


def test_knowledge_needs_a_known_way_and_proof_needs_a_tick():
    w, a = setup()
    a.learn("recipe:spear", "raised", w.tick)  # (a child raised by its parents: a real way)
    a.learn("recipe:basket", "taught", w.tick)
    a.made_it_work("recipe:basket", w.tick)
    assert INV.check(w) == []
    a.knows["recipe:cord"] = {"how": "osmosis", "tick": 0, "from": None, "status": "told"}
    a.knows["recipe:pot"] = {"how": "taught", "tick": 0, "from": None, "status": "worked"}
    assert kinds(INV.check(w)) == ["unknown_provenance", "unproven_worked"]


def test_experiment_contract_foreign_minds_and_stand_ins():
    w, a = setup()
    for o in w.agents.values():
        o.brain = "m"
    assert INV.check(w, "experiment", "m") == []
    a.brain = "other"
    assert kinds(INV.check(w, "experiment", "m")) == ["foreign_mind"]
    assert INV.check(w, "play", "m") == []  # play: a traveller keeps its mind
    a.brain = "m"
    a.plan, a.plan_source = [{"do": "rest"}], "instinct-filler"
    assert kinds(INV.check(w, "experiment", "m")) == ["stand_in"]
    a.plan_source = "instinct-duty"
    assert kinds(INV.check(w, "experiment", "m")) == ["stand_in"]
    a.plan = []  # (an empty plan left behind isn't acting on it)
    assert INV.check(w, "experiment", "m") == []
    b = list(w.agents.values())[1]
    b.brain, b.plan, b.plan_source = "instinct", [{"do": "rest"}], "instinct"
    assert kinds(INV.check(w, "experiment", "m")) == ["foreign_mind"]  # (instinct's own chits may use instinct)


def test_loops_are_soft_and_enforce_stops_only_on_hard():
    w, a = setup()
    for _ in range(diag.LOOP_N):
        diag.step_failed(w, a, "craft", "no kiln", "charcoal", "filler")
    found = INV.enforce(w)
    assert [(b["kind"], b["level"]) for b in found] == [("loops", "soft")] and "1 by filler" in found[0]["what"]
    a.inventory["wood"] = -3
    with pytest.raises(INV.InvariantBroken) as e:
        INV.enforce(w)
    assert [b["kind"] for b in e.value.broken] == ["negative_stock"] and "holds -3 wood" in str(e.value)


def _break_on_day(monkeypatch, day):
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick >= day * TICKS_PER_DAY:
            found.append({"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": "x holds -1 wood"})
        return found

    monkeypatch.setattr(INV, "check", fake)


def test_make_experiment_stops_on_a_hard_break_and_says_so(tmp_path, monkeypatch):
    import asyncio
    import json

    from chits.tools.experiment import run_experiment

    _break_on_day(monkeypatch, 1)
    s = asyncio.run(run_experiment({"A": None, "B": None}, 3.0, tmp_path, chits=4, seed=5, mode="versus"))
    assert s["ticks"] == TICKS_PER_DAY and {b["world"] for b in s["invariants"]["broken"]} == {"A", "B"}
    assert "**Stopped on day 2: an invariant broke**" in (tmp_path / "summary.md").read_text()
    assert json.loads((tmp_path / "summary.json").read_text())["invariants"]["broken"]


def test_a_clean_experiment_records_no_break(tmp_path):
    import asyncio

    from chits.tools.experiment import run_experiment

    s = asyncio.run(run_experiment({"A": None, "B": None}, 1.0, tmp_path, chits=4, seed=5, mode="versus"))
    assert s["ticks"] == TICKS_PER_DAY and s["invariants"]["broken"] == []
    assert "Stopped" not in (tmp_path / "summary.md").read_text()


def test_the_lab_stops_the_batch_on_a_hard_break(tmp_path, monkeypatch, capsys):
    import json

    from chits.lab.__main__ import main as lab_main

    _break_on_day(monkeypatch, 1)
    proto = {"name": "x", "arms": [{"name": "p"}, {"name": "q", "culture": "stigmergy"}], "seeds": [3], "days": 2,
             "size": 64, "population": 4}
    (tmp_path / "p.json").write_text(json.dumps(proto))
    assert lab_main(["run", str(tmp_path / "p.json"), "--out", str(tmp_path / "out")]) == 3
    assert "an invariant broke" in capsys.readouterr().err
    assert not list((tmp_path / "out").glob("runs/*/result.json"))  # (no result from a broken run)


def test_live_diagnostics_report_invariants_without_stopping(tmp_path):
    import asyncio

    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    next(iter(w.agents.values())).inventory["wood"] = -2
    inv = diag.report(rt)["worlds"][w.id]["invariants"]
    assert inv["hard"] == 1 and inv["counts"] == {"negative_stock": 1} and "holds -2 wood" in inv["examples"][0]
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_a_reloaded_chits_instinct_knowledge_stays_backed():
    from chits.sim.agent import Agent

    w, a = setup()
    assert INV.check(w) == []
    k = a.knows["design:hut"]
    assert k["status"] == "worked" and k["worked_tick"] == k["tick"]
    b = Agent.from_dict(a.to_dict())
    assert b.knows["design:hut"]["worked_tick"] == k["tick"]
    old = a.to_dict()  # a save from before: no status, no proof tick
    old["knows"] = {"design:hut": {"how": "instinct", "tick": 5, "from": None},
                    "recipe:spear": {"how": "taught", "tick": 7, "from": None, "status": "worked"}}
    b = Agent.from_dict(old)
    assert b.knows["design:hut"] == {"how": "instinct", "tick": 5, "from": None, "status": "worked", "worked_tick": 5}
    assert "worked_tick" not in b.knows["recipe:spear"]  # (told, then marked worked with no tick: left unbacked)
