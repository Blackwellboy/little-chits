"""Watching aids (display only): who is thinking for a world, and a chit's life story from the recorded events."""

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


def test_a_life_story_holds_the_chits_own_moments_its_childrens_births_and_its_death(tmp_path):
    rt, w = _rt(tmp_path)
    try:
        a, b, other = list(w.agents.values())[:3]
        w.learned(a, "recipe:cord", "discovered")
        w.learned(other, "recipe:cord", "taught", a)
        w.learned(a, "recipe:sharp_stone", "taught", other)
        w.emit("birth", f"Kid was born to {a.name} and {b.name}", 4, "a9999", 1, 1, parents=[a.id, b.id])
        w.emit("built", f"{other.name} built a hut", 2, other.id, 1, 1, builders=[other.id, a.id])
        w.emit("speech", f"{a.name} said hello", 1, a.id, 1, 1)  # (not a life event)
        w.tick += 3 * TICKS_PER_DAY
        w.kill(a, "old age")
        rt._flush_events(w)
        life = views.life(a, rt.store.life_events(w.id, a.id, views.LIFE_KINDS, epoch=w.timeline()))
        kinds = [(e["kind"], e["role"]) for e in life["events"]]
        assert ("discovery", "self") in kinds and ("birth", "child") in kinds and ("built", "helped") in kinds
        assert kinds[-1] == ("death", "self") and life["died_day"] == 4 and not life["alive"] and life["cause"]
        assert "speech" not in {k for k, _ in kinds}
        assert [e.get("what") for e in life["events"] if e["kind"] == "learned"] == ["sharp stone"]
        assert not [e for e in life["events"] if e["text"].startswith(other.name) and e["kind"] == "learned"], \
            "another chit learning from it is that chit's moment, not this one's"
        days = [e["day"] for e in life["events"]]
        assert days == sorted(days)
        # another chit's story has none of it
        mine = views.life(other, rt.store.life_events(w.id, other.id, views.LIFE_KINDS, epoch=w.timeline()))
        assert ("birth", "child") not in [(e["kind"], e["role"]) for e in mine["events"]]
    finally:
        _close(rt)


def test_a_long_life_is_thinned_but_keeps_its_birth_and_death():
    from chits.sim.agent import Agent

    a = Agent.__new__(Agent)
    a.id, a.name, a.alive, a.born, a.died, a.cause_of_death = "a1", "Ada", False, 0, 50 * TICKS_PER_DAY, "old age"
    rows = [{"seq": 0, "tick": 0, "kind": "birth", "importance": 2, "actor": "a1", "text": "born", "data": {}}]
    rows += [{"seq": i, "tick": i, "kind": "learned", "importance": 2, "actor": "a1", "text": f"l{i}", "data": {"how": "taught"}}
             for i in range(1, 300)]
    rows += [{"seq": 300, "tick": 300, "kind": "invention", "importance": 5, "actor": "a1", "text": "inv", "data": {}},
             {"seq": 301, "tick": 301, "kind": "death", "importance": 1, "actor": "a1", "text": "died", "data": {}}]
    life = views.life(a, rows, limit=20)
    ev = life["events"]
    assert len(ev) == 20 and life["thinned"]
    assert ev[0]["kind"] == "birth" and ev[-1]["kind"] == "death" and "invention" in [e["kind"] for e in ev]
    assert [e["seq"] for e in ev] == sorted(e["seq"] for e in ev)
    assert not views.life(a, rows[:5], limit=20)["thinned"]


def test_the_life_endpoint_and_who_is_thinking_are_served(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        wid = c.get("/api/worlds").json()[0]["id"]
        aid = c.get(f"/api/worlds/{wid}/agents").json()[0]["id"]
        life = c.get(f"/api/worlds/{wid}/chits/{aid}/life").json()
        assert life["id"] == aid and life["alive"] and isinstance(life["events"], list)
        assert c.get(f"/api/worlds/{wid}/chits/nobody/life").status_code == 404
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
