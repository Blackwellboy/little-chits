"""Model arms in the Lab, ready for a first model-vs-model study: a `make lab` entry point, the same explicit sampling
as `make experiment`, a BrainTape per run, thinking opportunities per chit-day, card swaps, server URLs set at run
time, and a check that each server really serves the model the protocol names."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from chits.lab import report, run
from chits.lab.__main__ import main as lab_main
from chits.lab.spec import ExperimentSpec, SpecError
from chits.tools.experiment import SAMPLING

ROOT = Path(__file__).resolve().parent.parent
SHARED = {"max_concurrency": 4, "timeout": 30.0, "temperature": 0.7, "max_tokens": 200, "json_mode": True,
          "disable_thinking": True}


def _free_port():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def fake():
    import uvicorn
    import fake_llm as F

    F.STATE["latency"] = 0.002
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True


def _brain(bid, url, **kw):
    return {"id": bid, "label": bid, "base_url": url, "model": "", **SHARED, **kw}


def _proto(url, **kw):
    d = {"name": "two models", "arms": [{"name": "one", "brain": "m1"}, {"name": "two", "brain": "m2"}],
         "allow_models": True, "brains": {"m1": _brain("m1", url), "m2": _brain("m2", url)},
         "seeds": [7, 8], "days": 1, "size": 64, "population": 3,
         "metrics": ["discoveries", "starved", "model_step_share", "requests_per_chit_day", "waiting_share"]}
    d.update(kw)
    return d


@pytest.fixture
def allow(monkeypatch):
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")


# ------------------------------------------------------------------ 1. make lab

@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_make_lab_runs_the_lab_from_the_repository_root():
    out = subprocess.run(["make", "-s", "lab", f"BIN={Path(sys.executable).parent}",
                          "ARGS=lint docs/protocols/treatments/stone-tools.json"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert '"claims"' in out.stdout


# ------------------------------------------------------------------ 2. the same sampling as make experiment

def test_model_arms_send_the_default_sampling_unless_the_config_sets_its_own(fake, allow, tmp_path):
    import fake_llm as F

    F.STATE["bodies"] = []
    spec = ExperimentSpec.from_dict(_proto(fake, seeds=[7]))
    run.run(spec, tmp_path / "default")
    bodies = F.STATE.pop("bodies")
    assert bodies and all(b.get(k) == v for b in bodies for k, v in SAMPLING.items())
    assert all("seed" in b for b in bodies)  # (and every request is seeded)
    man = json.loads((tmp_path / "default" / "manifest.json").read_text())
    assert man["sampling"] == SAMPLING and man["lockstep"] is True and man["request_seeds"] is True

    F.STATE["bodies"] = []
    own = {"top_p": 0.8, "top_k": 20, "min_p": 0.0}
    spec = ExperimentSpec.from_dict(_proto(fake, seeds=[7], brains={"m1": _brain("m1", fake, extra_body=own),
                                                                   "m2": _brain("m2", fake, extra_body=own)}))
    run.run(spec, tmp_path / "own")
    bodies = F.STATE.pop("bodies")
    assert bodies and all(b.get(k) == v for b in bodies for k, v in own.items())


# ------------------------------------------------------------------ 3 and 4. a tape per run; opportunities per chit-day

def test_each_model_run_records_a_tape_and_reports_its_thinking_opportunities(fake, allow, tmp_path):
    spec = ExperimentSpec.from_dict(_proto(fake, arms=[{"name": "model", "brain": "m1"}, {"name": "instinct"}],
                                           brains={"m1": _brain("m1", fake)}))
    run.run(spec, tmp_path)
    rows = run.results(tmp_path)
    assert len(rows) == 4
    for r in rows:
        rd = tmp_path / "runs" / f"{r['seed']}_{r['label']}"
        f = r["final"]
        for k in ("starved", "model_step_share", "requests_per_chit_day", "waiting_share", "wait_seconds_per_chit_day"):
            assert k in f, k
        if r.get("compute"):
            tape = (rd / "tape.jsonl").read_text().splitlines()
            assert len(tape) == r["compute"]["requests"] > 0  # every call, answered or failed, is on the tape
            assert f["requests_per_chit_day"] > 0 and 0 < f["model_step_share"] <= 1 and 0 <= f["waiting_share"] <= 1
            assert r["compute"]["chit_days"] > 0
            assert f["wait_seconds_per_chit_day"] > 0  # (lockstep: the world, not the chit, waits for the answers)
        else:
            assert not (rd / "tape.jsonl").exists()
            assert f["requests_per_chit_day"] == 0 and f["model_step_share"] == 0 and f["wait_seconds_per_chit_day"] == 0
    text = report.write_pack(tmp_path).read_text()
    assert "## Thinking opportunities" in text and "requests per chit-day" in text and "seconds waited" in text


def test_starved_counts_the_dead_who_starved():
    from chits.lab import extract
    from chits.sim.world import World

    w = World("A", "A", 3, "direct", 64, 4)
    a, b, *_ = list(w.agents.values())
    w.kill(a, "starvation")
    w.kill(b, "old age")
    assert extract.row(w, 4)["starved"] == 1


# ------------------------------------------------------------------ 5. card swaps

def test_card_swap_is_checked_and_swaps_servers_on_every_other_seed(fake, allow, tmp_path):
    other = fake.replace("127.0.0.1", "localhost")  # (the same fake answers on both: what matters is which URL)
    with pytest.raises(SpecError, match="card_swap"):
        ExperimentSpec.from_dict(_proto(fake, card_swap={"m1": other}))  # every model brain needs its other server
    with pytest.raises(SpecError, match="card_swap"):
        ExperimentSpec.from_dict(_proto(fake, card_swap={"m1": other, "m2": fake, "m3": fake}))
    spec = ExperimentSpec.from_dict(_proto(fake, brains={"m1": _brain("m1", fake), "m2": _brain("m2", other)},
                                           card_swap={"m1": other, "m2": fake}, seeds=[7, 8, 9]))
    run.run(spec, tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert [r["card_swapped"] for r in man["runs"]] == [False, True, False]
    served = {}
    for rd in (tmp_path / "runs").glob("*_*"):
        s = json.loads((rd / "server.json").read_text())
        served[(int(rd.name.split("_")[0]), s["brain"])] = s["base_url"]
        assert "base_url" not in (rd / "result.json").read_text()  # (the blind report never sees which server)
    assert served[(7, "m1")] == fake and served[(7, "m2")] == other
    assert served[(8, "m1")] == other and served[(8, "m2")] == fake
    assert served[(9, "m1")] == fake


def test_a_protocol_without_new_options_keeps_its_old_fingerprint():
    assert ExperimentSpec.load(ROOT / "docs/protocols/speech-vs-silence.json").fingerprint() == "665532ad4fcb145c"
    assert ExperimentSpec.load(ROOT / "docs/protocols/told-stone-tools.json").fingerprint() == "b68f2be7f448a2f6"


# ------------------------------------------------------------------ server URLs at run time; the model check

def test_server_urls_are_set_on_the_command_line_and_sealed(fake, allow, tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps(_proto("http://127.0.0.1:9/v1", seeds=[7])))
    assert lab_main(["run", str(p), "--out", str(tmp_path / "bad"), "--url", "nobody=" + fake]) == 2
    assert lab_main(["run", str(p), "--out", str(tmp_path / "o"), "--url", f"m1={fake}", "--url", f"m2={fake}"]) == 0
    man = json.loads((tmp_path / "o" / "manifest.json").read_text())
    assert man["protocol"]["brains"]["m1"]["base_url"] == fake == man["protocol"]["brains"]["m2"]["base_url"]


def test_a_server_that_does_not_serve_the_named_model_stops_the_run_before_it_starts(fake, allow, tmp_path):
    spec = ExperimentSpec.from_dict(_proto(fake, brains={"m1": _brain("m1", fake, model="not-this-one"),
                                                         "m2": _brain("m2", fake, model="fake-chit-7b")}))
    with pytest.raises(SpecError, match="not-this-one"):
        run.run(spec, tmp_path / "x")
    assert not (tmp_path / "x" / "manifest.json").exists()
    ok = ExperimentSpec.from_dict(_proto(fake, seeds=[7], brains={"m1": _brain("m1", fake, model="fake-chit-7b"),
                                                                  "m2": _brain("m2", fake, model="fake-chit-7b")}))
    run.run(ok, tmp_path / "y")
    man = json.loads((tmp_path / "y" / "manifest.json").read_text())
    assert "fake-chit-7b" in man["servers"][fake]


# ------------------------------------------------------------------ 6. the first study's protocol

def test_the_jevk5_vs_gemma_protocol_is_the_study_that_was_asked_for():
    spec = ExperimentSpec.load(ROOT / "docs/protocols/jevk5-vs-gemma.json")
    models = {b["model"] for b in spec.brains.values()}
    assert models == {"jevk5-9b-v0.3.3-Q8_0.gguf", "gemma-4-12b-it-Q4_K_M.gguf"}
    assert len(spec.arms) == 2 and {a.brain for a in spec.arms} == set(spec.brains)
    assert len({a.culture for a in spec.arms}) == 1 and not any(a.flags or a.treatment for a in spec.arms)
    assert len(spec.seeds) == 6 and spec.days == 25 and spec.population == 12
    assert spec.blind and spec.contract == "experiment" and spec.allow_models
    assert spec.metrics == ["discoveries", "era", "population", "starved", "model_step_share", "requests_per_chit_day"]
    assert {b["base_url"] for b in spec.brains.values()} == {"http://127.0.0.1:18195/v1", "http://127.0.0.1:18196/v1"}
    assert "T21" in spec.notes and "both arms" in spec.notes
