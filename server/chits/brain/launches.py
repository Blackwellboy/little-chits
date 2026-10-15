"""Instinct for the space programme (sim/space.py): a grown chit near a launch pad, with a rocket in hand or one in
the stores within its reach, takes it to the pad and flies it. Never while the stores near it run short of food."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..sim.agent import Agent

Plan = Dict[str, Any]
W = 1.2  # low-ish: the rocket waits while there is other work (and the plan takes an hour or two)
PAD_NEAR = 30
STORE_NEAR = 25


def options(world, a: Agent) -> List[Tuple[float, Plan]]:
    from ..sim import food, space
    from .instinct import _reachable

    if not space.on() or a.is_child(world.tick) or food.short(world, a):
        return []
    pad = next((s for s in world.structures_near(a.x, a.y, PAD_NEAR, "launch_pad") if s.functional and _reachable(world, a, s)), None)
    if pad is None:
        return []
    steps: List[Plan] = []
    if not a.has("rocket"):
        pile = next((s for s in world.structures_near(a.x, a.y, STORE_NEAR, "stockpile") if s.functional
                     and s.storage.get("rocket", 0) > 0 and _reachable(world, a, s)), None)
        if pile is None:
            return []
        it = world.item("rocket")
        if a.free_space() < (it.weight if it else 6):
            steps.append({"do": "store", "what": "all", "target": pile.id})  # (hands free for it first)
        steps.append({"do": "take", "what": "rocket", "qty": 1, "target": pile.id})
    steps.append({"do": "launch", "target": pad.id})
    return [(W + a.traits.get("curiosity", 0.5), {"goal": "launch the rocket", "thought": "The rocket is ready. Time to fly.",
                                                  "steps": steps})]
