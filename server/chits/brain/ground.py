"""Instinct for things lying on the ground (T28 piles): a curious chit picks up and studies a strange object, and
anyone can carry loose goods back to a stockpile.

The audit of day 1,361 found no chit had picked anything up in a week. Instinct never did (only a model's plan could,
and World A had no model), so meteorites from day 635 still lay where they fell, god-mode gifts went untouched, and
the loads chits dropped when the stockpiles were full stayed on the ground: one pile in World B's village held 570
charcoal, 22 sand and 19 copper while its chits failed "no stockpile nearby has charcoal"."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..sim.actions import stockpile_room
from ..sim.agent import TICKS_PER_DAY, Agent
from ..sim.items import HOME_STORES, item_name
from . import surplus as SUR

Plan = Dict[str, Any]
NEAR = 15  # tiles: a pile this close is worth a look
TIDY_MIN = 3  # loose goods worth a trip to the stockpile
TIDIERS_PER = 15  # one chit tidying up at a time per this many chits
CURIO_W, TIDY_W = 2.4, 1.4


def _goods(pile: Dict[str, int]) -> Dict[str, int]:
    from ..sim import artifacts as ART

    return {k: n for k, n in pile.items() if k != "_t" and n > 0 and not ART.is_artifact(k)}


def curio_plan(world, a: Agent) -> Optional[Plan]:
    """A strange object lies nearby: a curious chit goes to pick it up (or, if it's too big to carry, look at it) and
    studies it. Once per object and chit, every few days at most."""
    from ..sim import artifacts as ART

    if a.traits.get("curiosity", 0.5) < 0.35:
        return None
    memo = world.__dict__.setdefault("_curio", {})  # a planner's cache: not saved, not the chit's state
    for px, py, pile in world.piles_near(a.x, a.y, NEAR):
        for k in sorted(k for k in pile if ART.is_artifact(k) and pile[k] > 0):
            key = (a.id, px, py, k)
            if memo.get(key, 0) > world.tick or a.reflex_rest.get(f"unreach:{px},{py}", 0) > world.tick:
                continue
            memo[key] = world.tick + 3 * TICKS_PER_DAY
            name = item_name(k)
            if k in ART.UNCARRIABLE:
                steps = [{"do": "go", "to": f"{px},{py}"}, {"do": "inspect", "what": k}]
            else:
                steps = [{"do": "pickup", "what": k}, {"do": "inspect", "what": k}]
            return {"goal": f"find out what the {name} is", "thought": f"Something strange lies at ({px},{py}): a {name}.",
                    "steps": steps}
    return None


def tidy_plan(world, a: Agent) -> Optional[Plan]:
    """Loose goods lie near home and a stockpile there has room: carry them in (a few chits at a time)."""
    if a.free_space() < 4 or a.hunger < 40:
        return None
    if sum(1 for o in world.agents.values() if str(o.goal).startswith("tidy up")) >= max(1, len(world.agents) // TIDIERS_PER):
        return None
    h = world.structures.get(a.home or "")
    hx, hy = (h.x, h.y) if h is not None else (a.x, a.y)
    piles = [p for p in world.structures_near(hx, hy, 20, "stockpile") if p.design in HOME_STORES and p.functional]
    for px, py, pile in world.piles_near(hx, hy, NEAR):
        if a.reflex_rest.get(f"unreach:{px},{py}", 0) > world.tick:
            continue
        goods = sorted(((n, k) for k, n in _goods(pile).items() if n >= TIDY_MIN), reverse=True)
        for n, k in goods:
            if SUR.over(world, a, k, (hx, hy)):
                continue  # the stores hold plenty of it (issue #7: loose seed carried in was the stores' biggest source)
            dest = next((p for p in piles if stockpile_room(p, k) >= 10), None)
            if dest is None:
                continue  # nowhere to put it: it would only be dropped again
            return {"goal": f"tidy up the {item_name(k)} lying about",
                    "thought": f"There's {item_name(k)} lying on the ground at ({px},{py}). It belongs in the stockpile.",
                    "steps": [{"do": "pickup", "what": k}, {"do": "store", "what": k, "target": dest.id}]}
    return None


def ground_stock(world, a: Agent, radius: int = 12) -> Dict[str, int]:
    """Loose goods (no strange objects) lying within reach, for the supply planner."""
    out: Dict[str, int] = {}
    for px, py, pile in world.piles_near(a.x, a.y, radius):
        if a.reflex_rest.get(f"unreach:{px},{py}", 0) > world.tick:
            continue
        for k, n in _goods(pile).items():
            out[k] = out.get(k, 0) + n
    return out


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    if a.is_child(world.tick) or world.is_night:
        return []
    out: List[Tuple[float, Plan]] = []
    for w, plan in ((CURIO_W * 2 * a.traits.get("curiosity", 0.5), curio_plan(world, a)), (TIDY_W, tidy_plan(world, a))):
        if plan:
            out.append((w, plan))
    return out
