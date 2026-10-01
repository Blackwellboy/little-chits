"""Compute accounting (research plan item 29): what a world's thinking cost, beside what it achieved."""

from types import SimpleNamespace

from chits import diag
from chits.sim.world import World
from chits.tools.experiment import _compute, _md


def _brain(tin=6000, tout=2000, requests=10, failed=1, retries=2):
    return SimpleNamespace(stats=SimpleNamespace(tokens_in=tin, tokens_out=tout, requests=requests, failed=failed,
                                                 retries=retries))


def test_the_cost_of_a_worlds_thinking():
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for origin, res in (("model_generated", "done"), ("model_repaired", "done"), ("model_selected", "no wood"),
                        ("instinct", "done"), ("reflex", "done")):
        diag.action_finished(w, a, {"do": "gather", "_origin": origin, "_reflex": origin == "reflex"}, res)
    recs = [{"outcome": "adopted", "latency_ms": 1500}, {"outcome": "adopted", "style": "repair", "latency_ms": 500},
            {"outcome": "stale", "latency_ms": 1000}, {"outcome": "failed", "latency_ms": None},
            {"outcome": "adopted", "style": "chief-project", "latency_ms": 2000}]
    c = _compute(_brain(), recs, diag.of(w), 2.0, 4)
    assert c["tokens"] == 8000 and c["tokens_per_day"] == 4000.0
    assert c["decisions_adopted"] == 2 and c["tokens_per_decision"] == 4000.0  # (the chief's choice isn't a plan)
    assert c["tokens_per_discovery"] == 2000.0 and c["request_seconds"] == 5.0
    assert c["repair_rate"] == 0.25
    assert c["model_steps_done"] == 2 and c["model_step_success"] == 0.667  # instinct and reflexes don't count
    assert c["model_steps_done_per_1k_tokens"] == 0.2
    assert c["requests"] == 10 and c["failed_requests"] == 1 and c["retries"] == 2


def test_nothing_to_divide_by_is_none_not_a_crash():
    w = World("A", "A", 1, "direct", 64, 2)
    c = _compute(_brain(0, 0, 0, 0, 0), [], diag.of(w), 0.0, 0)
    assert c["tokens_per_day"] is None and c["tokens_per_discovery"] is None and c["model_step_success"] is None
    assert c["repair_rate"] == 0.0
    assert _compute(None, [], diag.of(w), 1.0, 0) == {}


def _summary(mode):
    axes = {"deaths_by_cause": {}, "discovery_days": []}
    ws = {wid: {"label": f"M{wid}", "axes": axes, "model_plans": 1,
                "compute": {"tokens": 100 * (i + 1), "tokens_per_discovery": None}} for i, wid in enumerate("AB")}
    return {"seed": 1, "days": 1, "ticks": 240, "wall_s": 1.0, "mode": mode, "worlds": ws}


def test_the_report_has_a_cost_table_and_describes_the_mode_it_ran():
    md = _md(_summary("versus"), {}, [])
    assert "## What the thinking cost" in md and "| Tokens | 100 | 200 |" in md
    assert "| Tokens per discovery | – | – |" in md
    assert "both can talk" in md and "can only watch" not in md
    md = _md(_summary("culture"), {}, [])
    assert "World B can only watch" in md
