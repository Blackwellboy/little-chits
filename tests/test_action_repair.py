"""Bounded action repair (research plan item 40): a model's step fails, the simulator's exact reason goes back to the
same model once, in its next request, and both attempts are on record. On in play; in an experiment only when its
protocol declares it. Nothing judges the plan."""

import asyncio

from chits.brain import prompt as P
from chits.brain.mind import STALE_TICKS, Mind
from chits.sim import actions
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def setup():
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 90.0
    w.tick = TICKS_PER_DAY + 60
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1"})
    m.assign(w, "test")
    asked = []
    m._spawn = lambda coro: coro.close()
    m._think = lambda world, agent, brain, at_send, rec, sent: asked.append((sent["msgs"], rec, at_send)) or asyncio.sleep(0)
    return w, a, m, m.brains["test"], asked


def fail_step(w, a, origin="model_generated", decision="d1"):
    a.plan = [{"do": "craft", "what": "no_such_thing", "_origin": origin, "_decision_id": decision},
              {"do": "gather", "what": "wood", "qty": 2, "_origin": origin}]
    for _ in range(50):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    assert a.last_result.startswith("Could not craft"), a.last_result


def test_a_failed_model_step_is_noted_for_its_model_with_the_exact_reason():
    w, a, m, b, asked = setup()
    fail_step(w, a)
    rep = a.__dict__["_repair"]
    assert rep["failed"].startswith("craft") and rep["reason"] in a.last_result
    assert rep["decision_id"] == "d1" and rep["dropped"] and rep["dropped"][0].startswith("gather")


def test_only_the_models_own_first_attempt_is_repaired():
    for origin in ("model_repaired", "instinct", "routine", "duty"):
        w, a, m, b, asked = setup()
        fail_step(w, a, origin=origin)
        assert "_repair" not in a.__dict__, origin
    w, a, m, b, asked = setup()
    fail_step(w, a, origin="model_selected")
    assert "_repair" in a.__dict__


def test_the_next_request_carries_the_reason_once_and_is_recorded_as_a_repair():
    w, a, m, b, asked = setup()
    fail_step(w, a)
    m._ask(w, a, b)
    msgs, rec, at_send = asked[-1]
    assert "YOUR PLAN FAILED" in msgs[-1]["content"] and a.__dict__.get("_repair") is None
    assert "YOUR PLAN FAILED" in at_send()[-1]["content"]  # the scene rebuilt when the request goes out keeps it
    assert len([x for x in msgs if x["role"] == "user"]) == 1  # added to the scene, not a second user turn
    assert rec["style"] == "repair" and rec["repair_of"] == "d1" and rec["repair_step"].startswith("craft")
    assert rec["repair_reason"] and rec["repair_reason"] in a.last_result
    a.thinking = False
    m._ask(w, a, b)  # bounded: the next request is an ordinary one
    msgs, rec, _ = asked[-1]
    assert "YOUR PLAN FAILED" not in msgs[-1]["content"] and rec.get("style") != "repair"


def test_a_stale_note_is_dropped():
    w, a, m, b, asked = setup()
    fail_step(w, a)
    w.tick += STALE_TICKS + 1
    m._ask(w, a, b)
    assert "YOUR PLAN FAILED" not in asked[-1][0][-1]["content"] and "_repair" not in a.__dict__


def test_experiments_repair_only_when_declared():
    for repair, expect in ((None, False), (True, True), (False, False)):
        w, a, m, b, asked = setup()
        m.strict, m.repair = True, repair
        fail_step(w, a)
        m._ask(w, a, b)
        assert ("YOUR PLAN FAILED" in asked[-1][0][-1]["content"]) is expect, repair
    w, a, m, b, asked = setup()
    m.repair = False  # play can switch it off too
    fail_step(w, a)
    m._ask(w, a, b)
    assert "YOUR PLAN FAILED" not in asked[-1][0][-1]["content"]


def test_a_repaired_plan_is_adopted_as_such_and_gets_no_second_repair():
    w, a, m, b, asked = setup()
    fail_step(w, a)
    m._ask(w, a, b)
    rec = asked[-1][1]
    a.thinking = False
    a.plan = []
    a.pending_plan = {"goal": "g", "thought": "t", "steps": [{"do": "craft", "what": "no_such_thing"}]}
    m.hook(w, a)
    assert a.plan and a.plan[0]["_origin"] == "model_repaired" and rec["outcome"] == "adopted"
    for _ in range(50):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    assert "_repair" not in a.__dict__


def test_with_repair_leaves_the_original_messages_alone():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "scene"}]
    out = P.with_repair(msgs, {"failed": "craft spear", "reason": "you don't know how", "dropped": ["gather wood"]})
    assert msgs[-1]["content"] == "scene"
    assert out[-1]["content"].startswith("scene") and "you don't know how" in out[-1]["content"]
    assert "gather wood" in out[-1]["content"]
