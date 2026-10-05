"""Preventable deaths, recorded as they happen in a Lab run (the report card in docs/research/model-programme.md).

A starvation is preventable when, at the moment of death, a working store on the chit's own land within
PREVENTABLE_NEAR tiles held food: the same rule as tools/harness/probe.py, which stays as it is because it must run
against older trees. Whether a chit lived or died, its world can't say afterwards: so the Lab attaches this to every
run's world before the first tick and counts as it goes.
"""

from __future__ import annotations

from typing import Any, Dict, List

PREVENTABLE_NEAR = 30  # tiles (tools/harness/probe.py)


def food_in(world, s) -> int:
    """Food a chit could take from this store (none from one that isn't functional)."""
    if not s.functional:
        return 0
    return sum(n for k, n in s.storage.items() if n > 0 and (it := world.item(k)) is not None and it.food > 0)


def preventable(world, a) -> bool:
    return any(food_in(world, s) and world.same_land(a, s)
               for s in world.structures_near(a.x, a.y, PREVENTABLE_NEAR, "stockpile"))


def attach(world) -> List[Dict[str, Any]]:
    """Watch a world's deaths; returns the list each starvation's record is added to (also world._starvations)."""
    found: List[Dict[str, Any]] = []
    world.__dict__["_starvations"] = found

    def on_event(ev) -> None:
        if ev.kind == "death" and (ev.data or {}).get("cause") == "starvation":
            a = world.dead.get(ev.actor)
            if a is not None:
                found.append({"id": a.id, "day": world.tick // 240, "preventable": preventable(world, a)})

    world.listeners.append(on_event)
    return found


def count(world) -> int:
    """Preventable starvations so far (None-safe: a world nobody attached to has none counted)."""
    return sum(1 for s in world.__dict__.get("_starvations", ()) if s["preventable"])
