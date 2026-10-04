"""Fixes from the 2026-09-30 audits, batch 1 (docs/FIXES_2026-09-30.md): F1, F2, F3, F4, F9, F22."""

import asyncio
import json

import pytest

from chits import invariants as INV
from chits.brain.llm import BrainConfig
from chits.sim import projects
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


# F1: a strict experiment stops when a configured model stops answering
def test_an_experiment_stops_when_a_model_stops_answering(tmp_path):
    from chits.tools.experiment import BRAIN_FAIL_STOP, run_experiment

    dead = BrainConfig(id="dead", label="Dead", base_url="http://127.0.0.1:9/v1", model="m", timeout=2)
    s = asyncio.run(run_experiment({"A": dead, "B": None}, 2.0, tmp_path, chits=4, seed=5, mode="versus"))
    stop = s["invariants"]["broken"]
    assert s["ticks"] < 2 * TICKS_PER_DAY and stop and stop[0]["kind"] == "brain_unavailable" and stop[0]["world"] == "A"
    assert f"{BRAIN_FAIL_STOP} requests failed in a row" in stop[0]["what"]
    assert "a model stopped answering" in (tmp_path / "summary.md").read_text()


def test_a_disabled_brain_stops_it_at_once(tmp_path):
    from chits.tools.experiment import run_experiment

    off = BrainConfig(id="off", label="Off", base_url="http://127.0.0.1:9/v1", model="m", enabled=False)
    s = asyncio.run(run_experiment({"A": None, "B": off}, 1.0, tmp_path, chits=4, seed=5, mode="versus"))
    assert s["ticks"] == 1 and "(disabled)" in s["invariants"]["broken"][0]["what"]


# F2: hard invariants are checked after every tick, not once a day
def _break_at_tick(monkeypatch, tick):
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick == tick:  # (broken for one tick only, then "fixed")
            found.append({"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": "x holds -1 wood"})
        return found

    monkeypatch.setattr(INV, "check", fake)


def test_a_break_that_lasts_one_tick_still_stops_an_experiment(tmp_path, monkeypatch):
    from chits.tools.experiment import run_experiment

    w = World("A", "A", 5, "direct", 128, 4)
    _break_at_tick(monkeypatch, w.tick + 7)
    s = asyncio.run(run_experiment({"A": None, "B": None}, 1.0, tmp_path, chits=4, seed=5, mode="versus"))
    assert s["ticks"] == 7 and s["invariants"]["broken"]


def test_and_stops_a_lab_run(tmp_path, monkeypatch, capsys):
    from chits.lab.__main__ import main as lab_main

    w = World("A", "p", 3, "direct", 64, 4)
    _break_at_tick(monkeypatch, w.tick + 7)
    proto = {"name": "x", "arms": [{"name": "p"}, {"name": "q", "culture": "stigmergy"}], "seeds": [3], "days": 1,
             "size": 64, "population": 4}
    (tmp_path / "p.json").write_text(json.dumps(proto))
    assert lab_main(["run", str(tmp_path / "p.json"), "--out", str(tmp_path / "out")]) == 3


# F3: only an invariant break is reported as one
def test_the_lab_does_not_call_any_runtime_error_an_invariant(tmp_path, monkeypatch):
    from chits.lab import run
    from chits.lab.__main__ import main as lab_main

    def boom(*a, **k):
        raise RuntimeError("an ordinary bug")

    monkeypatch.setattr(run, "run", boom)
    proto = {"name": "x", "arms": [{"name": "p"}, {"name": "q", "culture": "stigmergy"}], "seeds": [3], "days": 1,
             "size": 64, "population": 4}
    (tmp_path / "p.json").write_text(json.dumps(proto))
    with pytest.raises(RuntimeError, match="an ordinary bug"):
        lab_main(["run", str(tmp_path / "p.json"), "--out", str(tmp_path / "out")])


# F4: an undiscovered thing is named only in the riddle's words
def _chief(monkeypatch, cands):
    w = World("A", "A", 3, "direct", 64, 4)
    a = next(iter(w.agents.values()))
    w.leader = a.id
    w.flags["say"] = True
    monkeypatch.setattr(projects, "candidates", lambda world, sc=None: cands)
    return w, a


def test_a_chief_cannot_name_an_undiscovered_thing_by_its_real_name(monkeypatch):
    cand = (1.0, "discover", "copper", "on the road to the Bronze Age", {})
    w, a = _chief(monkeypatch, [cand])
    assert not projects.name_project(w, a, "discover copper")
    assert not projects.name_project(w, a, "Copper")
    riddle = projects._heard({"kind": "discover", "key": "copper"})
    assert "copper" not in riddle.lower()
    assert projects.name_project(w, a, riddle) and projects.of(w)["key"] == "copper"


def test_what_is_made_or_built_can_still_be_named(monkeypatch):
    w, a = _chief(monkeypatch, [(1.0, "make", "spear", "why", {"n": 2, "for": "hut"})])
    assert projects.name_project(w, a, "make a spear")
    w, a = _chief(monkeypatch, [(1.0, "build", "stockpile", "why", {})])
    assert projects.name_project(w, a, "build a stockpile")


# F9: a warehouse's goods count as the village's
def test_warehouse_stock_counts_for_village_projects():
    w = World("A", "A", 3, "direct", 64, 4)
    a = next(iter(w.agents.values()))
    st = w.place_site("warehouse", *w.find_site("warehouse", a.x, a.y), a)
    w.complete_structure(st, a)
    st.storage["stone"] = 30
    assert projects.stock(w, "stone") >= 30


# F22: a model-server probe gets a JSON 404, not the game's page
def test_api_looking_paths_get_a_json_404(tmp_path):
    from chits.app import page

    (tmp_path / "index.html").write_text("<html>game</html>")
    (tmp_path / "logo.svg").write_text("<svg/>")
    for p in ("v1/models", "props", "health", "api/nope", "metrics", "slots"):
        r = page(tmp_path, p)
        assert r.status_code == 404 and b"not a model server" in r.body, p
    assert str(page(tmp_path, "").path).endswith("index.html")
    assert str(page(tmp_path, "world/B").path).endswith("index.html")  # (the viewer's own routes still get the page)
    assert str(page(tmp_path, "logo.svg").path).endswith("logo.svg")
