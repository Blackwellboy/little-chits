"""Who decided what a chit did (docs/PROVENANCE.md).

"Instinct" covers several different mechanisms, and only some of them are a model deciding anything. Every plan a
chit adopts and every step it finishes carries an origin label (`step["_origin"]`, set where the plan is adopted in
brain/mind.py; `_reflex` and `_filler` flags for the body's reflexes and filler). This module maps each label to one
category, so diagnostics, the Lab and the UI all count the same way and none credits a model with what its body,
the executor or the heuristic planner did.

    model_plan     the model wrote this plan (full or compact prompt)
    model_choice   the model chose this plan by letter from options instinct drafted (choose/cascade): the model
                   decided, but instinct's menu generator wrote the plan
    model_repair   the model's plan after the simulator told it why its last one failed (bounded repair)
    body_reflex    the body met a physical need: eat, sleep, shelter, warm up, make room in its hands
    routine        upkeep adopted without asking the model (eat, sleep, rest, shelter, store, drop, refuel)
    instinct_plan  the heuristic strategic planner decided: no model, or a pioneer's duty
    fallback       the heuristic planner stood in because the model was unavailable or its queue was full
    filler         something to do while waiting for the model's answer (heuristic)
    unknown        a step with no label (should not happen; counted, never credited to anyone)

Deterministic execution (walking, pathfinding, fetching a craft's inputs, a build that turns into feeding the fire
beside it) is not a decision: it carries out the step it belongs to, under that step's category, and redirects are
counted on their own (`redirects`).
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

CATEGORIES = ("model_plan", "model_choice", "model_repair", "body_reflex", "routine", "instinct_plan", "fallback",
              "filler", "unknown")
MODEL = frozenset({"model_plan", "model_choice", "model_repair"})  # the model decided
MODEL_AUTHORED = frozenset({"model_plan", "model_repair"})  # ... and wrote the plan itself
STRATEGIC = frozenset({"model_plan", "model_choice", "model_repair", "instinct_plan", "fallback"})  # what to do next,
# as opposed to the body's needs, upkeep and filler

LABELS = {
    "model_plan": "Model wrote the plan", "model_choice": "Model chose from instinct's menu",
    "model_repair": "Model repaired a failed plan", "body_reflex": "Body reflex", "routine": "Routine upkeep",
    "instinct_plan": "Heuristic instinct", "fallback": "Instinct standing in for the model",
    "filler": "Filler while waiting", "unknown": "Unlabelled",
}

_ORIGINS = {
    "model_generated": "model_plan", "model_selected": "model_choice", "model_repaired": "model_repair",
    "model_repaired_choice": "model_choice",  # (a repaired choice: still instinct's plan, picked by the model)
    "reflex": "body_reflex", "routine": "routine", "instinct": "instinct_plan", "duty": "instinct_plan",
    "fallback": "fallback", "shed": "fallback", "filler": "filler",
    # a chit's plan_source, for a step with no label of its own (an instinct-only Lab run installs plans directly)
    "instinct-routine": "routine", "instinct-duty": "instinct_plan", "instinct-filler": "filler",
    "instinct-fallback": "fallback",
}


def category(origin: Any) -> str:
    """The category of an origin label (a step's `_origin`, or a plan's authorship kind)."""
    return _ORIGINS.get(str(origin or ""), "unknown")


def of_step(step: Mapping[str, Any], fallback: Any = None) -> str:
    """A step's category: its body reflex and filler flags first, then its origin label, then `fallback` (the plan's
    source, for a step with no label of its own)."""
    if step.get("_reflex"):
        return "body_reflex"
    if step.get("_filler"):
        return "filler"
    return category(step.get("_origin") or fallback)


def _shares(counts: Mapping[str, int]) -> Dict[str, Any]:
    by = {c: int(counts.get(c, 0)) for c in CATEGORIES}
    total = sum(by.values())
    pct = {c: (round(100 * n / total, 1) if total else None) for c, n in by.items()}
    return {"counts": by, "pct": pct, "total": total}


def _pct(n: int, d: int):
    return round(100 * n / d, 1) if d else None


def drivers(plan_counts: Mapping[str, int], step_counts: Mapping[str, int], waiting_ticks: int = 0,
            model_ticks: int = 0, redirects: int = 0) -> Dict[str, Any]:
    """Who drove a world: plans adopted and steps finished, by category (counts and shares), with the headline
    shares the UI shows. `plan_counts`/`step_counts` are keyed by category or by origin label (either is mapped)."""
    plans: Dict[str, int] = {}
    for k, n in plan_counts.items():
        c = k if k in CATEGORIES else category(k)
        plans[c] = plans.get(c, 0) + int(n)
    steps: Dict[str, int] = {}
    for k, n in step_counts.items():
        c = k if k in CATEGORIES else category(k)
        steps[c] = steps.get(c, 0) + int(n)
    strategic = sum(plans.get(c, 0) for c in STRATEGIC)
    finished = sum(steps.values())
    return {
        "plans": _shares(plans), "steps": _shares(steps),
        # of the plans that set what to do next (not the body's needs, upkeep or filler): how many the model decided,
        # and how many it also wrote (a menu choice was written by instinct)
        "model_strategic_pct": _pct(sum(plans.get(c, 0) for c in MODEL), strategic),
        "model_authored_strategic_pct": _pct(sum(plans.get(c, 0) for c in MODEL_AUTHORED), strategic),
        "model_steps_pct": _pct(sum(steps.get(c, 0) for c in MODEL), finished),
        "model_authored_steps_pct": _pct(sum(steps.get(c, 0) for c in MODEL_AUTHORED), finished),
        "reflex_steps_pct": _pct(steps.get("body_reflex", 0), finished),
        "routine_steps_pct": _pct(steps.get("routine", 0), finished),
        "instinct_steps_pct": _pct(sum(steps.get(c, 0) for c in ("instinct_plan", "fallback", "filler")), finished),
        "waiting_pct": _pct(waiting_ticks, model_ticks),
        "redirects": int(redirects),
    }
