"""What-if forks: a copy of a world as it is now, stepping alongside it with another mind or culture, compared as the
two drift apart. Play games only; in memory; never part of the real match (no boats, fairs or relations)."""

import asyncio

import pytest


def _rt(tmp_path, monkeypatch, contract=None):
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="versus", contract=contract)
    return rt


def _close(rt):
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_a_fork_is_a_copy_that_steps_alongside_on_instinct(tmp_path, monkeypatch):
    rt = _rt(tmp_path, monkeypatch)
    wa = rt.worlds["A"]
    for a in wa.agents.values():  # the real world thinks with a model...
        a.brain = "rtx5090"
    v = rt.fork("A")
    f = rt.forks[v["id"]]["world"]
    assert v["fork"]["population"] == v["original"]["population"] and v["from_day"] == wa.day + 1
    assert set(rt.worlds) == {"A", "B"} and v["id"] not in rt.worlds  # never part of the match
    assert all(a.brain == "instinct" for a in f.agents.values()) and all(a.brain == "rtx5090" for a in wa.agents.values())
    a_id = next(iter(f.agents))
    f.agents[a_id].hunger = 1.0
    assert wa.agents[a_id].hunger != 1.0  # a copy, not the same chits
    t0 = f.tick
    rt.step_worlds(12)
    assert f.tick == t0 + 12 == wa.tick
    _close(rt)


def test_a_silent_fork_cant_talk_and_the_view_shows_what_only_one_knows(tmp_path, monkeypatch):
    rt = _rt(tmp_path, monkeypatch)
    v = rt.fork("B", culture="stigmergy")
    f = rt.forks[v["id"]]["world"]
    assert f.flags["say"] is False and rt.worlds["B"].flags["say"] is True
    a = next(iter(f.agents.values()))
    f.leader = a.id
    assert f.decree(a, "Everyone carries wood home.") is False  # (no words to decree with)
    a.learn("recipe:iron", "discovered", f.tick)
    b = next(iter(rt.worlds["B"].agents.values()))
    b.learn("recipe:glass", "discovered", rt.worlds["B"].tick)
    v = rt.fork_view(v["id"])
    assert "iron" in v["only_fork_knows"] and "glass" in v["only_original_knows"]
    _close(rt)


def test_forks_are_few_ended_on_request_gone_with_a_new_game_and_never_in_an_experiment(tmp_path, monkeypatch):
    rt = _rt(tmp_path, monkeypatch)
    ids = [rt.fork("A")["id"] for _ in range(rt.MAX_FORKS)]
    with pytest.raises(ValueError):
        rt.fork("A")
    assert rt.end_fork(ids[0]) and not rt.end_fork(ids[0]) and len(rt.forks) == 1
    with pytest.raises(ValueError):
        rt.fork("A", brain="no-such-brain")
    rt.reset(seed=6, mode="versus")
    assert rt.forks == {}
    _close(rt)
    rt = _rt(tmp_path / "x", monkeypatch, contract="experiment")
    with pytest.raises(ValueError):
        rt.fork("A")
    _close(rt)


def test_a_what_if_runs_on_instinct_and_nobody_sails_out_of_one(tmp_path, monkeypatch):
    from chits.sim import actions

    rt = _rt(tmp_path, monkeypatch)
    rt.mind.upsert({"id": "m1", "model": "fake", "base_url": "http://127.0.0.1:9/v1"})
    with pytest.raises(ValueError):
        rt.fork("A", brain="m1")  # (it would share the real match's model servers)
    v = rt.fork("A")
    f = rt.forks[v["id"]]["world"]
    t = next(iter(f.agents.values()))
    t.origin, t.voyage_intent, t.stats["boat_abroad"] = "B", "trade", 1
    assert "what-if" in actions.advance(f, t, {"do": "sail", "intent": "home"}) and t.id in f.agents
    assert v["id"] not in rt.mind.world_brain
    _close(rt)
