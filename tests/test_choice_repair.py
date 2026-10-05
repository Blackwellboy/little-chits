"""Bounded action repair for choosing brains (issue #112): a menu choice that failed puts the simulator's exact reason in
the next choice scene, and in a cascade's full plan when it escalates. Behind mind.CHOICE_REPAIR (off): until now a
choose or cascade brain never heard why its choice failed."""

import asyncio

import pytest

from chits.brain import mind as M
from chits.brain.mind import Mind
from chits.sim import actions
from tests.test_action_repair import fail_step, setup as full_setup

LINE = "YOUR LAST PLAN FAILED"


def setup(style="cascade"):
    w, a, m, b, asked = full_setup()
    b.cfg.prompt_style = style
    chosen = []
    m._choose = lambda world, agent, brain, at_send, rec, sent, cascade=False: (
        chosen.append((world, agent, brain, at_send, rec, sent, cascade)) or asyncio.sleep(0))
    return w, a, m, b, chosen, asked


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(M, "CHOICE_REPAIR", True)


def test_off_a_choosing_brain_asks_as_before():
    w, a, m, b, chosen, _ = setup()
    fail_step(w, a, origin="model_selected")
    m._ask(w, a, b)
    *_, at_send, rec, sent, _c = chosen[-1]
    assert LINE not in at_send()[-1]["content"] and rec["style"] == "choose" and "_repair" in a.__dict__


@pytest.mark.parametrize("style", ["choose", "cascade"])
def test_the_next_choice_carries_the_reason_once(on, style):
    w, a, m, b, chosen, _ = setup(style)
    fail_step(w, a, origin="model_selected")
    m._ask(w, a, b)
    *_, at_send, rec, sent, _c = chosen[-1]
    msgs = at_send()
    assert LINE in msgs[-1]["content"] and a.__dict__.get("_repair") is None
    assert len([x for x in msgs if x["role"] == "user"]) == 1  # in the scene, not a second user turn
    assert msgs[-1]["content"].rstrip().endswith("Answer with one letter only.")  # still asked for a letter
    assert rec["style"] == "repair" and rec["repair_of"] == "d1" and rec["repair_step"].startswith("craft")
    a.thinking = False
    m._ask(w, a, b)  # bounded: the next choice is an ordinary one
    *_, at_send, rec, _s, _c = chosen[-1]
    assert LINE not in at_send()[-1]["content"] and rec["style"] == "choose"


def test_an_experiment_repairs_a_choice_only_when_declared(on):
    for repair, expect in ((None, False), (True, True)):
        w, a, m, b, chosen, _ = setup()
        m.strict, m.repair = True, repair
        fail_step(w, a, origin="model_selected")
        m._ask(w, a, b)
        assert (LINE in chosen[-1][3]()[-1]["content"]) is expect, repair


def test_a_repaired_choice_is_adopted_as_such_and_gets_no_second_repair(on):
    w, a, m, b, chosen, _ = setup()
    fail_step(w, a, origin="model_selected")
    m._ask(w, a, b)
    rec = chosen[-1][4]
    rec["parse"] = "choice"
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


def test_an_escalated_cascade_writes_its_plan_with_the_reason(on):
    w, a, m, b, chosen, _ = setup("cascade")
    fail_step(w, a, origin="model_selected")
    m._ask(w, a, b)
    world, agent, brain, at_send, rec, sent, cascade = chosen[-1]
    at_send()
    own = "ABCDEFGH"[len(sent["options"])]  # the last letter: its own idea, so it escalates

    async def chat(at, **kw):
        at() if callable(at) else None
        return {"text": own, "top_logprobs": {own: 0.0}, "latency_ms": 1.0}

    b.chat = chat
    full = []
    m._think = lambda world, agent, brain, at, rec, sent: full.append((at, rec)) or asyncio.sleep(0)
    asyncio.run(Mind._choose(m, world, agent, brain, at_send, rec, sent, cascade))
    full_at_send, rec2 = full[-1]
    fresh = full_at_send()
    assert "YOUR PLAN FAILED" in fresh[-1]["content"] and rec2["style"] == "repair"
