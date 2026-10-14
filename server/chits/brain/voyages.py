"""Instinct for trade over the sea (contact games only): take a surplus across in a boat, barter it at the other
village's stores for goods of the same worth, and sail home with them.

At war, a village with a longship sends a raider instead (one at a time): abroad it goes for the stores, a holmgang
of rune, sail and axe with whoever stands there decides whether it gets anything (sim/holmgang.py), and it sails home
in the longship, which waited for it. A village at war with a boat and the idea of a longship builds one.

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
    """A trader from over the sea: barter its load, then sail home. A raider: try the stores, then sail home."""
    if a.origin and a.voyage_intent == "raid":
        if not a.stats.get("pillaged_trip"):
            return {"goal": "raid the stores here", "thought": "The longship is beached. To the stores, and may the runes favour me.",
                    "steps": [{"do": "pillage"}]}
        if a.stats.get("boat_abroad"):
            return {"goal": "sail home with the plunder", "thought": "Back to the ship, and home over the whale-road.",
                    "steps": [{"do": "sail", "intent": "home"}]}
        return None
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


def at_war(world) -> bool:
    return any(r.get("state") == "war" for r in getattr(world, "relations", {}).values())


def raid_plan(world, a: Agent) -> Plan | None:
    """At war, with a longship at hand: one raider at a time sails over to try the other village's stores."""
    if a.origin or a.is_child(world.tick) or not getattr(world, "contact", False) or not at_war(world):
        return None
    last = (getattr(world, "civic", None) or {}).get("raider_sent", -10 ** 9)
    if world.tick - last < SEND_EVERY_DAYS * TICKS_PER_DAY:
        return None
    if any((o.get("agent") or {}).get("voyage_intent") == "raid" for o in getattr(world, "outbox", [])):
        return None
    ship = next((b for b in world.structures_near(a.x, a.y, 60, "longship") if b.functional and world.same_land(a, b)), None)
    if ship is None:
        return None
    return {"goal": "go raiding over the sea",
            "thought": "They are our enemies now. The longship is ready, and the runes are carved.",
            "steps": [{"do": "sail", "target": ship.id, "intent": "raid"}]}


def longship_plan(world, a: Agent) -> Plan | None:
    """At war, with a boat but no longship: build one (a sail and a dragon prow) on the shore."""
    t = world.tick
    memo = world.__dict__.setdefault("_nolongship", {})  # a planner's cache: not saved, not the chit's state
    if (a.origin or a.is_child(t) or not getattr(world, "contact", False) or not a.knows_design("longship")
            or memo.get(a.id, 0) > t or a.reflex_rest.get("nobuild:longship", 0) > t or not at_war(world)):
        return None
    if any(s.design == "longship" for s in world.structures.values()):
        memo[a.id] = t + TICKS_PER_DAY
        return None
    from .instinct import _need_steps

    mats = DESIGNS["longship"].material_map
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        memo[a.id] = t + TICKS_PER_DAY
        return None
    hx, hy = _home_xy(world, a)
    return {"goal": "build a longship",
            "thought": "A boat is for traders. For a war over the sea we need a longship with a sail.",
            "steps": steps[:4] + [{"do": "build", "what": "longship", "near": f"{hx},{hy}"}]}


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    plan = abroad_plan(world, a)
    if plan:
        return [(ABROAD_W, plan)]
    plan = raid_plan(world, a)
    if plan:
        return [(SEND_W + 1.0 - a.traits.get("caution", 0.5), plan)]
    plan = send_plan(world, a) or boat_plan(world, a) or longship_plan(world, a)
    return [(SEND_W + a.traits.get("sociability", 0.5), plan)] if plan else []


def sent(world, who: str = "trader") -> None:
    """A trader (or raider) has set out: the next one waits a few days."""
    world.civic[f"{who}_sent"] = world.tick
