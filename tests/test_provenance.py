"""Who decided what (provenance.py): every plan and step is put in one category, and no model is credited with what
its body, the executor, upkeep or the heuristic planner did."""

import json
import re
from pathlib import Path

from chits import diag
from chits import provenance as PV
from chits.sim import actions
from chits.sim.world import World

SERVER = Path(__file__).resolve().parents[1] / "server" / "chits"


def test_every_origin_label_the_code_assigns_has_a_category():
    """A label added later and left out of provenance.py would be counted as unknown (and credited to no one):
    every literal origin the code assigns, and every kind instinct plans are adopted as, must map."""
    src = "\n".join(p.read_text() for p in SERVER.rglob("*.py"))
    found = set(re.findall(r'\["_origin"\] = "(\w+)"', src))
    found |= set(re.findall(r'_instinct_plan\([^)]*kind="(\w+)"', src))
    found |= set(re.findall(r'origin = "(model_\w+)"', src))
    found |= {"model_generated", "model_selected", "model_repaired", "instinct", "fallback", "filler"}  # (mind.py)
    assert found, "the scan found nothing: its patterns are stale"
    assert {o: PV.category(o) for o in found if PV.category(o) == "unknown"} == {}


def test_reflexes_and_filler_are_never_the_models():
    assert PV.of_step({"do": "eat", "_reflex": True, "_origin": "model_generated"}) == "body_reflex"
    assert PV.of_step({"do": "rest", "_filler": True, "_origin": "model_generated"}) == "filler"
    assert PV.of_step({"do": "gather", "_origin": "model_selected"}) == "model_choice"
    assert PV.of_step({"do": "gather"}) == "unknown"
    assert PV.category("duty") == PV.category("instinct") == "instinct_plan"


def test_a_menu_choice_is_the_models_decision_but_instincts_plan():
    dr = PV.drivers({"model_selected": 6, "model_generated": 2, "instinct": 2, "routine": 10, "filler": 5},
                    {"model_selected": 30, "reflex": 50, "routine": 10, "instinct": 10}, waiting_ticks=25,
                    model_ticks=100, redirects=3)
    # strategic plans: 6 menu choices, 2 written, 2 instinct (routine and filler aren't strategic)
    assert dr["model_strategic_pct"] == 80.0 and dr["model_authored_strategic_pct"] == 20.0
    assert dr["model_steps_pct"] == 30.0 and dr["model_authored_steps_pct"] == 0.0
    assert dr["reflex_steps_pct"] == 50.0 and dr["routine_steps_pct"] == 10.0 and dr["instinct_steps_pct"] == 10.0
    assert dr["waiting_pct"] == 25.0 and dr["redirects"] == 3
    assert dr["steps"]["counts"]["body_reflex"] == 50 and sum(dr["steps"]["pct"][c] for c in PV.MODEL) == 30.0
    empty = PV.drivers({}, {})
    assert empty["model_strategic_pct"] is None and empty["steps"]["total"] == 0


def test_a_finished_step_records_its_provenance_and_a_redirect_is_executions_not_the_models():
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    a.learn("design:campfire", "taught", w.tick)
    fire = w.place_site("campfire", *w.find_site("campfire", a.x + 2, a.y, 8), a)
    w.complete_structure(fire, a)
    fire.fuel = 10
    a.inventory["wood"] = 3
    a.plan = [{"do": "build", "what": "campfire", "_origin": "model_generated"}]
    for _ in range(200):
        if not a.plan:
            break
        actions.run(w, a)
        w.tick += 1
    d = diag.of(w)
    rec = next(r for r in d.recent_steps if r["verb"] == "build")
    assert rec["provenance"] == "model_plan" and rec["executed_as"] == "refuel" and d.redirects == 1


def test_lab_results_say_who_drove_each_run(tmp_path):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "drivers", "arms": [{"name": "a"}, {"name": "b"}], "seeds": [3],
                                     "days": 2, "size": 64, "population": 4})
    run.run(spec, tmp_path / "out")
    for p in (tmp_path / "out" / "runs").glob("*/result.json"):
        f = json.loads(p.read_text())["final"]
        # instinct arms: no plan goes through a mind, so none is counted as decided (none, not 0%); every finished
        # step is instinct's or the body's, none the model's
        assert f["model_strategic_share"] is None and f["model_authored_step_share"] == 0.0
        assert f["instinct_step_share"] > 0 and f["reflex_step_share"] is not None
        assert abs(f["instinct_step_share"] + f["reflex_step_share"] + f["routine_step_share"] - 1) < 0.01


def test_the_scorecard_shows_who_is_driving(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        rows = c.get("/api/scorecard").json()["rows"]
        assert rows and all({"model_strategic_pct", "reflex_steps_pct", "waiting_pct"} <= set(r["drivers"]) for r in rows)


def test_a_models_spoken_reply_is_the_models():
    """Codex on #139: a reply's top-level "say" was inserted untagged and counted as unknown."""
    from chits.brain.mind import Mind

    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    m = Mind(None)
    m.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1"})
    m.assign(w, "m")
    a.plan = []
    a.pending_plan = {"goal": "talk", "thought": "", "steps": [{"do": "rest"}], "say": "hello all", "objective": ""}
    m.hook(w, a)
    say = next(s for s in a.plan if s.get("do") == "say")
    assert PV.of_step(say) == "model_plan" and all(PV.of_step(s) == "model_plan" for s in a.plan)


def test_the_report_lists_redirects():
    from chits.lab import report

    assert "redirects" in {k for _, k in report.OPPORTUNITY_ROWS}
