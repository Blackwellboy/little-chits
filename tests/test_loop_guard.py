"""A thing a world cannot name must never stop it, and a step that fails must never stop the game without a word.

Live, 2026-10-04: a chit carried two of the other world's inventions (brought over on a trade voyage). They were
registered in memory only, so after a restart its world could not name them, the rule that chooses what to put down
when hands are full raised on them, and the game loop's task died: the game stood still, unpaused, with no error."""

import json
import os
import random
import time

import pytest

from chits.brain.instinct import Instinct
from chits.sim.world import World

INV = {"name": "Reed Net", "inputs": {"fiber": 2, "wood": 1}, "props": ["invented", "for fishing", "stringy"],
       "effect": {"tool": "spear", "tool_power": 1.2}}


def test_a_thing_the_world_cannot_name_gets_a_stand_in_and_nothing_fails_on_it():
    w = World("B", "B", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    d = json.loads(json.dumps(w.to_dict()))
    for ad in d["agents"]:
        if ad["id"] == a.id:
            ad["inventory"] = {"inv_a_11": 1, "inv_a_2": 1, "wood": 9, "stone": 2}
    again = World.from_dict(d)
    b = again.agents[a.id]
    assert again.unknown_things() == []  # every carried thing has a name now
    assert again.item("inv_a_11").name == "strange thing" and b._item("inv_a_2") is not None
    ins = Instinct()
    ins._world = again
    ins._declutter(again, b, random.Random(1))  # the rule that raised: what to put down when hands are full
    for _ in range(30):  # and a world with such a chit steps
        again.step(lambda world, c: None)


def test_another_worlds_invention_is_still_known_after_a_restart():
    home, away = World("A", "A", 3, "direct", 64, 3), World("B", "B", 3, "direct", 64, 3)
    traveller = next(iter(home.agents.values()))
    traveller.inventory["inv_a_1"] = 1
    away.arrive(traveller.to_dict(), "A", "A", inventions={"inv_a_1": INV})
    assert away.item("inv_a_1").name == "Reed Net" and away.item("inv_a_1").tool == "spear"
    again = World.from_dict(json.loads(json.dumps(away.to_dict())))
    assert again.item("inv_a_1").name == "Reed Net" and again.item("inv_a_1").tool == "spear"  # not a stand-in
    assert again.recipe("inv_a_1") is not None and again.unknown_things() == []
    # a world nothing foreign has reached saves as before
    assert "foreign" not in World("A", "A", 3, "direct", 64, 3).to_dict()


@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
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


def test_the_game_names_a_stand_in_again_from_the_world_that_invented_it(env, monkeypatch):
    monkeypatch.setenv("CHITS_SPEED", "0")
    with _client():
        r = _rt()
        a, b = r.worlds["A"], r.worlds["B"]
        a.inventions["inv_a_1"] = dict(INV, purpose="fishing", by="x")
        chit = next(iter(b.agents.values()))
        chit.inventory["inv_a_1"] = 1
        assert b.name_unknown_things() == ["inv_a_1"] and b.item("inv_a_1").name == "strange thing"
        assert r.mend_foreign() == ["B:inv_a_1"]
        assert b.item("inv_a_1").name == "Reed Net" and "inv_a_1" in b.foreign and not b._strange


def test_a_step_that_fails_pauses_the_game_and_says_why(env, monkeypatch):
    monkeypatch.setenv("CHITS_SPEED", "1")
    with _client() as c:
        r = _rt()
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise AttributeError("'NoneType' object has no attribute 'tool'")

        monkeypatch.setattr(r, "step_worlds", boom)
        for _ in range(600):  # (the pause comes last, after the manifest is written: wait for it, not the error)
            if r.paused:
                break
            time.sleep(0.05)
        assert r.paused and "NoneType" in r.loop_error and calls["n"] == 1  # paused at once, not retried in a spin
        assert r.control_state()["loop_error"] == r.loop_error
        monkeypatch.undo()  # the step works again: resuming clears the error and the game goes on
        os.environ["CHITS_DATA_DIR"] = str(env)
        tick = max(w.tick for w in r.worlds.values())
        assert c.post("/api/control", json={"paused": False}).status_code == 200
        for _ in range(100):
            if max(w.tick for w in r.worlds.values()) > tick:
                break
            time.sleep(0.05)
        assert not r.loop_error and max(w.tick for w in r.worlds.values()) > tick


def test_a_failed_step_ends_an_experiment_as_invalid_and_a_new_game_starts_clean(env, monkeypatch):
    # one world may have stepped before the other failed: the run can't go on as a valid comparison
    monkeypatch.setenv("CHITS_SPEED", "1")
    with _client() as c:
        c.post("/api/reset", json={"mode": "versus", "contract": "experiment"})
        r = _rt()
        assert r.contract == "experiment"
        real = r.step_worlds

        def boom():
            raise RuntimeError("world B could not step")

        monkeypatch.setattr(r, "step_worlds", boom)
        for _ in range(600):  # (the pause comes last, after the manifest is written: wait for it, not the error)
            if r.paused:
                break
            time.sleep(0.05)
        assert r.paused and "world B could not step" in r.invalid_reason
        monkeypatch.setattr(r, "step_worlds", real)
        assert c.post("/api/control", json={"paused": False}).status_code == 409  # not resumable as valid
        # a new game is a clean slate: the old failure is not shown over it
        assert c.post("/api/reset", json={"mode": "versus", "contract": "play"}).status_code == 200
        assert r.loop_error == "" and r.invalid_reason == "" and r.control_state()["loop_error"] == ""
