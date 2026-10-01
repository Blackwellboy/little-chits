"""From a world to rows: one tidy row per sampled day, and a summary at the end. Only simulator facts."""

from __future__ import annotations

from typing import Any, Dict

from ..sim.agent import TICKS_PER_DAY

HOMES = ("hut", "brick_house", "longhouse", "two_storey_house")
USEFUL = ("well", "granary", "mill", "smithy", "watchtower", "school", "bell_tower", "bridge", "warehouse")


def row(w, founders: int = 0) -> Dict[str, Any]:
    """`founders`: the chits the world began with (births = everyone who ever lived beyond them)."""
    st = w.stats()
    b = st["by_design"]
    store: Dict[str, int] = {}
    for s in w.structures.values():
        for k, n in s.storage.items():
            store[k] = store.get(k, 0) + n
    food = sum(n for k, n in store.items() if (it := w.item(k)) is not None and it.food > 0)
    try:
        from ..sim import pioneers as PI

        villages = len(PI.villages(w))
    except Exception:
        villages = st.get("settlements", 0)
    return {
        "day": w.tick // TICKS_PER_DAY, "population": st["population"], "deaths": st["deaths"], "era": w.era()[0],
        "discoveries": st["discoveries"], "knowledge": st["knowledge"], "structures": st["structures"],
        "homes": sum(b.get(h, 0) for h in HOMES), "farms": b.get("farm", 0), "useful": sum(b.get(k, 0) for k in USEFUL),
        "stockpiles": b.get("stockpile", 0) + b.get("warehouse", 0), "food": food,
        "copper": store.get("copper", 0), "iron": store.get("iron", 0), "tablets": st["tablets"],
        "villages": villages, "generations": st["generations"], "tunnels": len(getattr(w, "tunnels", {}) or {}),
        "loose": sum(n for pile in getattr(w, "ground", {}).values() for k, n in pile.items() if k != "_t"),
        "forgotten": w.lifetime("forgotten"),  # (whole run: the event window holds only the last 4,000 events)
        "births": max(0, st["population"] + st["deaths"] - founders) if founders else 0,
    }



def lifetime(w) -> Dict[str, Any]:
    """Persistent whole-run event counters (F6), with an explicit coverage boundary for older migrated saves."""
    return {
        "since_tick": int(getattr(w, "tallies_since", 0)),
        "through_tick": int(w.tick),
        "complete_from_start": int(getattr(w, "tallies_since", 0)) == 0,
        "events": dict(sorted((str(k), int(v)) for k, v in getattr(w, "tallies", {}).items())),
    }

def summary(w, daily, founders: int = 0, blind: bool = False) -> Dict[str, Any]:
    from . import propositions

    last = row(w, founders)
    return {"final": last, "peak_population": max([r["population"] for r in daily] + [last["population"]]),
            "propositions": propositions.snapshot(w, blind=blind), "lifetime": lifetime(w)}
