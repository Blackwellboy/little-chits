"""A game can hold every world at fewer chits than its island allows, so the models can keep up with them. Births
pause while a world is at or over the limit; nobody is removed. Play only, the same for every world, on the record."""

import json
import os

import pytest

from chits.brain.instinct import Instinct
from chits.sim.world import POP_CAP, POP_CAP_BIG, POP_CAP_MIN, World


def _run(w, days):
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    top = len(w.agents)
    for _ in range(240 * days):
        w.step(hook)
        top = max(top, len(w.agents))
    return top


def test_a_held_world_has_no_births_over_its_limit_and_an_unheld_one_grows_past_it():
    free = World("A", "A", 7, "direct", 96, 18)
    held = World("A", "A", 7, "direct", 96, 18)
    held.cap = 20
    assert free.pop_cap() == POP_CAP and held.pop_cap() == 20 and held.island_cap() == POP_CAP
    assert _run(held, 12) <= 20
    assert _run(free, 12) > 20  # the same island without the limit: the limit is what held it


def _ages(w, ages):
    """Give the world's chits these ages in days (the youngest last)."""
    for a, d in zip(w.agents.values(), ages):
        a.born = w.tick - int(d * 240)


def test_a_world_at_or_just_over_its_limit_has_no_births_and_nobody_is_removed():
    w = World("A", "A", 3, "direct", 64, 12)
    w.tick = 240 * 60
    _ages(w, [30] * 12)
    w.cap = 8  # 12 is within half as big again as 8: nobody is born, though none of them is young
    assert not w.births_open()
    before = set(w.agents)
    for _ in range(5):
        w._births()
    assert set(w.agents) == before  # none born, none taken away
    w.cap = 12
    assert not w.births_open()  # at the limit
    w.cap = 13
    assert w.births_open()  # under it: births as ever


def test_a_world_far_over_its_limit_keeps_a_young_cohort_so_it_shrinks_instead_of_dying_out():
    # only adults under 40 days have children and a chit lives about 47: with births simply paused while 30 chits
    # became 10, the youngest would be too old by then and the world would die out
    w = World("A", "A", 3, "direct", 64, 30)
    w.tick = 240 * 60
    w.cap = 10
    _ages(w, [30] * 30)
    assert w.births_open()  # far over the limit and nobody young: children are still born
    _ages(w, [30] * 25 + [5] * 5)
    assert not w.births_open()  # five under 20 days is the cohort for a limit of 10
    _ages(w, [30] * 26 + [5] * 4)
    assert w.births_open()
    # an unheld world over its island's limit never has this exception
    w.cap = None
    assert w.births_open() == (len(w.agents) < w.island_cap())


def test_a_held_world_shrinks_to_its_limit_and_lives_on():
    w = World("A", "A", 11, "direct", 96, 30)
    w.cap = 10
    _run(w, 70)  # longer than a lifetime: every founder is gone
    n = len(w.agents)
    assert 4 <= n <= 15, n  # near its limit: neither still crowded nor died out
    assert any(not a.is_child(w.tick) and a.age(w.tick) < 40 for a in w.agents.values())  # and still able to go on


def test_the_limit_never_raises_a_world_over_its_island():
    small, big = World("A", "A", 3, "direct", 64, 4), World("A", "A", 3, "direct", 256, 4)
    assert (small.island_cap(), big.island_cap()) == (POP_CAP, POP_CAP_BIG)
    small.cap = 500
    assert small.pop_cap() == POP_CAP


def test_the_limit_is_saved_with_the_world_and_a_world_without_one_saves_as_before():
    w = World("A", "A", 3, "direct", 64, 4)
    assert "cap" not in w.to_dict()
    assert World.from_dict(json.loads(json.dumps(w.to_dict()))).cap is None
    w.cap = 20
    again = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert again.cap == 20 and again.pop_cap() == 20


@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_MODE", "versus")
    return tmp_path


def _client():
    from fastapi.testclient import TestClient

    from chits.app import app

    return TestClient(app)


def _rt():
    from chits.app import R

    return R()


def test_the_game_holds_every_world_at_the_same_limit_and_says_so_on_the_run(env):
    with _client() as c:
        r = _rt()
        assert r.control_state()["pop_cap"] == {"cap": None, "min": POP_CAP_MIN, "island": POP_CAP}
        assert c.get("/api/run").json()["sandbox_modified"] is False
        got = c.post("/api/population", json={"cap": 20})
        assert got.status_code == 200 and got.json()["pop_cap"]["cap"] == 20
        assert all(w.cap == 20 and w.pop_cap() == 20 for w in r.worlds.values()) and len(r.worlds) == 2
        run = c.get("/api/run").json()
        assert run["sandbox_modified"] is True and any("held at 20" in x for x in run["sandbox_reasons"])
        assert r.manifest()["pop_cap"] == 20
        # out of range is refused and changes nothing
        for bad in (POP_CAP_MIN - 1, POP_CAP + 1, 0):
            assert c.post("/api/population", json={"cap": bad}).status_code == 400
        assert all(w.cap == 20 for w in r.worlds.values())
        # lifted again
        assert c.post("/api/population", json={"cap": None}).json()["pop_cap"]["cap"] is None
        assert all(w.cap is None for w in r.worlds.values())


def test_an_experiment_refuses_a_change_of_limit(env):
    with _client() as c:
        c.post("/api/reset", json={"mode": "versus", "contract": "experiment"})
        r = _rt()
        assert r.contract == "experiment"
        assert c.post("/api/population", json={"cap": 20}).status_code == 409
        assert all(w.cap is None for w in r.worlds.values())


def test_a_new_game_can_start_held(env, monkeypatch):
    monkeypatch.setenv("CHITS_POP_CAP", "12")
    with _client():
        assert all(w.cap == 12 for w in _rt().worlds.values())


def test_an_experiment_never_takes_the_machines_limit(env, monkeypatch):
    monkeypatch.setenv("CHITS_POP_CAP", "12")
    with _client() as c:
        assert all(w.cap == 12 for w in _rt().worlds.values())  # a play game does
        c.post("/api/reset", json={"mode": "versus", "contract": "experiment"})
        r = _rt()
        assert r.contract == "experiment" and all(w.cap is None and w.pop_cap() == POP_CAP for w in r.worlds.values())


def test_a_limit_read_from_a_save_file_is_checked():
    base = World("A", "A", 3, "direct", 64, 4).to_dict()
    for bad in (0, -5, "20", 2.5, True, None, [20]):
        assert World.from_dict(json.loads(json.dumps(dict(base, cap=bad)))).cap is None, bad
    assert World.from_dict(json.loads(json.dumps(dict(base, cap=1)))).cap == POP_CAP_MIN  # too small: the smallest
    big = World.from_dict(json.loads(json.dumps(dict(base, cap=5000))))
    assert big.pop_cap() == POP_CAP  # above the island's own: the island's


def test_the_limit_needs_the_access_token_like_every_private_route(env, monkeypatch):
    monkeypatch.setenv("CHITS_TOKEN", "s3cret-for-this-test")
    with _client() as c:
        assert c.post("/api/population", json={"cap": 20}).status_code == 401
        assert c.post("/api/population?token=s3cret-for-this-test", json={"cap": 20}).status_code == 200
