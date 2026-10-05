"""A two-level mind (docs/TWO_LEVEL.md): a cascade brain answers the one-letter choices and hands each escalation to
the planner it names (`escalate_to`), never to any other model in its place."""

import asyncio
import json

import pytest

from chits.brain.mind import Mind
from chits.sim.world import World
from test_lab import lab_fake_llm  # noqa: F401  (the Lab's fake model server, a fixture)


def _minds():
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = o.health = 95.0
    m = Mind(None)
    m.upsert({"id": "plan", "base_url": "http://127.0.0.1:9/v1", "model": "planner-model"})
    m.upsert({"id": "jev", "base_url": "http://127.0.0.1:9/v1", "model": "jev", "prompt_style": "cascade",
              "escalate_to": "plan"})
    m.assign(w, "jev")
    chosen, thought = [], []
    m._choose_orig = Mind._choose
    m._spawn = lambda coro: coro.close()
    m._choose = lambda world, agent, brain, at_send, rec, sent, cascade=False: (
        chosen.append((world, agent, brain, at_send, rec, sent, cascade)) or asyncio.sleep(0))
    m._think = lambda world, agent, brain, at, rec, sent: thought.append((brain.id, rec)) or asyncio.sleep(0)
    return w, a, m, chosen, thought


def _escalate(m, chosen):
    world, agent, brain, at_send, rec, sent, cascade = chosen[-1]
    at_send()
    own = "ABCDEFGH"[len(sent["options"])]  # "my own idea": it escalates

    async def chat(at, **kw):
        at() if callable(at) else None
        return {"text": own, "top_logprobs": {own: 0.0}, "latency_ms": 1.0}

    brain.chat = chat
    asyncio.run(Mind._choose(m, world, agent, brain, at_send, rec, sent, cascade))
    return rec


def test_an_escalation_goes_to_the_planner_and_says_so():
    w, a, m, chosen, thought = _minds()
    m.hook(w, a)
    rec = _escalate(m, chosen)
    assert thought and thought[-1][0] == "plan"  # the planner writes the plan, not the decision brain
    assert rec["choice"]["escalated"] and rec["choice"]["planner"] == "plan"


def test_a_planner_that_is_down_means_no_escalation_never_another_model():
    import time

    w, a, m, chosen, thought = _minds()
    m.brains["plan"].cooldown_until = time.monotonic() + 600
    m.hook(w, a)
    rec = _escalate(m, chosen)
    assert not thought  # nobody else writes it
    assert rec["choice"]["escalated"] is False and rec["choice"]["denial"] == "planner unavailable"
    assert a.pending_plan is not None  # (its choice runs instead)


def _proto(url, **jev):
    return {"name": "two-level", "allow_models": True, "seeds": [7], "days": 1, "size": 64, "population": 3,
            "arms": [{"name": "two", "brain": "jev"}, {"name": "base"}],
            "brains": {"jev": {"id": "jev", "label": "Deciderx", "base_url": url, "model": "fake",
                               "max_concurrency": 4, "max_tokens": 120, "prompt_style": "cascade",
                               "escalate_below": 1.01, "escalate_share": 1.0, "escalate_to": "plan", **jev},
                       "plan": {"id": "plan", "label": "Plannerx", "base_url": url, "model": "fake-chit-7b",
                                "max_concurrency": 4, "max_tokens": 120}}}


def test_a_protocol_seals_its_planner_and_refuses_a_bad_one():
    from chits.lab.run import identities
    from chits.lab.spec import ExperimentSpec, SpecError

    spec = ExperimentSpec.from_dict(_proto("http://127.0.0.1:9/v1"))
    ids = {s.lower() for s in identities(spec, spec.arms[0])}
    assert {"plannerx", "plan", "fake-chit-7b"} <= ids  # (the planner names the arm too: redacted when blind)
    for bad in ({"escalate_to": "nobody"}, {"escalate_to": "jev"}, {"prompt_style": "full"}):
        with pytest.raises(SpecError):
            ExperimentSpec.from_dict(_proto("http://127.0.0.1:9/v1", **bad))
    p = _proto("http://127.0.0.1:9/v1")
    p["brains"]["plan"]["escalate_to"] = "jev"
    with pytest.raises(SpecError):
        ExperimentSpec.from_dict(p)


def test_a_lab_run_counts_the_planners_thinking_apart_and_stays_blind(monkeypatch, tmp_path, lab_fake_llm):
    from chits.lab import report, run
    from chits.lab.spec import ExperimentSpec

    import fake_llm as F

    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    monkeypatch.setitem(F.STATE, "letters", True)  # (the fake answers one-letter choices: cascade, then escalation)
    run.run(ExperimentSpec.from_dict(_proto(lab_fake_llm)), tmp_path / "run", jobs=1)
    model = next(x for x in run.results(tmp_path / "run") if x.get("compute"))
    assert model["compute"]["planner"]["requests"] > 0 and model["compute"]["requests"] > 0
    server = json.loads(next((tmp_path / "run" / "runs").glob("7_*/server.json")).read_text())
    assert server["planner"]["model"] == "fake-chit-7b"  # (kept apart, like the decision brain's server)
    blind = report.write_pack(tmp_path / "run").read_text().lower()
    assert "plannerx" not in blind and "deciderx" not in blind


def test_the_planners_server_is_checked_before_anything_runs(monkeypatch, tmp_path, lab_fake_llm):
    """A planner whose server doesn't serve the model it names stops the experiment before it starts, as a decision
    brain's does: the wrong model under the right name would write every escalated plan."""
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec, SpecError

    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    p = _proto(lab_fake_llm)
    p["brains"]["plan"]["model"] = "no-such-planner.gguf"
    with pytest.raises(SpecError, match="no-such-planner"):
        run.run(ExperimentSpec.from_dict(p), tmp_path / "run", jobs=1)
    assert not (tmp_path / "run" / "manifest.json").exists()


def test_an_architecture_comparison_is_declared_and_still_matches_sampling():
    """Research item 71: model arms differ only in the model. An architecture study (prompt style, escalation) must
    say so (compare: "architecture"), and even then sampling, tokens, timeouts and concurrency must match."""
    from chits.lab.spec import ExperimentSpec, SpecError

    url = "http://127.0.0.1:9/v1"
    base = {"id": "a", "base_url": url, "model": "m", "max_concurrency": 4, "max_tokens": 120}
    proto = {"name": "arch", "allow_models": True, "seeds": [1], "days": 1, "size": 64, "population": 3,
             "arms": [{"name": "full", "brain": "a"}, {"name": "cascade", "brain": "b"}],
             "brains": {"a": dict(base), "b": dict(base, id="b", prompt_style="cascade")}}
    with pytest.raises(SpecError, match="architecture"):
        ExperimentSpec.from_dict(proto)
    spec = ExperimentSpec.from_dict(dict(proto, compare="architecture"))
    assert spec.fingerprint() != ExperimentSpec.from_dict(dict(proto, brains={"a": dict(base), "b": dict(base, id="b")})).fingerprint()
    hot = dict(proto, compare="architecture")
    hot["brains"] = {"a": dict(base), "b": dict(base, id="b", prompt_style="cascade", temperature=1.2)}
    with pytest.raises(SpecError, match="temperature"):
        ExperimentSpec.from_dict(hot)
    with pytest.raises(SpecError):
        ExperimentSpec.from_dict(dict(proto, compare="vibes"))
