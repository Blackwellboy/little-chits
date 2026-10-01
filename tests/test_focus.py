"""Stop the waiting, and spend the model where it matters: a slow model is asked for a chit's next plan two steps before
the current one runs out, and (a brain's "focus", play games only) a plan that is only eating, sleeping or hauling is
left to instinct instead of queueing for the model."""

from chits import diag
from chits.brain.mind import Mind
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def _setup(focus=True, latency_ms=500.0):
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 90.0
    w.tick = TICKS_PER_DAY + 60
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "focus": focus})
    m.assign(w, "test")
    b = m.brains["test"]
    b.stats.latency_ms_avg = latency_ms
    asked = []
    m._ask = lambda world, agent, brain: asked.append(agent.id)
    return w, a, m, b, asked


def test_a_slow_model_is_asked_two_steps_ahead():
    w, a, m, b, asked = _setup(latency_ms=500.0)
    assert m.lead(b) == 1
    a.plan = [{"do": "rest"}, {"do": "rest"}]
    m.hook(w, a)
    assert asked == []  # a quick model: on the last step, as before
    a.plan = [{"do": "rest"}]
    m.hook(w, a)
    assert asked == [a.id]
    w, a, m, b, asked = _setup(latency_ms=12700.0)  # the 5090's median reply
    assert m.lead(b) == 2
    a.plan = [{"do": "rest"}, {"do": "rest"}]
    m.hook(w, a)
    assert asked == [a.id]
    a.plan = [{"do": "rest", "_filler": True}, {"do": "rest", "_filler": True}]
    asked.clear()
    m.hook(w, a)
    assert asked == []  # instinct filling in while it thinks: not a plan to ask ahead of


def test_eating_is_left_to_instinct_and_the_rest_goes_to_the_model():
    w, a, m, b, asked = _setup()
    a.hunger = 15.0
    a.inventory["berries"] = 6
    a.plan = []
    m.hook(w, a)
    assert asked == [] and a.plan_source == "instinct-routine" and {s["do"] for s in a.plan} & {"eat"}
    assert diag.of(w).plans["routine"] == 1
    w2, a2, m2, b2, asked2 = _setup()
    a2.inventory.clear()
    a2.plan = []
    m2.hook(w2, a2)
    assert asked2 == [a2.id]  # fed and rested: whatever it does next is the model's call


def test_no_focus_and_no_focus_in_an_experiment():
    for focus, strict in ((False, False), (True, True)):
        w, a, m, b, asked = _setup(focus=focus)
        m.strict = strict
        a.hunger = 15.0
        a.inventory["berries"] = 6
        a.plan = []
        m.hook(w, a)
        assert asked == [a.id] and a.plan_source != "instinct-routine", (focus, strict)


def test_the_models_share_is_of_the_plans_that_werent_routine(tmp_path):
    import asyncio

    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    diag.of(w).plans.update({"model": 7, "filler": 3, "routine": 30})
    wd = diag.report(rt)["worlds"][w.id]
    assert wd["model_share_pct"] == 70.0 and wd["routine_pct"] == 75.0
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_the_focus_setting_is_saved_from_the_brains_panel(tmp_path, monkeypatch):
    """(The review found the checkbox did nothing: the API dropped the field.)"""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        assert c.post("/api/brains", json={"id": "m1", "base_url": "http://127.0.0.1:9/v1", "focus": False}).status_code == 200
        b = next(x for x in c.get("/api/brains").json()["brains"] if x["config"]["id"] == "m1")
        assert b["config"]["focus"] is False
