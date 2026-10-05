"""Model-led play (docs/MODEL_LED.md): the model supplies the intelligence and the chit keeps its body. A model's chits
get no instinct plans, filler, fallback, duty or routine; the body's reflexes and the executor stay; a model that is
down leaves its chits finishing their plan, then waiting visibly, never on instinct."""

import time

import pytest

from chits import diag
from chits.brain.mind import Mind
from chits.sim import actions
from chits.sim.world import World

INSTINCT_ORIGINS = {"instinct", "fallback", "filler", "duty", "routine", "shed"}


def _setup(led=True, focus=False):
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.plan = []
    m = Mind(None)
    m.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1", "focus": focus})
    m.assign(w, "m")
    m.model_led = led
    m._spawn = lambda coro: coro.close()  # (the model never answers)
    return w, a, m


def _instinct_steps(a):
    return [s for s in a.plan if s.get("_origin") in INSTINCT_ORIGINS or s.get("_filler")]


@pytest.mark.parametrize("led", [True, False])
def test_while_the_model_thinks_its_chit_waits_instead_of_getting_filler(led):
    w, a, m = _setup(led)
    for _ in range(m.patience_ticks + 5):
        m.hook(w, a)
        w.tick += 1
    assert a.thinking
    assert (not _instinct_steps(a)) is led  # (without model-led, instinct fills in while it thinks)
    if led:
        assert a.activity == "waiting for its mind" and a.plan_source == "waiting"


@pytest.mark.parametrize("led", [True, False])
def test_a_mind_that_is_down_leaves_its_chit_finishing_its_plan_then_waiting(led):
    w, a, m = _setup(led)
    b = m.brains["m"]
    b.cooldown_until = time.monotonic() + 600  # the model is down
    own = [{"do": "gather", "what": "wood", "qty": 1, "_origin": "model_generated"}]
    a.plan = [dict(s) for s in own]
    m.hook(w, a)
    assert a.plan[0]["_origin"] == "model_generated"  # its own plan runs on
    a.plan = []
    m.hook(w, a)
    if led:
        assert not a.plan and a.plan_source == "waiting" and a.activity == "its mind is unavailable"
    else:
        assert _instinct_steps(a)  # (play without model-led: instinct stands in)
    assert diag.of(w).unavailable_ticks == 2


def test_the_body_keeps_its_reflexes_under_model_led():
    w, a, m = _setup(True)
    a.hunger = 5.0
    a.inventory["berries"] = 3
    a.plan = [{"do": "gather", "what": "wood", "qty": 5, "_origin": "model_generated"}]
    meals = a.stats.get("meals", 0)
    for _ in range(60):
        w.step(m.hook)
        if a.stats.get("meals", 0) > meals:
            break
    assert a.stats.get("meals", 0) > meals  # it ate: a reflex, not an instinct plan
    assert not _instinct_steps(a)  # (eating what it carries is the body acting at once, with no plan)


def test_no_routine_without_asking_the_model_under_model_led():
    for led in (True, False):
        w, a, m = _setup(led, focus=True)
        a.energy = 3.0  # (instinct's next plan would be routine: sleep)
        m.hook(w, a)
        assert (a.plan_source != "instinct-routine") is led


def test_switching_model_led_on_drops_instincts_plans_and_keeps_the_body_and_the_model():
    w, a, m = _setup(False)
    others = [o for o in w.agents.values() if o is not a]
    a.plan = [{"do": "eat", "_reflex": True}, {"do": "gather", "what": "wood", "_origin": "instinct"},
              {"do": "rest", "_filler": True, "_origin": "filler"}]
    others[0].plan = [{"do": "gather", "what": "stone", "_origin": "model_selected"},
                      {"do": "build", "what": "hut", "_origin": "model_generated"}]
    m.model_led = True
    dropped = m.start_model_led(w)
    assert dropped == 2 and a.plan == [{"do": "eat", "_reflex": True}]
    assert [s["_origin"] for s in others[0].plan] == ["model_selected", "model_generated"]
    assert diag.of(w).model_led_since == w.tick and diag.of(w).model_led_dropped == 2
    # a chit that comes under a model later is cleaned before it acts
    m.assign(w, "instinct", [a.id])
    a.plan = [{"do": "gather", "what": "clay", "_origin": "instinct"}]
    m.assign(w, "m", [a.id])
    assert a.plan == []
    # ... and one made model-driven any other way (a voyager taking its new home's brain), by the tick hook
    b = others[1]
    b.brain = "instinct"
    m.hook(w, b)
    b.plan = [{"do": "gather", "what": "reeds", "_origin": "instinct"}]
    b.brain = "m"
    m.hook(w, b)
    assert not _instinct_steps(b)


def _game(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)


def test_the_game_keeps_model_led_records_it_and_an_experiment_refuses_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    _game(tmp_path, monkeypatch)
    from chits.app import R, app

    with TestClient(app) as c:
        r = R()
        assert r.mind.model_led is False
        assert c.post("/api/model-led", json={"on": True}).json()["model_led"] is True
        assert r.store.get_meta("model_led") == "1" and r.manifest()["model_led"] is True
        assert c.post("/api/reset", json={"seed": 5, "chits": 4, "size": 64}).status_code == 200
        assert r.mind.model_led is True  # (a new game that doesn't say keeps the game's choice)
        assert c.post("/api/reset", json={"seed": 5, "chits": 4, "size": 64, "model_led": False}).status_code == 200
        assert r.mind.model_led is False and r.store.get_meta("model_led") == "0"
        assert c.post("/api/reset", json={"seed": 5, "chits": 4, "size": 64, "model_led": True,
                                          "contract": "experiment"}).status_code == 200
        assert r.mind.model_led is False  # (an experiment is stricter already)
        assert c.post("/api/model-led", json={"on": True}).status_code == 409


def test_a_scripted_model_led_run_takes_no_step_from_instinct():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "harness"))
    from mindrun import run_world

    w, p, mp, low, report = run_world(42, 4, size=96, chits=10, mind="scripted", model_led=True)
    srcs = diag.of(w).step_sources
    assert not {k: n for k, n in srcs.items() if k in INSTINCT_ORIGINS and n}, dict(srcs)
    assert srcs.get("reflex", 0) > 0 and sum(n for k, n in srcs.items() if str(k).startswith("model")) > 0


def test_switching_model_led_on_keeps_a_model_plan_already_waiting():
    """Codex on #140: the switch bumped the chit's revision, so a plan the model had already returned was then
    thrown away as stale."""
    w, a, m = _setup(False)
    m.hook(w, a)  # asks its model
    rec = a._decision
    a.pending_plan = {"goal": "wood", "thought": "", "steps": [{"do": "gather", "what": "wood", "qty": 1}]}
    rec["parse"] = "ok"
    a.thinking = False
    m.model_led = True
    m.start_model_led(w)
    m.hook(w, a)
    assert a.plan and a.plan[0]["what"] == "wood" and a.plan[0]["_origin"] == "model_generated"
    assert rec["outcome"] == "adopted"


def test_a_reset_keeping_an_experiment_never_turns_model_led_on(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    _game(tmp_path, monkeypatch)
    from chits.app import R, app

    with TestClient(app) as c:
        r = R()
        assert c.post("/api/reset", json={"seed": 5, "chits": 4, "size": 64, "contract": "experiment"}).status_code == 200
        assert c.post("/api/reset", json={"seed": 6, "chits": 4, "size": 64, "model_led": True}).status_code == 200
        assert r.contract == "experiment" and r.mind.model_led is False


def test_the_harness_refuses_both_modes_at_once():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "tools" / "harness" / "run.py"), "3", "--days", "1", "--mind",
                        "scripted", "--model-led", "--model-only"], capture_output=True, text=True)
    assert r.returncode != 0 and "pick one" in r.stderr
