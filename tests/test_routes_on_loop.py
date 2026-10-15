"""Every route that reads or changes the live worlds runs on the loop (`async def`), between two steps. A plain `def`
route runs in a worker thread while the loop steps the worlds: /api/why walked a world's buildings mid-step and
answered 500 "dictionary changed size during iteration" (live, 2026-10-15), and /api/scorecard, polled by the side
panel every 10 s, made the same walk. A route left as a thread is named here with the reason it never reads a world."""

import inspect
import re

from fastapi.routing import APIRoute, APIWebSocketRoute

from chits import app as APP

# what a route reaches the live game through: the runtime, a world, or the helpers that walk them
LIVE = re.compile(r"\bR\(\)|\bworld\(|_saves_runtime\(|_rivals_data\(|_story_inputs\(|_replay_data\(")

THREADS = {  # route name -> why it may stay a thread
    "savepoint_list": "stored save points only (the database)",
    "savepoint_delete": "deletes a stored save point (the database)",
    "saves_list": "stored save points only (the database)",
    "saves_export": "reads one stored save point and gzips it",
    "saves_delete": "deletes a stored save point (the database)",
    "decisions_jsonl": "every stored decision (the database)",
    "recorder_status": "the recorder's settings and its folder on disk (world ids only, never a world)",
    "recorder_configure": "the recorder's settings and its browser process (world ids only)",
    "recordings": "the recordings folder on disk",
    "director_cut": "encodes a week's clips with ffmpeg: never on the loop",
    "recording_file": "serves a file from the recordings folder",
}


def _routes():
    for r in APP.app.routes:
        if isinstance(r, (APIRoute, APIWebSocketRoute)) and getattr(r.endpoint, "__module__", "") == APP.__name__:
            yield r.endpoint


def test_every_route_that_reaches_the_worlds_runs_on_the_loop():
    on_thread = []
    for fn in _routes():
        if LIVE.search(inspect.getsource(fn)) and not inspect.iscoroutinefunction(fn) and fn.__name__ not in THREADS:
            on_thread.append(fn.__name__)
    assert on_thread == [], f"these routes read or change the live game from a worker thread: {on_thread}"


def test_the_routes_left_as_threads_still_exist_and_are_threads():
    names = {fn.__name__: fn for fn in _routes()}
    assert set(THREADS) <= set(names), set(THREADS) - set(names)  # (a renamed route must not keep a stale pass)
    assert not [n for n in THREADS if inspect.iscoroutinefunction(names[n])]


def test_the_check_sees_the_routes_that_walk_the_worlds():
    """The pattern must catch the way each kind of route reaches the game (or the first test passes on nothing)."""
    src = {fn.__name__: inspect.getsource(fn) for fn in _routes()}
    for name in ("scorecard", "why_slow", "lineage", "hall_of_ancestors", "story_x", "replay", "rivals", "saves_list"):
        assert LIVE.search(src[name]), name


def test_the_routes_that_read_the_database_beside_a_world_still_answer(tmp_path, monkeypatch):
    """Those now read the world on the loop and the database in a thread (app._io): each still answers."""
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from fastapi.testclient import TestClient

    with TestClient(APP.app) as c:
        APP.R().step_worlds(30)
        wid = next(iter(APP.R().worlds))
        APP.R().worlds[wid].emit("note", "a test event", 3)
        for path in (f"/api/worlds/{wid}/replay", "/api/replay/export?days=1", f"/api/worlds/{wid}/events",
                     f"/api/worlds/{wid}/decisions", f"/api/worlds/{wid}/recap", f"/api/worlds/{wid}/progress",
                     "/api/story/x", "/api/story/card.svg", f"/api/worlds/{wid}/log.txt", f"/api/worlds/{wid}/chronicle",
                     f"/api/worlds/{wid}/sagas", f"/api/worlds/{wid}/history", f"/api/worlds/{wid}/hall",
                     "/api/scorecard", "/api/brains", "/api/forks", "/api/run", "/api/health", "/api/worlds"):
            r = c.get(path)
            assert r.status_code == 200, (path, r.status_code, r.text[:200])
        assert c.get(f"/api/worlds/{wid}/events").json(), "events were flushed and read back"
        assert c.get(f"/api/worlds/{wid}/stories/1").status_code == 404
