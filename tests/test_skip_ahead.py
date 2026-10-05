"""⏩ Skip ahead: run the worlds forward at full speed until the next discovery, the next big moment or N days, then
go back to the speed the game had. It is the same stepping through the same Mind (so the same world comes out), it
stops at once on a storage error, and an experiment refuses it."""

import asyncio
import os
import sqlite3
import time

import pytest

from chits.runtime import Runtime
from chits.sim.agent import TICKS_PER_DAY


@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")  # the game stands still unless it is skipping
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_MODE", "versus")
    return tmp_path


def client():
    from fastapi.testclient import TestClient

    from chits.app import app

    return TestClient(app)


def rt():
    from chits.app import R

    return R()


def finished(r, timeout=180.0):
    """Wait for the running skip to end; returns how it ended."""
    end = time.time() + timeout
    while r.skip is not None and time.time() < end:
        time.sleep(0.02)
    assert r.skip is None, "the skip did not end"
    time.sleep(0.2)  # (this thread may see the skip end while the loop is still inside that last step)
    return r.last_skip


def ticks(r):
    return {wid: w.tick for wid, w in r.worlds.items()}


def stands_still(r):
    time.sleep(0.15)  # (a step that was under way when the request was answered may still finish)
    before = ticks(r)
    time.sleep(0.3)
    return ticks(r) == before


def test_skipping_a_day_runs_exactly_a_day_and_goes_back_to_the_speed_it_had(env):
    with client() as c:
        r = rt()
        assert stands_still(r) and c.get("/api/health").json()["control"]["skip"] is None
        state = c.post("/api/skip", json={"until": "days", "days": 1})
        assert state.status_code == 200
        assert state.json()["skip"]["until"] == "days" and state.json()["skip"]["from_day"] == 1
        last = finished(r)
        assert ticks(r) == {"A": TICKS_PER_DAY, "B": TICKS_PER_DAY}
        assert (last["reason"], last["ticks"], last["from_day"], last["day"]) == ("days", TICKS_PER_DAY, 1, 2)
        control = c.get("/api/health").json()["control"]
        assert (control["speed"], control["paused"], control["skip"]) == (0, False, None)
        assert control["last_skip"]["reason"] == "days" and stands_still(r)
        # a skip is play, not meddling: nothing is marked, but the run's record says which stretch was skipped
        run = c.get("/api/run").json()
        assert run["sandbox_modified"] is False
        assert run["skips"] == [{"from_tick": 0, "to_tick": TICKS_PER_DAY, "until": "days", "reason": "days"}]

        # a paused game is paused again afterwards
        assert c.post("/api/control", json={"paused": True}).json()["paused"] is True
        assert c.post("/api/skip", json={"until": "days", "days": 1}).json()["paused"] is False
        assert finished(r)["reason"] == "days" and r.paused is True
        assert ticks(r) == {"A": 2 * TICKS_PER_DAY, "B": 2 * TICKS_PER_DAY}


def test_a_skipped_day_is_the_same_day_as_one_played_step_by_step(env, tmp_path):
    async def skip_a_day(r):
        loop = asyncio.create_task(r._loop())
        r.start_skip("days", 1)
        while r.skip is not None:
            await asyncio.sleep(0.01)
        loop.cancel()

    def picture(r):
        return {wid: (w.tick, w.to_dict()["rng_state"], w.to_dict().get("rng_tick"), w.stats(), sorted(w.first),
                      [(a.id, a.x, a.y, round(a.hunger, 6), a.activity) for a in w.agents.values()])
                for wid, w in r.worlds.items()}

    skipped, played = Runtime(tmp_path / "skipped"), Runtime(tmp_path / "played")
    try:
        asyncio.run(skip_a_day(skipped))
        for _ in range(TICKS_PER_DAY):
            played.step_worlds()
            for w in played.worlds.values():
                played._maybe_save(w)
        assert picture(skipped) == picture(played)
        assert skipped.speed == played.speed and skipped.paused == played.paused
    finally:
        for r in (skipped, played):
            r.store.db.close()
            asyncio.run(r.mind.close())


def test_skipping_to_the_next_discovery_stops_on_the_tick_it_is_made(env):
    with client() as c:
        r = rt()
        known = {wid: set(w.first) for wid, w in r.worlds.items()}
        assert c.post("/api/skip", json={"until": "discovery"}).status_code == 200
        last = finished(r)
        assert last["reason"] == "found" and last["text"]
        new = {wid: set(w.first) - known[wid] for wid, w in r.worlds.items()}
        assert any(new.values())
        for wid, keys in new.items():
            for k in keys:  # made on the very step the skip stopped at
                assert r.worlds[wid].tick - r.worlds[wid].first[k]["tick"] <= 1
        assert stands_still(r)


def test_skipping_to_the_next_big_moment_stops_at_an_importance_5_event_only(env, tmp_path):
    r = Runtime(tmp_path)
    try:
        w = r.worlds["B"]
        r.start_skip("moment")
        w.emit("birth", "A child was born", 4)
        r._skip_check()
        assert r.skip is not None
        w.emit("law", "The village passed its first law", 5)
        r._skip_check()
        assert r.skip is None
        assert (r.last_skip["reason"], r.last_skip["text"]) == ("found", "The village passed its first law")
        # and with nothing to find it gives up after SKIP_MAX_DAYS
        r.start_skip("discovery")
        for x in r.worlds.values():
            x.tick += r.SKIP_MAX_DAYS * TICKS_PER_DAY
        r._skip_check()
        assert r.skip is None and r.last_skip["reason"] == "limit"
    finally:
        r.store.db.close()
        asyncio.run(r.mind.close())


def test_a_skip_stops_at_once_when_the_game_cannot_be_saved(env, monkeypatch):
    with client() as c:
        r = rt()

        def boom(*args, **kwargs):
            raise OSError("disk full")

        real = r.store.save_world
        monkeypatch.setattr(r.store, "save_world", boom)
        assert c.post("/api/skip", json={"until": "days", "days": 5}).status_code == 200
        last = finished(r)
        assert last["reason"] == "storage" and "disk full" in last["text"]
        assert ticks(r) == {"A": 5, "B": 5}  # the first checkpoint of the skip failed: not one tick more
        assert r.paused is True and r.save_errors and stands_still(r)
        got = c.post("/api/skip", json={"until": "days", "days": 1})
        assert got.status_code == 409 and "storage error" in got.json()["detail"]
        monkeypatch.setattr(r.store, "save_world", real)
        assert c.post("/api/save").status_code == 200 and not r.save_errors

        # a write that normal play only logs (a replay keyframe) stops a skip too, and the game is left as it was
        r.paused = False

        def locked(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(r.store, "save_keyframe", locked)
        assert c.post("/api/skip", json={"until": "days", "days": 5}).status_code == 200
        last = finished(r)
        assert last["reason"] == "storage" and "database is locked" in last["text"]
        assert r.paused is False and stands_still(r) and ticks(r) == {"A": 24, "B": 24}  # (the step it failed in)


def test_stop_and_the_speed_buttons_end_a_skip(env):
    with client() as c:
        r = rt()
        c.post("/api/skip", json={"until": "days", "days": 30})
        assert r.skip is not None
        again = c.post("/api/skip", json={"until": "days", "days": 1})
        assert again.status_code == 409 and "already skipping" in again.json()["detail"]
        stopped = c.post("/api/skip/stop").json()
        assert stopped["skip"] is None and stopped["last_skip"]["reason"] == "stopped" and stands_still(r)
        assert c.post("/api/skip/stop").status_code == 200  # (nothing to stop is not an error)

        c.post("/api/skip", json={"until": "moment"})
        paused = c.post("/api/control", json={"paused": True}).json()
        assert paused["skip"] is None and paused["paused"] is True and stands_still(r)
        c.post("/api/skip", json={"until": "days", "days": 30})
        assert c.post("/api/control", json={"speed": 0}).json()["skip"] is None and stands_still(r)

        for body in ({"until": "tomorrow"}, {"until": "days"}, {"until": "days", "days": 0},
                     {"until": "days", "days": 31}):
            assert c.post("/api/skip", json=body).status_code == 400, body
        assert r.skip is None


def test_an_experiment_run_refuses_to_skip_and_says_why(env, monkeypatch):
    with client() as c:
        r = rt()
        r.contract = "experiment"
        try:
            got = c.post("/api/skip", json={"until": "days", "days": 1})
            assert got.status_code == 409 and "experiment" in got.json()["detail"] and "instinct" in got.json()["detail"]
            assert c.post("/api/skip/stop").status_code == 409
            with pytest.raises(PermissionError):
                r.start_skip("days", 1)
            assert r.skip is None and stands_still(r) and ticks(r) == {"A": 0, "B": 0}
        finally:
            r.contract = "play"
        monkeypatch.setenv("CHITS_TOKEN", "sesame-for-this-test")
        assert c.post("/api/skip", json={"until": "days", "days": 1}).status_code == 401 and r.skip is None
        monkeypatch.delenv("CHITS_TOKEN")
