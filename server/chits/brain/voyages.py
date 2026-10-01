"""Instinct for trade over the sea (contact games only): take a surplus across in a boat, barter it at the other
village's stores for goods of the same worth, and sail home with them.

Boats could only carry a chit away for good. Now a village with a surplus and a boat sends one trader at a time;
abroad, the trader trades at the stores (sim.actions._trade_at_stores: a silent trade, so it works in any culture) and sails home in the
boat it came in, back to the home it left.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..sim.agent import TICKS_PER_DAY, Agent
from ..sim.items import DESIGNS, item_name

Plan = Dict[str, Any]
SURPLUS = 20  # a store holding this much of one thing has some to spare
CARGO = 8
SEND_EVERY_DAYS = 3  # at most one trader leaves a village in this many days
ABROAD_W, SEND_W = 8.0, 0.9


def abroad_plan(world, a: Agent) -> Plan | None:
    """A trader from over the sea: barter its load, then sail home."""
    if not a.origin or a.voyage_intent != "trade":
        return None
    if a.stats.get("traded_trip"):
        if not a.stats.get("boat_abroad"):
            return None  # (a trader from an old save, with no boat waiting: it stays)
        return {"goal": "sail home with the trade goods", "thought": "The trade is made. Home, with what I got.",
                "steps": [{"do": "sail", "intent": "home"}]}
    return {"goal": "trade at the stores here", "thought": "I came over the sea to trade. Let's see what they have.",
            "steps": [{"do": "trade", "at": "stores"}]}


def _home_xy(world, a: Agent) -> Tuple[int, int]:
    h = world.structures.get(a.home or "")
    return (h.x, h.y) if h is not None else (a.x, a.y)


def _surplus(world, a: Agent):
    """(store, the good it has most of) for a store near home with some to spare, else None."""
    hx, hy = _home_xy(world, a)
    for pile in world.structures_near(hx, hy, 25, "stockpile"):
        if not pile.functional or not world.same_land(a, pile):
            continue
        spare = sorted(((n, k) for k, n in pile.storage.items() if n >= SURPLUS and (it := world.item(k)) is not None
                        and not it.tool), reverse=True)
        if spare:
            return pile, spare[0][1]
    return None


def boat_plan(world, a: Agent) -> Plan | None:
    """Something to spare and no boat to carry it: build one on the shore."""
    t = world.tick
    memo = world.__dict__.setdefault("_noboat", {})  # a planner's cache: not saved, not the chit's state
    if (a.origin or a.is_child(t) or not (getattr(world, "contact", False) or getattr(world, "fair_soon", False))
            or not a.knows_design("boat")
            or memo.get(a.id, 0) > t or a.reflex_rest.get("nobuild:boat", 0) > t):
        return None
    if any(s.design == "boat" for s in world.structures.values()) or _surplus(world, a) is None:
        memo[a.id] = t + TICKS_PER_DAY
        return None
    from .instinct import _need_steps

    mats = DESIGNS["boat"].material_map
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        memo[a.id] = t + TICKS_PER_DAY
        return None
    hx, hy = _home_xy(world, a)
    return {"goal": "build a boat to trade over the sea",
            "thought": "We have more than we need, and over the sea they have things we don't. We need a boat.",
            "steps": steps[:4] + [{"do": "build", "what": "boat", "near": f"{hx},{hy}"}]}


def send_plan(world, a: Agent) -> Plan | None:
    """A surplus in the stores near home and a boat at hand: take a load over the sea to trade."""
    if a.origin or a.is_child(world.tick) or not getattr(world, "contact", False):
        return None
    last = (getattr(world, "civic", None) or {}).get("trader_sent", -10 ** 9)  # saved with the village
    if world.tick - last < SEND_EVERY_DAYS * TICKS_PER_DAY:
        return None
    if any((o.get("agent") or {}).get("voyage_intent") == "trade" for o in getattr(world, "outbox", [])):
        return None
    boat = next((b for b in world.structures_near(a.x, a.y, 60, "boat") if b.functional and world.same_land(a, b)), None)
    found = _surplus(world, a) if boat is not None else None
    if found:
        pile, k = found
        return {"goal": f"take {item_name(k)} over the sea to trade",
                "thought": f"We have more {item_name(k)} than we need. Over the sea they may have what we don't.",
                "steps": [{"do": "take", "what": k, "qty": CARGO, "target": pile.id},
                          {"do": "sail", "target": boat.id, "intent": "trade"}]}
    return None


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    plan = abroad_plan(world, a)
    if plan:
        return [(ABROAD_W, plan)]
    plan = send_plan(world, a) or boat_plan(world, a)
    return [(SEND_W + a.traits.get("sociability", 0.5), plan)] if plan else []


def sent(world) -> None:
    """A trader has set out: the next one waits a few days."""
    world.civic["trader_sent"] = world.tick
