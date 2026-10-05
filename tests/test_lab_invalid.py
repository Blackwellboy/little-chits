"""A run that breaks a hard invariant is that run's outcome, not the batch's end.

The first real model study (JevK5 vs Gemma, 2026-10-05) lost its whole batch after 2 hours: one run's model server
stopped answering (12 read timeouts in a row: `brain_unavailable`), the worker raised InvariantBroken, the exception
couldn't be unpickled in the parent, and the process pool broke. Now the exception survives a process boundary, the
run records why it is invalid (invalid.json, with its last model calls), the others carry on, the report lists it
and leaves it out, and a resume keeps it unless told to retry."""

import json
import pickle
import threading
import time
from concurrent.futures import ProcessPoolExecutor

import pytest

from chits import invariants as INV
from chits.lab import report, run
from chits.lab.__main__ import main as lab_main
from chits.lab.spec import ExperimentSpec
from chits.sim.agent import TICKS_PER_DAY

BREAK = [{"kind": "negative_stock", "level": "hard", "tick": 7, "what": "x holds -1 wood", "agent": "a1"}]


def _raise_broken():
    raise INV.InvariantBroken(BREAK)


def test_an_invariant_break_survives_pickling_and_a_process_boundary():
    e = pickle.loads(pickle.dumps(INV.InvariantBroken(BREAK)))
    assert isinstance(e, INV.InvariantBroken) and e.broken == BREAK and str(e) == "negative_stock: x holds -1 wood"
    with ProcessPoolExecutor(max_workers=1) as ex:
        with pytest.raises(INV.InvariantBroken) as got:
            ex.submit(_raise_broken).result()
    assert got.value.broken == BREAK


def _break_silent_arm(monkeypatch, day=1):
    """Only the stigmergy world breaks (on `day`): one arm invalid, the other fine."""
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.culture == "stigmergy" and world.tick >= day * TICKS_PER_DAY:
            found.append({"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": "x holds -1 wood"})
        return found

    monkeypatch.setattr(INV, "check", fake)


def _proto(**kw):
    d = {"name": "x", "arms": [{"name": "talking"}, {"name": "silent", "culture": "stigmergy"}], "seeds": [3, 4],
         "days": 2, "size": 64, "population": 4, "metrics": ["discoveries", "population"]}
    d.update(kw)
    return d


@pytest.mark.parametrize("jobs", [1, 2])
def test_a_broken_run_is_recorded_and_the_batch_carries_on(tmp_path, monkeypatch, capsys, jobs):
    _break_silent_arm(monkeypatch)
    (tmp_path / "p.json").write_text(json.dumps(_proto()))
    out = tmp_path / "out"
    assert lab_main(["run", str(tmp_path / "p.json"), "--out", str(out), "--jobs", str(jobs)]) == 3
    assert "an invariant broke in 2 of 4 runs" in capsys.readouterr().err
    names = json.loads((out / "sealed" / "assignment.json").read_text())
    for rd in sorted((out / "runs").glob("*_*")):
        arm = names[rd.name.split("_")[1]]
        if arm == "talking":
            assert (rd / "result.json").exists() and not (rd / "invalid.json").exists()
        else:
            assert not (rd / "result.json").exists()
            bad = json.loads((rd / "invalid.json").read_text())
            assert bad["kind"] == "negative_stock" and bad["what"] == "x holds -1 wood"
            assert bad["tick"] == TICKS_PER_DAY and bad["day"] == 2
            assert bad["seed"] == int(rd.name.split("_")[0]) and bad["arm"] == "silent" and bad["label"] == rd.name.split("_")[1]
            assert bad["broken"][0]["kind"] == "negative_stock"
    text = report.write_pack(out).read_text()
    assert "## Invalid runs" in text and "negative_stock" in text and "x holds -1 wood" in text
    assert "silent" not in text  # (blind: the invalid runs are listed by label)
    assert "Runs finished: 2 of 4 (2 invalid" in text
    a = report.analyze(out)
    assert {r["label"] for r in a["runs"]} == {l for l, n in names.items() if n == "talking"}  # out of every mean
    assert "silent" in report.write_pack(out, unblind=True).read_text()


def test_a_resume_keeps_an_invalid_run_unless_told_to_retry_it(tmp_path, monkeypatch, capsys):
    """Kept by default: rerunning only the runs that broke until they don't would keep the lucky draws (a model whose
    server falls over on hard seeds would end up measured on easy ones). A retry is for a cause outside the
    experiment, a server that went down, and it is declared and kept on record."""
    _break_silent_arm(monkeypatch)
    spec = ExperimentSpec.from_dict(_proto(seeds=[3]))
    out = tmp_path / "out"
    first = run.run(spec, out)
    assert first["invalid"] == 1
    bad = next((out / "runs").glob("*/invalid.json"))
    before = bad.read_text()
    again = run.run(spec, out)
    assert again["ran"] == 0 and again["invalid"] == 1 and bad.read_text() == before  # kept, not rerun

    monkeypatch.undo()  # (whatever broke it is fixed)
    assert lab_main(["resume", str(out), "--retry-invalid"]) == 0
    rd = bad.parent
    assert (rd / "result.json").exists() and not (rd / "invalid.json").exists()
    assert json.loads((rd / "invalid-attempt-1.json").read_text())["kind"] == "negative_stock"  # the history stays
    result = json.loads((rd / "result.json").read_text())
    assert result["invalid_attempts"] == 1
    text = report.write_pack(out).read_text()
    assert "Runs finished: 2 of 2." in text and "retried after an invalid attempt" in text


# ------------------------------------------------------------------ the study's own break, reproduced

@pytest.fixture(scope="module")
def slow_fake():
    """A model server that answers slower than the brain will wait: every call times out, as JevK5's did."""
    import socket

    import uvicorn
    import fake_llm as F

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    F.STATE["latency"] = 0.4
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    F.STATE["latency"] = 0.005


def test_a_model_server_that_stops_answering_invalidates_only_its_run(slow_fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    brain = {"id": "m1", "label": "m1", "base_url": slow_fake, "model": "fake", "max_concurrency": 4, "timeout": 0.05,
             "max_tokens": 100}
    spec = ExperimentSpec.from_dict(_proto(arms=[{"name": "model", "brain": "m1"}, {"name": "instinct"}],
                                           allow_models=True, brains={"m1": brain}, seeds=[3], days=1))
    res = run.run(spec, tmp_path, jobs=2)  # (through the process pool, as the study ran)
    assert res["invalid"] == 1
    bad = json.loads(next(tmp_path.glob("runs/*/invalid.json")).read_text())
    assert bad["kind"] == "brain_unavailable" and "12 requests failed in a row" in bad["what"]
    assert bad["arm"] == "model" and bad["tape_calls"] >= 12
    assert len(bad["last_calls"]) == 5 and all("Timeout" in c["error"] for c in bad["last_calls"])
    assert len(list(tmp_path.glob("runs/*/result.json"))) == 1  # the instinct arm finished
