"""Knowledge that outlives its keepers.

World A once knew iron; everyone who knew it died, and at day 597 its village had to discover iron again before it
could build a forge. Now the world notices when a thing the village has made is known by one living chit, and that
chit is old: it says so (an event, and a line in that chit's scene), and instinct puts passing it on first, by
whatever the culture allows: teaching a younger chit, writing it on a tablet, or (where chits can't talk) making it
where others can watch. When the last one who knew a thing dies, the world says the village has forgotten it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .agent import Agent

OLD = 0.75  # of its lifespan: a last keeper this old starts passing the thing on


def keepers(world) -> Dict[str, List[Agent]]:
    """Recipes the village has made (world.first) -> the living chits who know them."""
    out: Dict[str, List[Agent]] = {}
    for a in world.agents.values():
        for k in a.knows:
            if k.startswith("recipe:") and k in world.first:
                out.setdefault(k, []).append(a)
    return out


def old(world, a: Agent) -> bool:
    return world.tick - a.born >= OLD * a.lifespan


def at_risk(world) -> List[Tuple[str, Agent]]:
    """(recipe key, its only keeper) for what only one living chit knows, oldest keepers first."""
    out = [(k, ks[0]) for k, ks in keepers(world).items() if len(ks) == 1]
    return sorted(out, key=lambda kv: (kv[1].born, kv[0]))


def last_of(world, a: Agent) -> List[str]:
    """What only this chit knows, if it is old enough that it should pass it on now."""
    if not old(world, a):
        return []
    return sorted(k for k, keeper in at_risk(world) if keeper is a)


def daily(world) -> None:
    """Once a day: say (once) when an old chit is the last one who knows how to make something."""
    warned = world.civic.setdefault("lore_warned", [])
    for k, a in at_risk(world):
        tag = f"{k}|{a.id}"
        if tag in warned or not old(world, a):
            continue
        warned.append(tag)
        what = world.item_name(k.split(":", 1)[1])
        world.emit("last_keeper", f"Only {a.name}, old now, still knows how to make {what}", 3, a.id, a.x, a.y,
                   knowledge=k)
    del warned[:-200]


def on_death(world, a: Agent) -> None:
    """The last chit who knew a thing has died: the village has forgotten it."""
    left = keepers(world)
    for k in sorted(a.knows):
        if k.startswith("recipe:") and k in world.first and not left.get(k):
            what = world.item_name(k.split(":", 1)[1])
            world.emit("forgotten", f"With {a.name} gone, nobody in {world.name} remembers how to make {what}", 4,
                       a.id, a.x, a.y, knowledge=k)


def scene_line(world, a: Agent) -> Optional[str]:
    """The last keeper's own reminder, in the words its culture allows (none where the rules leave lore alone)."""
    if not world.rules.lore_rescue:
        return None
    keys = last_of(world, a)
    if not keys:
        return None
    what = ", ".join(world.item_name(k.split(":", 1)[1]) for k in keys[:3])
    if world.flags.get("teach"):
        how = "teach it to someone younger"
    elif world.flags.get("write"):
        how = "write it on a tablet"
    else:
        how = "make it where others can watch you"
    return f"You are the last one alive who knows how to make {what}, and you are old: {how} before it is lost."
