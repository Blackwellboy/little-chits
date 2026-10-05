"""An invalid run must not unblind the report (Codex on #122). `brain_unavailable` says which model stopped
answering, so its text names the brain. Everything the blind report and the CLI read about an invalid run is
redacted to the blind label. The raw record goes to invalid-sealed.json, which only an unblinded report reads, and it
keeps every break, however many there were."""

import json
import socket
import threading
import time

import pytest

from chits import invariants as INV
from chits.lab import report, run
from chits.lab.__main__ import main as lab_main
from chits.sim.agent import TICKS_PER_DAY

LABEL, MODEL, BRAIN, ARM = "Secretmodel Nine", "secretmodel-9b-Q8_0.gguf", "secretbrain", "secretarm"


@pytest.fixture(scope="module")
def slow_fake():
    """A server slower than the brain will wait, which lists the secret model's name."""
    import uvicorn
    import fake_llm as F

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    old = (F.STATE.get("latency"), F.STATE.get("models"))
    F.STATE["latency"] = 0.4
    F.STATE["models"] = ["fake-chit-7b", "fake", MODEL]
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    F.STATE["latency"] = old[0] if old[0] is not None else 0.005
    if old[1] is None:
        F.STATE.pop("models", None)
    else:
        F.STATE["models"] = old[1]


def _blind_files(out):
    """Everything blind: the report, its CSVs, and each run's invalid.json (what the report and the CLI read)."""
    files = list(out.glob("*-blind.*")) + list(out.glob("runs/*/invalid.json"))
    assert files
    return {f.name: f.read_text() for f in files}


def test_an_invalid_model_run_names_no_model_in_anything_blind(slow_fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    brain = {"id": BRAIN, "label": LABEL, "base_url": slow_fake, "model": MODEL, "max_concurrency": 4,
             "timeout": 0.05, "max_tokens": 100}
    proto = {"name": "blind", "arms": [{"name": ARM, "brain": BRAIN}, {"name": "baseline"}], "allow_models": True,
             "brains": {BRAIN: brain}, "seeds": [3], "days": 1, "size": 64, "population": 4}
    (tmp_path / "p.json").write_text(json.dumps(proto))
    out = tmp_path / "out"
    assert lab_main(["run", str(tmp_path / "p.json"), "--out", str(out), "--jobs", "2"]) == 3
    cli = capsys.readouterr()
    assert "brain_unavailable" in cli.err
    report.write_pack(out)
    secrets = (LABEL, MODEL, BRAIN, ARM, slow_fake, slow_fake.split("//")[1])
    for where, text in {"cli": cli.out + cli.err, **_blind_files(out)}.items():
        for s in secrets:
            assert s not in text, f"{s!r} in {where}"
    bad = json.loads(next(out.glob("runs/*/invalid.json")).read_text())
    assert bad["kind"] == "brain_unavailable" and "12 requests failed in a row" in bad["what"]
    assert bad["what"].startswith(f"arm {bad['label']}")  # (named by its blind label instead)
    # the raw record is kept, sealed, and only the unblinded report shows it
    sealed = json.loads(next(out.glob("runs/*/invalid-sealed.json")).read_text())
    assert sealed["arm"] == ARM and sealed["brain"] == BRAIN and LABEL in sealed["what"]
    assert all("Timeout" in (c["error"] or "") for c in sealed["last_calls"])
    assert LABEL in report.write_pack(out, unblind=True).read_text()


def test_every_break_is_kept_however_many(tmp_path, monkeypatch):
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick >= TICKS_PER_DAY:
            found += [{"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": f"c{i} holds -1 wood"}
                      for i in range(25)]
        return found

    monkeypatch.setattr(INV, "check", fake)
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "many", "arms": [{"name": "p"}, {"name": "q"}], "seeds": [3], "days": 2,
                                     "size": 64, "population": 4})
    run.run(spec, tmp_path)
    for rd in (tmp_path / "runs").glob("*_*"):
        bad = json.loads((rd / "invalid.json").read_text())
        sealed = json.loads((rd / "invalid-sealed.json").read_text())
        assert bad["breaks"] == 25 and bad["by_kind"] == {"negative_stock": 25}
        assert len(sealed["broken"]) == 25 and sealed["broken"][-1]["what"] == "c24 holds -1 wood"
