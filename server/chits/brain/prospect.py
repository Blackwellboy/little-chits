"""Instinct for prospecting: when something the village needs is gone from around home and nobody here remembers where
more lies, one chit walks far out to look (sim.actions._do_prospect). Where chits talk, what it finds is told at home and
every hearer remembers it (sim.actions.remembered_place reads what it heard); where they can't, only the prospector knows,
and its own outpost camp or mine plans (brain/outposts.py) use it."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..sim.actions import remembered_place
from ..sim.agent import Agent
from ..sim.items import item_name
from . import outposts as OP

Plan = Dict[str, Any]
W = 1.0


def prospect_plan(world, a: Agent) -> Plan | None:
    t = world.tick
    if a.origin or a.is_child(t) or world.is_night or (getattr(world, "civic", None) or {}).get("prospector_until", 0) > t:
        return None
    if a.hunger < 45 or a.energy < 45:
        return None  # (a long walk: set out fed and rested)
    hx, hy = OP._home_xy(world, a)
    for kind in OP._wanted(world, a):
        if world.nearest_resource(hx, hy, kind, 26) or remembered_place(world, a, kind):
            continue
        if kind in ("ore", "iron_ore"):
            from ..sim import buildings as BLD

            if BLD.mine_near(world, a, BLD.PIT_REACH, kind) is not None:
                continue
        return {"goal": f"go prospecting for {item_name(kind)}",
                "thought": f"There's no {item_name(kind)} left near home. Somewhere out there, there must be.",
                "steps": [{"do": "prospect", "what": kind}]}
    return None


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    plan = prospect_plan(world, a)
    return [(W + a.traits.get("curiosity", 0.5), plan)] if plan else []
