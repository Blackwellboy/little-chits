"""Bounded action repair for choosing brains (issue #112): a menu choice that failed puts the simulator's exact reason in
the next choice scene, and in a cascade's full plan when it escalates. Behind mind.CHOICE_REPAIR (off): until now a
choose or cascade brain never heard why its choice failed."""

import asyncio
import json

import pytest

from chits.brain import mind as M
from chits.brain.mind import Mind
from chits.sim import actions
from test_lab import lab_fake_llm  # noqa: F401  (the Lab's fake model server, a fixture)
from test_action_repair import fail_step, setup as full_setup  # noqa: E402  (a sibling test module, as in test_model_only)

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


# ----------------------------------------------------------------------------------------- a Lab arm setting

def _proto(repair_a=None, style="full", url="http://127.0.0.1:9/v1"):
    brain = {"id": "fake", "label": "Fake", "base_url": url, "model": "fake", "max_concurrency": 4,
             "max_tokens": 120, "prompt_style": style}
    a = {"name": "a", "brain": "fake", **({"repair": repair_a} if repair_a is not None else {})}
    return {"name": "repair", "arms": [a, {"name": "b", "brain": "fake"}], "allow_models": True,
            "brains": {"fake": brain}, "seeds": [7], "days": 2, "size": 64, "population": 4}


def test_repair_is_a_declared_arm_setting_and_old_protocols_keep_their_fingerprint():
    from chits.lab.spec import ExperimentSpec, SpecError

    plain = ExperimentSpec.from_dict(_proto())
    assert ExperimentSpec.from_dict(_proto(False)).fingerprint() == plain.fingerprint()
    on = ExperimentSpec.from_dict(_proto(True))
    assert on.fingerprint() != plain.fingerprint() and on.arms[0].repair is True
    with pytest.raises(SpecError):
        ExperimentSpec.from_dict(_proto("yes"))
    with pytest.raises(SpecError, match="instinct arm"):
        ExperimentSpec.from_dict({**_proto(), "arms": [{"name": "a", "repair": True}, {"name": "b"}]})


def test_each_arm_runs_with_the_repair_it_declares(monkeypatch, tmp_path, lab_fake_llm):
    """Choosing brains included (mind.choice_repair). A cascade's choices rarely fail since the menu offers only what
    can start (#119), so this reads the minds the Lab made rather than waiting for a failure."""
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec

    made = []
    init = M.Mind.__init__

    def record(self, *a, **kw):
        init(self, *a, **kw)
        made.append(self)

    monkeypatch.setattr(M.Mind, "__init__", record)
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    run.run(ExperimentSpec.from_dict({**_proto(True, "cascade", lab_fake_llm), "days": 1}), tmp_path / "run", jobs=1)
    assert sorted((m.repair, m.choice_repair) for m in made) == [(False, False), (True, True)]


@pytest.mark.parametrize("style", ["full"])
def test_only_the_repair_arm_hears_why_its_step_failed(monkeypatch, tmp_path, lab_fake_llm, style):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec

    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    spec = ExperimentSpec.from_dict(_proto(True, style, lab_fake_llm))
    run.run(spec, tmp_path / "run", jobs=1)
    names = json.loads((tmp_path / "run" / "sealed" / "assignment.json").read_text())
    told = {}
    for label, arm in names.items():
        tape = (tmp_path / "run" / "runs" / f"7_{label}" / "tape.jsonl").read_text()
        told[arm] = ("PLAN FAILED" in tape)
    assert told == {"a": True, "b": False}, told
    res = {names[r["label"]]: r["final"] for r in run.results(tmp_path / "run")}
    assert res["a"]["repairs_asked"] > 0 and res["b"]["repairs_asked"] == 0  # (recorded, for the study)
    assert res["b"]["repaired_steps_ok"] == res["b"]["repaired_steps_failed"] == 0  # (no repair, no repaired steps;
    # whether a repaired plan runs a step before the run ends depends on the fake model's replies, so arm a's isn't fixed)
    assert all(0 <= f["model_step_failure_rate"] <= 1 and f["model_steps_failed"] >= 0 for f in res.values())


def test_a_minds_own_choice_repair_setting_overrides_the_module_switch(monkeypatch):
    for module, own, expect in ((False, True, True), (True, False, False), (True, None, True)):
        monkeypatch.setattr(M, "CHOICE_REPAIR", module)
        w, a, m, b, chosen, _ = setup("cascade")
        m.choice_repair = own
        fail_step(w, a, origin="model_selected")
        m._ask(w, a, b)
        assert (LINE in chosen[-1][3]()[-1]["content"]) is expect, (module, own)


def test_a_protocol_sealed_before_arm_repair_existed_keeps_its_fingerprint():
    """docs/protocols/jevk5-vs-gemma.json was sealed as 6fc60a4faaa15742 (its manifest, 2026-10-06, commit d3882f3)."""
    from pathlib import Path

    from chits.lab.spec import ExperimentSpec

    root = Path(__file__).resolve().parents[1]
    spec = ExperimentSpec.load(root / "docs" / "protocols" / "jevk5-vs-gemma.json") if hasattr(ExperimentSpec, "load")         else ExperimentSpec.from_dict(json.loads((root / "docs" / "protocols" / "jevk5-vs-gemma.json").read_text()))
    assert spec.fingerprint() == "6fc60a4faaa15742"


def test_a_repaired_plan_counts_only_its_corrective_first_step():
    """Codex on #142: every step of a repaired plan was counted, so a good first step's followers inflated the
    repair's success. Only each repaired decision's first finished step counts."""
    from chits import diag
    from chits.sim.world import World

    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    plan = [{"do": "rest", "_origin": "model_repaired", "_decision_id": "r1"},
            {"do": "rest", "_origin": "model_repaired", "_decision_id": "r1"},
            {"do": "rest", "_origin": "model_repaired", "_decision_id": "r1"}]
    for s in plan:
        diag.action_finished(w, a, dict(s), "done")
    diag.action_finished(w, a, {"do": "craft", "_origin": "model_repaired", "_decision_id": "r2"}, "missing wood")
    d = diag.of(w)
    assert d.repaired_first == {"ok": 1, "fail": 1}
    from chits.lab.run import repair_outcomes

    out = repair_outcomes(w)
    assert out["repaired_steps_ok"] == 1 and out["repaired_steps_failed"] == 1


def test_failure_loops_are_the_models_own():
    """Codex on #142: loops from reflexes and instinct were counted in the model's failure_loops."""
    from chits import diag
    from chits.lab.run import repair_outcomes
    from chits.sim.world import World

    w = World("A", "A", 3, "direct", 64, 2)
    d = diag.of(w)
    d.loops.update({"model": 2, "reflex": 5, "instinct": 3})
    assert repair_outcomes(w)["failure_loops"] == 2
