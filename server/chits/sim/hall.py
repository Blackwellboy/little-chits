"""The hall of ancestors: a short biography for every chit that mattered, written from its own record when anyone asks
(views.hall). Nothing here is stored or read back by the world: the record is the chit's (who it was, what it knew
and made, what it did as chief), and the world's own firsts and inventions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .agent import TICKS_PER_DAY, Agent
from .items import DESIGNS

DEEDS_MAX = 8  # the deeds a chit's record keeps: elections won, laws decreed (the newest)
RENOWN, TAUGHT, CHILDREN, OLD = 3.0, 20, 5, 75  # any one of these, or a first or an invention, makes a chit notable


def deed(a: Agent, text: str) -> None:
    a.deeds.append(text)
    del a.deeds[:-DEEDS_MAX]


def _firsts(world, a: Agent) -> List[str]:
    out = []
    for key, f in world.first.items():
        if f.get("by") != a.id or ":" not in key:
            continue
        kind, k = key.split(":", 1)
        if kind == "recipe":
            out.append(f"make {world.item_name(k)}")
        elif kind == "design" and k in DESIGNS:
            out.append(f"build a {DESIGNS[k].name}")
    return out


def _children(world, a: Agent) -> int:
    return sum(1 for o in list(world.agents.values()) + list(world.dead.values()) if a.id in (o.parents or ()))


def notable(world, a: Agent) -> bool:
    age = ((a.died if a.died is not None and a.died >= 0 else world.tick) - a.born) / TICKS_PER_DAY
    return bool(_firsts(world, a) or any(i.get("by") == a.id for i in world.inventions.values()) or a.deeds
                or getattr(a, "renown", 0) >= RENOWN or a.stats.get("taught", 0) >= TAUGHT
                or _children(world, a) >= CHILDREN or age >= OLD)


def biography(world, a: Agent) -> Optional[Dict[str, Any]]:
    """None for a chit that didn't (yet) do anything the village would remember it by."""
    if not notable(world, a):
        return None
    born = max(1, a.born // TICKS_PER_DAY + 1)  # (the first chits arrived grown, "born" before day 1)
    died = a.died // TICKS_PER_DAY + 1 if a.died is not None and a.died >= 0 else None
    age = int(((a.died if died else world.tick) - a.born) / TICKS_PER_DAY)
    firsts = _firsts(world, a)
    inventions = [i["name"] for i in world.inventions.values() if i.get("by") == a.id]
    kids = _children(world, a)
    who = next((o for o in (world.agents.get(p) or world.dead.get(p) for p in (a.parents or ())) if o), None)
    parents = [o.name for o in (world.agents.get(p) or world.dead.get(p) for p in (a.parents or ())) if o]
    did = []
    if firsts:
        did.append(f"was the first in {world.name} to " + _join(firsts[:3]))
    if inventions:
        did.append("invented the " + _join(inventions[:3]))
    did += a.deeds[-3:]
    if a.stats.get("taught", 0) >= 10:
        did.append(f"taught {a.stats['taught']} chits what it knew")
    if kids:
        did.append(f"had {kids} {'child' if kids == 1 else 'children'}")
    span = f"day {born} to {died}" if died else f"born day {born}"
    text = f"{a.name} ({span}, generation {a.generation}){' ' + _join(did) if did else ''}."
    if died:
        text += f" {a.name} died of {a.cause_of_death or 'something unknown'} at {age} days old."
    words = a.lessons[-1] if a.lessons else ""
    if words:
        text += f' In its own words: "{words[:200]}"'
    return {"id": a.id, "name": a.name, "alive": died is None, "born_day": born, "died_day": died, "age": age,
            "cause": a.cause_of_death if died else None, "generation": a.generation, "parents": parents,
            "children": kids, "firsts": firsts, "inventions": inventions, "deeds": list(a.deeds),
            "taught": a.stats.get("taught", 0), "renown": round(getattr(a, "renown", 0.0), 1), "words": words, "text": text,
            "hue": a.hue, "_by": who.id if who else None}


def _join(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
