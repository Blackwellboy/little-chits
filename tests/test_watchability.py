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


def test_a_model_that_is_not_answering_is_instinct_too():
    t = views.thinking(_steps(fallback=15, body_reflex=10), "m1", model_up=False)
    assert t["on_instinct"] and t["why"] == "model_down" and t["fallback_pct"] == 60.0 and t["instinct_pct"] == 60.0
    # down is the brain's own health, whatever the last steps were
    assert views.thinking(_steps(model_plan=30), "m1", model_up=False)["why"] == "model_down"
    assert views.thinking(_steps(filler=5, fallback=5), "m1")["instinct_pct"] == 100.0


def test_a_slow_model_is_busy_not_missing():
    t = views.thinking(_steps(fallback=25, filler=5, body_reflex=10), "m1", model_up=True, waiting_pct=41.5)
    assert not t["on_instinct"] and t["why"] == "busy" and t["fallback_pct"] == 75.0 and t["waiting_pct"] == 41.5
    # a model that only picks from instinct's menu, or only repairs, is still deciding
    for c in ("model_choice", "model_repair"):
        t = views.thinking(_steps(fallback=30, **{c: 1}), "m1")
        assert t["why"] == "" and t["model_pct"] == round(100 / 31, 1)


def test_a_world_without_a_model_still_counts_a_voyagers_model():
    t = views.thinking(_steps(model_plan=10, instinct_plan=30), "instinct")
    assert t["on_instinct"] and t["why"] == "no_model" and t["model_pct"] == 25.0


def test_a_brain_is_up_unless_it_backs_off_or_keeps_failing():
    from types import SimpleNamespace as NS

    from chits.app import model_up

    b = lambda healthy, fails: NS(healthy=lambda: healthy, stats=NS(consecutive_fail=fails))
    assert model_up(b(True, 0)) and model_up(b(True, 2))
    assert not model_up(b(False, 0)) and not model_up(b(True, 3)) and not model_up(None)


def test_a_model_that_is_thinking_is_not_instinct():
    t = views.thinking(_steps(model_plan=3, model_choice=3, fallback=14, routine=20), "m1")
    assert t["why"] == ""
    assert not t["on_instinct"] and t["why"] == "" and t["model_pct"] == 15.0 and t["routine_pct"] == 50.0
    # too few steps to say anything: a model that has only just started is not called down
    t = views.thinking(_steps(fallback=THIN - 1), "m1")
    assert not t["on_instinct"] and t["why"] == ""
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
        rows = rt.store.life_events(w.id, a.id, views.LIFE_KINDS, 0, w.tick, epoch=w.timeline())
        assert not [r for r in rows if r["actor"] == other.id and r["kind"] == "learned"], \
            "the store reads only the events about this chit (a pupil's lesson names its teacher, but is not its moment)"
        life = views.life(a, rows)
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
        mine = views.life(other, rt.store.life_events(w.id, other.id, views.LIFE_KINDS, 0, w.tick, epoch=w.timeline()))
        assert ("birth", "child") not in [(e["kind"], e["role"]) for e in mine["events"]]
    finally:
        _close(rt)


def test_a_long_life_is_thinned_but_keeps_its_birth_and_death():
    from chits.sim.agent import Agent

    a = Agent.__new__(Agent)
    a.id, a.name, a.alive, a.born, a.died, a.cause_of_death = "a1", "Ada", False, 0, 50 * TICKS_PER_DAY, "old age"
    rows = [{"seq": 0, "tick": 0, "kind": "birth", "importance": 2, "actor": "a1", "text": "born", "data": {}}]
    rows += [{"seq": i, "tick": i, "kind": "learned" if i % 2 else "job", "importance": 2 if i % 2 else 3, "actor": "a1",
              "text": f"l{i}", "data": {"how": "taught"}} for i in range(1, 300)]
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
        t = c.get(f"/api/worlds/{wid}/progress").json()["who_thinks"]
        assert t["brain"] == "instinct" and t["on_instinct"] and t["why"] == "no_model"
        assert c.get("/api/health").json()["who_thinks"][wid]["on_instinct"]


def test_who_is_thinking_reads_the_diagnostics_recent_steps(tmp_path):
    rt, w = _rt(tmp_path)
    try:
        from chits import app as APP

        diag.of(w).recent_steps.extend(_steps(fallback=30))
        rt.mind.world_brain[w.id] = "m1"  # (no such brain: nothing answers)
        t = APP._thinking(rt, w)
        assert t["steps"] == 30 and t["why"] == "model_down"
    finally:
        _close(rt)


def _store(tmp_path):
    from chits.sim.world import Event
    from chits.store import Store

    st = Store(tmp_path / "life.db")
    ev = lambda seq, tick, kind, actor, **data: Event(seq, tick, kind, f"{kind} {seq}", 2, actor, None, None, data)
    return st, ev


def test_the_store_always_reads_a_long_lifes_birth_and_death(tmp_path):
    st, ev = _store(tmp_path)
    evs = [ev(1, 0, "birth", "a1")] + [ev(i, i, "job", "a1") for i in range(2, 500)] + [ev(500, 500, "death", "a1")]
    st.append_events("A", evs)
    rows = st.life_events("A", "a1", views.LIFE_KINDS, 0, 500, limit=10)
    kinds = [r["kind"] for r in rows]
    assert kinds[0] == "birth" and kinds[-1] == "death", "the newest `limit` rows alone lost the birth"
    assert len(rows) == 11 and [r["seq"] for r in rows] == sorted(r["seq"] for r in rows)
    st.db.close()


def test_the_store_reads_mentions_only_within_the_life_and_nothing_past_the_checkpoint(tmp_path):
    st, ev = _store(tmp_path)
    st.append_events("A", [ev(1, 100, "built", "b", builders=["b", "a1"]),   # in its life: its moment
                           ev(2, 900, "built", "b", builders=["b", "a1"]),   # after it died: not read
                           ev(3, 50, "birth", "kid", parents=["a1", "c"]),   # before it was born: not read
                           ev(4, 120, "learned", "b", source="a1"),          # names it, but is another's lesson
                           ev(5, 130, "job", "a1"), ev(6, 140, "job", "a1")])
    rows = st.life_events("A", "a1", views.LIFE_KINDS, 60, 800)
    assert [r["seq"] for r in rows] == [1, 5, 6]
    assert [r["seq"] for r in st.life_events("A", "a1", views.LIFE_KINDS, 60, 800, max_seq=5)] == [1, 5]
    plan = " ".join(str(r) for r in st.db.execute(
        "EXPLAIN QUERY PLAN SELECT seq FROM events WHERE world_id='A' AND actor='a1' AND kind IN ('job') ORDER BY seq DESC"))
    assert "events_by_actor" in plan, plan
    st.db.close()


def test_the_life_endpoint_never_checkpoints_and_sees_what_is_not_stored_yet(tmp_path, monkeypatch):
    import inspect

    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits import app as APP

    assert inspect.iscoroutinefunction(APP.chit_life), "it reads the world on the game's loop, between steps"
    with TestClient(APP.app) as c:
        rt = APP.R()
        w = next(iter(rt.worlds.values()))
        a = next(iter(w.agents.values()))

        calls = []
        real = rt._checkpoint
        monkeypatch.setattr(rt, "_checkpoint", lambda *x, **k: (calls.append(x), real(*x, **k))[1])
        w.emit("invention", f"{a.name} invented a thing", 5, a.id, 1, 1)
        life = c.get(f"/api/worlds/{w.id}/chits/{a.id}/life").json()
        assert calls == [], "the Life tab checkpointed the world"
        assert any(e["kind"] == "invention" for e in life["events"]), "an event not yet stored is read from memory"
