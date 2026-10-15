"""Watching aids (display only): who is thinking for a world."""

import asyncio

from chits import diag, views
from chits.sim.agent import TICKS_PER_DAY


def _steps(**by):
    return [{"provenance": c} for c, n in by.items() for _ in range(n)]


def test_a_world_with_no_model_runs_on_instinct():
    t = views.thinking(_steps(instinct_plan=5, body_reflex=5), "instinct")
    assert t["on_instinct"] and t["why"] == "no_model"
    assert t["model_pct"] == 0.0 and t["instinct_pct"] == 50.0 and t["body_pct"] == 50.0 and t["steps"] == 10


def test_a_model_that_only_ever_falls_back_is_instinct_too():
    t = views.thinking(_steps(fallback=15, body_reflex=10), "m1")
    assert t["on_instinct"] and t["why"] == "model_down" and t["fallback_pct"] == 60.0


def test_a_model_that_is_thinking_is_not_instinct():
    t = views.thinking(_steps(model_plan=3, model_choice=3, fallback=14, routine=20), "m1")
    assert not t["on_instinct"] and t["why"] == "" and t["model_pct"] == 15.0 and t["routine_pct"] == 50.0
    # too few steps to say anything: a model that has only just started is not called down
    t = views.thinking(_steps(fallback=THIN - 1), "m1")
    assert not t["on_instinct"]
    # body reflexes and upkeep alone are not instinct standing in for the model
    assert not views.thinking(_steps(body_reflex=40, routine=40), "m1")["on_instinct"]
    e = views.thinking([], "m1")
    assert e["steps"] == 0 and e["model_pct"] is None and not e["on_instinct"]


THIN = views.THINKING_MIN_STEPS


def _rt(tmp_path):
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    return rt, next(iter(rt.worlds.values()))


def _close(rt):
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_who_is_thinking_is_served(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        wid = c.get("/api/worlds").json()[0]["id"]
        t = c.get(f"/api/worlds/{wid}/progress").json()["thinking"]
        assert t["brain"] == "instinct" and t["on_instinct"] and t["why"] == "no_model"
        assert c.get("/api/health").json()["thinking"][wid]["on_instinct"]


def test_who_is_thinking_reads_the_diagnostics_recent_steps(tmp_path):
    rt, w = _rt(tmp_path)
    try:
        from chits import app as APP

        diag.of(w).recent_steps.extend(_steps(fallback=30))
        rt.mind.world_brain[w.id] = "m1"
        t = APP._thinking(rt, w)
        assert t["steps"] == 30 and t["why"] == "model_down"
    finally:
        _close(rt)
