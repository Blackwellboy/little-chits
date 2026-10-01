import json
import time

import pytest
from fastapi.testclient import TestClient


def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)


def test_manifest_and_experiment_locks(tmp_path, monkeypatch, fake_llm_url):
    env(monkeypatch, tmp_path)
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        assert c.post("/api/brains", json={"id": "m1", "base_url": fake_llm_url}).status_code == 200
        r = c.post("/api/reset", json={"seed": 3, "mode": "versus", "brains": {"A": "m1", "B": "m1"},
                                       "contract": "experiment"})
        assert r.status_code == 200
        rt = appmod.rt
        man = c.get("/api/run").json()
        assert man["contract"] == "experiment" and man["run_id"] == rt.run_id and man["seed"] == 3
        assert man["worlds"]["A"]["brain"]["id"] == "m1" and man["worlds"]["A"]["brain"]["base_url"] == fake_llm_url
        assert man["prompt_version"] and man["sandbox_modified"] is False
        assert (tmp_path / "runs" / rt.run_id / "manifest.json").exists()
        assert c.post("/api/worlds/A/brain", json={"brain": "instinct"}).status_code == 409
        assert c.post("/api/brains", json={"id": "m1", "base_url": fake_llm_url, "temperature": 1.5}).status_code == 409
        assert c.post("/api/control", json={"pace_to_brain": False}).status_code == 409
        assert c.post("/api/reset", json={"contract": "nonsense"}).status_code == 400
        # play again: everything is allowed
        c.post("/api/reset", json={"seed": 4, "mode": "versus", "contract": "play"})
        assert c.post("/api/worlds/A/brain", json={"brain": "instinct"}).status_code == 200
        rt.mark_sandbox("test meddling")
        man = c.get("/api/run").json()
        assert man["sandbox_modified"] is True


def test_no_silent_fallback_in_experiments(tmp_path, monkeypatch):
    env(monkeypatch, tmp_path)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.mind.upsert({"id": "dead", "base_url": "http://127.0.0.1:9/v1"})
    for contract, expect_plan in (("play", True), ("experiment", False)):
        rt.reset(seed=5, mode="single", brains={"A": "dead"}, contract=contract)
        w = rt.worlds["A"]
        b = rt.mind.brains["dead"]
        b.cooldown_until = time.time() + 999  # unhealthy
        a = next(iter(w.agents.values()))
        a.plan = []
        rt.mind.hook(w, a)
        assert bool(a.plan) is expect_plan, contract
        if not expect_plan:
            assert a.plan_source == "waiting"
    with pytest.raises(ValueError):
        rt.reset(seed=6, mode="versus", contract="experiment", contact=True)


def test_unreadable_save(tmp_path, monkeypatch):
    env(monkeypatch, tmp_path)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    good = rt.worlds["A"].to_dict()
    bad = dict(good)
    bad["agents"] = "garbage"
    rt.store.save_world(bad)
    rt.store.set_meta("contract", "play")
    rt2 = Runtime(tmp_path)  # play: set aside and start fresh
    assert "A" in rt2.worlds
    n = rt2.store.db.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    assert n >= 1
    rt2.store.save_world(bad)
    rt2.store.set_meta("contract", "experiment")
    with pytest.raises(RuntimeError):
        Runtime(tmp_path)
