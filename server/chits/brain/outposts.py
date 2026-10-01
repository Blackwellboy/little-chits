"""Instinct for outpost camps (upgrade #8): found one beside far ore, sand or clay, work it, and haul home.

World A's chits failed "there is no copper ore anywhere nearby" 332 times: ore lay beyond the 26 tiles instinct
gathers in, and a trip there and back cost a winter's day. A camp by it changes that: chits gather there and store
it in the camp, sleep there on long trips, and haulers carry full loads home. Like the rest of instinct this only
uses what the chit knows: the camp is founded where it remembers seeing the resource (sim.actions.remembered_place).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..sim.actions import remembered_place, stockpile_room
from ..sim.agent import TICKS_PER_DAY, Agent
from ..sim.items import DESIGNS, GATHER_RULES, HOME_STORES, item_name

Plan = Dict[str, Any]
FAR = 30  # a resource at least this far from home is worth a camp
CAMP_REACH = 10  # a camp this close to a place serves it
HAUL_MIN = 6  # a camp holding this much of something is worth a trip home
FOUND_W, WORK_W, HAUL_W = 2.2, 1.8, 1.6


def _home_xy(world, a: Agent) -> Tuple[int, int]:
    h = world.structures.get(a.home or "")
    return (h.x, h.y) if h is not None else (a.x, a.y)


def _wanted(world, a: Agent) -> List[str]:
    """The scarce things this chit has a use for."""
    out = []
    if a.knows_recipe("copper") or a.knows_recipe("iron") or a.best_tool("pick"):
        if a.best_tool("pick"):
            out.append("ore")
    if a.knows_recipe("brick") or a.knows_recipe("glass"):
        out.append("sand")
    out.append("clay")
    return out


def _camps(world) -> List:
    return [s for s in world.structures.values() if s.design == "outpost" and s.functional]


def found_plan(world, a: Agent) -> Optional[Plan]:
    """A scarce thing it needs lies only far from home, where it remembers seeing some, and no camp serves that place:
    found one there."""
    from .instinct import _need_steps

    t = world.tick
    memo = world.__dict__.setdefault("_nocamp", {})  # a planner's cache: not saved, not the chit's state
    if not a.knows_design("outpost") or memo.get(a.id, 0) > t or a.reflex_rest.get("nobuild:outpost", 0) > t:
        return None
    if len(_camps(world)) + sum(1 for s in world.structures.values() if s.design == "outpost" and not s.complete) \
            >= max(1, len(world.agents) // 15):
        return None
    hx, hy = _home_xy(world, a)
    for kind in _wanted(world, a):
        if world.nearest_resource(hx, hy, kind, 26):
            continue  # there's some near home
        spot = remembered_place(world, a, kind)
        if spot is None or max(abs(spot[0] - hx), abs(spot[1] - hy)) < FAR:
            continue
        if any(c.dist(*spot) <= CAMP_REACH for c in world.structures.values() if c.design == "outpost"):
            continue
        mats = DESIGNS["outpost"].material_map
        steps = _need_steps(a, mats, world)
        if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
            continue
        return {"goal": f"set up a camp by the {item_name(kind)}",
                "thought": f"The {item_name(kind)} is a long way from home. A camp beside it would let us work it.",
                "steps": steps[:4] + [{"do": "build", "what": "outpost", "near": f"{spot[0]},{spot[1]}"}]}
    memo[a.id] = t + TICKS_PER_DAY  # nothing to camp by: look again tomorrow
    return None


def work_plan(world, a: Agent) -> Optional[Plan]:
    """A camp stands beside something this chit needs: go, gather it, and store it in the camp."""
    for camp in sorted(_camps(world), key=lambda c: c.dist(a.x, a.y)):
        if camp.dist(a.x, a.y) > 60 or not world.same_land(a, camp) or stockpile_room(camp, "ore") < 6:
            continue
        for kind in _wanted(world, a):
            rule = GATHER_RULES.get(kind) or {}
            if rule.get("requires") and not a.best_tool(rule["tool"]):
                continue
            if world.nearest_resource(camp.x, camp.y, kind, CAMP_REACH):
                return {"goal": f"work the camp's {item_name(kind)}",
                        "thought": f"There's {item_name(kind)} by the camp. I'll gather some and leave it in the camp's store.",
                        "steps": [{"do": "go", "to": camp.id}, {"do": "gather", "what": kind, "qty": 6},
                                  {"do": "store", "what": kind, "target": camp.id}]}
    return None


def haul_plan(world, a: Agent) -> Optional[Plan]:
    """A camp's store holds a load of something, and home is far: carry it home."""
    hx, hy = _home_xy(world, a)
    home_piles = [p for p in world.structures_near(hx, hy, 20, "stockpile") if p.design in HOME_STORES and p.functional]
    if not home_piles or a.free_space() < HAUL_MIN:
        return None
    for camp in sorted(_camps(world), key=lambda c: c.dist(a.x, a.y)):
        if camp.dist(hx, hy) < 20 or camp.dist(a.x, a.y) > 60 or not world.same_land(a, camp):
            continue
        goods = sorted(((n, k) for k, n in camp.storage.items() if n >= HAUL_MIN and k in GATHER_RULES), reverse=True)
        for n, k in goods:
            pile = next((p for p in home_piles if stockpile_room(p, k) >= HAUL_MIN), None)
            if pile is None:
                continue
            qty = min(n, 8, a.free_space())
            return {"goal": f"haul {item_name(k)} home from the camp",
                    "thought": f"The camp's store is full of {item_name(k)}. Home needs it.",
                    "steps": [{"do": "take", "what": k, "qty": qty, "target": camp.id},
                              {"do": "store", "what": k, "target": pile.id}]}
    return None


TRIP_W = 1.2
TRIP_FAR = 80  # the farthest a remembered place is worth a trip on foot
TRIPS_PER = 20  # one chit on such a trip at a time per this many chits


def trip_plan(world, a: Agent) -> Optional[Plan]:
    """Something it needs is gone from around home and no camp serves the place it remembers some: walk there, fill its
    hands, and bring it home. (The live worlds failed "no sand anywhere nearby" and "no copper ore" hundreds of times
    while sand and ore lay 30-80 tiles away; World B, whose chits didn't know how to build a camp, never went.)
    Only a fed, rested chit goes, and only a few at a time: sending instinct far cost chits before."""
    if a.hunger < 60 or a.energy < 50 or a.health < 70 or a.free_space() < 6:
        return None
    if sum(1 for o in world.agents.values() if str(o.goal).startswith("fetch ")) >= max(1, len(world.agents) // TRIPS_PER):
        return None
    hx, hy = _home_xy(world, a)
    piles = [p for p in world.structures_near(hx, hy, 20, "stockpile") if p.design in HOME_STORES and p.functional]
    if not piles:
        return None
    for kind in _wanted(world, a):
        if a.reflex_rest.get("scarce:" + kind, 0) <= world.tick and world.nearest_resource(hx, hy, kind, 26):
            continue  # there's some near home
        rule = GATHER_RULES.get(kind) or {}
        if rule.get("requires") and not a.best_tool(rule["tool"]):
            continue
        spot = remembered_place(world, a, kind)
        if spot is None or max(abs(spot[0] - hx), abs(spot[1] - hy)) > TRIP_FAR:
            continue
        if any(c.dist(*spot) <= CAMP_REACH for c in _camps(world)):
            continue  # a camp's there: work_plan and haul_plan use it
        pile = next((p for p in piles if stockpile_room(p, kind) >= 6), None)
        if pile is None:
            continue
        return {"goal": f"fetch {item_name(kind)} from far away",
                "thought": f"There's no {item_name(kind)} left near home, but I remember some at ({spot[0]},{spot[1]}).",
                "steps": [{"do": "go", "to": f"{spot[0]},{spot[1]}"},
                          {"do": "gather", "what": kind, "qty": min(8, a.free_space()), "_far": True},  # (not near home)
                          {"do": "store", "what": kind, "target": pile.id}]}
    return None


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    if a.is_child(world.tick) or world.is_night:
        return []
    out: List[Tuple[float, Plan]] = []
    for w, plan in ((HAUL_W, haul_plan(world, a)), (WORK_W, work_plan(world, a)), (FOUND_W, found_plan(world, a)),
                    (TRIP_W, trip_plan(world, a))):
        if plan:
            out.append((w, plan))
    return out
