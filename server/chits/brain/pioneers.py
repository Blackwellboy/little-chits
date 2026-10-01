"""Instinct for pioneers (sim/pioneers.py): light the new village's first fire, then build a home there."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..sim import pioneers as PI
from ..sim.agent import Agent
from ..sim.items import DESIGNS

Plan = Dict[str, Any]
W = 6.0  # the party set out on purpose: it goes


def plan(world, a: Agent) -> Plan | None:
    from .instinct import _need_steps

    em = PI.pioneer(world, a)
    if not em or world.is_night:
        return None
    sx, sy = em["x"], em["y"]
    near = f"{sx},{sy}"
    if not any(s.design == "campfire" and s.dist(sx, sy) <= 10 for s in world.structures.values()):
        what, goal, thought = "campfire", "light the new village's first fire", "A new village starts with a fire."
    else:
        home = world.structures.get(a.home or "")
        if home is not None and home.dist(sx, sy) <= 12:
            return None  # settled in
        what, goal, thought = "hut", "build a home in the new village", "Our new village needs homes. Mine first."
    mats = DESIGNS[what].material_map
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        return None
    return {"goal": goal, "thought": thought, "steps": steps[:4] + [{"do": "build", "what": what, "near": near}]}


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    p = plan(world, a)
    return [(W, p)] if p else []
