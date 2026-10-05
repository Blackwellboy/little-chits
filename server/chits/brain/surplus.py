"""Plenty (issue #7, F33): how much of a good is enough, and what to do with more.

A long live run filled every store: one world held about 1,900 seeds, the other about 990 wood and 840 grain, so station
shifts had no room for their goods. Instinct fetched by habit, with no reading of what the village already held: in
60-day runs two thirds of all the wood and stone gathered, and most of the charcoal and brick made by hand, were for a
building site whose materials lay in the stores, and what the site didn't take went into the stores as well.

Each good has a ceiling that grows with the village's people. The urge to gather it (or make it by hand) falls as the
stores a chit can reach fill, and is nothing at the ceiling: what a job needs then comes out of the stores instead.
Over its ceiling, grain is ground at a mill, wood burned to charcoal at a kiln and seed sown (sinks), each as an
ordinary shift or plan, and only while the product is under its own ceiling. These are instinct's own choices, and
the plans it drafts as options; a model's explicit plan is not held back.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from ..sim import actions as ACT
from ..sim import food
from ..sim.actions import STATION_NEAR, _useful, plan_bill, village_stores
from ..sim.agent import Agent
from ..sim.items import DESIGNS

# what a village uses of each good, per head and day: measured over 60-day instinct runs (gathered or made, less what
# was left in the stores), rounded up; seeds and flour by what a sowing and a baking take
USE_PER_DAY = {"wood": 1.0, "stone": 0.35, "fiber": 0.3, "clay": 0.25, "sand": 0.2, "charcoal": 0.15, "brick": 0.2,
               "seeds": 0.2, "flour": 0.2}
CEILING_DAYS = 5  # the stores hold enough of a good at this many days of the village's use
GRAIN_DAYS = 4.0  # ...and of grain at this many days of everyone's food: more is ground and baked. Grain is the food
# reserve (flour feeds nobody until baked): at 1 day the mill ground it away and chits starved by stores holding 2-8 food
# (seed 42); at 4 days the 24-seed A/B gained 5.8 and 2.7 discoveries with no starvation of its own
MIN_CEILING = 60  # no ceiling is lower than this: a small village still keeps a building's worth of each good
PLENTY_SIGHT = food.STORE_SIGHT  # the stores, and the homes, a chit counts as its village's (as it judges food)
SINK_WEIGHT = 1.5  # how much a shift that works off a surplus counts among a chit's choices (a bill counts 0.4-2.4)
SINKS = (("grain", "flour", "mill"), ("wood", "charcoal", "kiln"))  # a good over its ceiling, what it becomes, where
SURPLUS_FARM_PER = 3  # with seed over its ceiling a village sows a field per this many chits nearby (else per four)
GLUT_ROOM = 20  # stores holding this much beyond their ceilings are full of plenty, not short of room


def people(world, x: int, y: int) -> int:
    """The chits who live around here: whose home (or who, with none) is within PLENTY_SIGHT."""
    n = 0
    for o in world.agents.values():
        h = world.structures.get(o.home or "")
        ox, oy = (h.x, h.y) if h is not None else (o.x, o.y)
        n += max(abs(ox - x), abs(oy - y)) <= PLENTY_SIGHT
    return n


def _at(a: Agent, at: Optional[Tuple[int, int]]) -> Tuple[int, int]:
    return at if at is not None else (a.x, a.y)


def stock(world, a: Agent, at: Optional[Tuple[int, int]] = None) -> Dict[str, int]:
    """What the village's stores this chit can reach hold (actions.village_stores), around it or around `at`."""
    out: Dict[str, int] = {}
    for p in village_stores(world, *_at(a, at), PLENTY_SIGHT, a):
        for k, n in p.storage.items():
            out[k] = out.get(k, 0) + n
    return out


def ceiling(world, a: Agent, key: str, at: Optional[Tuple[int, int]] = None) -> Optional[float]:
    """How much of a good is enough for the chits living here; None for a good with no ceiling (and for every
    good with actions.PLENTY off: no ceiling, so the urge is whole, nothing is over and there are no sinks)."""
    if not ACT.PLENTY:
        return None
    if key == "grain":
        per_head = GRAIN_DAYS * food.FOOD_PER_DAY / world.item("grain").food
    elif key in USE_PER_DAY:
        per_head = USE_PER_DAY[key] * CEILING_DAYS
    else:
        return None
    return max(float(MIN_CEILING), per_head * people(world, *_at(a, at)))


def plenty(world, a: Agent) -> Dict[str, int]:
    """The goods the stores here hold at or over their ceilings, and how much of each."""
    held = stock(world, a)
    return {k: n for k, n in held.items() if n > 0 and urge(world, a, k, held=held) <= 0}


def urge(world, a: Agent, key: str, at: Optional[Tuple[int, int]] = None, held: Optional[Dict[str, int]] = None) -> float:
    """How much this chit still wants to fetch a good: 1 with none in the stores, falling to 0 at its ceiling (and 1
    for a good that has none)."""
    top = ceiling(world, a, key, at)
    if top is None:
        return 1.0
    have = (stock(world, a, at) if held is None else held).get(key, 0)
    return max(0.0, 1.0 - have / top)


def over(world, a: Agent, key: str, at: Optional[Tuple[int, int]] = None) -> bool:
    """The stores hold this good at or over its ceiling."""
    return urge(world, a, key, at) <= 0.0


def split(world, a: Agent, key: str, n: int) -> Tuple[int, int]:
    """A job needs n of a good: (how many to gather or make fresh, how many to take from the stores). All fresh with
    empty stores, all from the stores at the ceiling, in between by how full they are."""
    held = stock(world, a)
    fresh = min(n, math.ceil(n * urge(world, a, key, held=held)))  # (rounded up: with little in store nothing is taken)
    return fresh, min(n - fresh, held.get(key, 0))


def glut(world, a: Agent) -> bool:
    """The stores here are full of what the village has plenty of: without what lies over the ceilings they would
    have room. Another stockpile would only be filled with more of the same."""
    held = stock(world, a)
    extra = 0.0
    for k, n in held.items():
        top = ceiling(world, a, k)
        if top is not None and n > top:
            extra += n - top
    return extra > GLUT_ROOM


def sinks(world, a: Agent) -> List[Tuple[float, Dict[str, Any]]]:
    """Shifts that work off a surplus: for each good over its ceiling whose product is under its own, a shift at the
    station nearby that turns one into the other, if the shift can run now (plan_bill: this chit knows the recipe,
    the stores by the station hold the good and have room for the product). Grain is ground only while the stores hold
    food enough (food.short comes first): flour feeds nobody until it is baked."""
    out: List[Tuple[float, Dict[str, Any]]] = []
    if a.is_child(world.tick):
        return out
    held = stock(world, a)
    for src, product, station in SINKS:
        if urge(world, a, src, held=held) > 0 or urge(world, a, product, held=held) <= 0:
            continue
        if not _useful(world, product):
            continue  # (as for any shift: flour before anyone can bake it, or charcoal before any smelting, is waste)
        if src == "grain" and food.short(world, a):
            continue
        bill, _ = plan_bill(world, a, {station}, None, product, radius=STATION_NEAR)
        if bill is None or bill.r.key != product:
            continue
        sname, what, old = DESIGNS[bill.st.design].name, world.item_name(product), world.item_name(src)
        out.append((SINK_WEIGHT, {
            "goal": f"work at the {sname} ({what})",
            "thought": f"The stores hold more {old} than we'll use. A shift at the {sname} turns some into {what}.",
            "steps": [{"do": "work", "at": station, "what": product, "target": bill.st.id}]}))
    return out
