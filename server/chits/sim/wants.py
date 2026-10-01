"""Wants and renown (The Sims' wants, a village's regard).

Each adult has one current want, drawn from its nature, its age and what's around it: a brick house of its own, a
copper axe, to be first to discover something, to teach 3 chits, a pet sheep. When the world makes it come true
(the want is checked against what really happened, never against what a chit says) the chit is happier and gains
renown. Renown also comes from discoveries, from work on the village's projects and from teaching. The most renowned
chit is imitated: chits near it lean a little towards what it is doing (brain/civic.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .agent import TICKS_PER_DAY, Agent
from .items import DESIGNS, item_name

WANT_DAYS = 12  # a wish that hasn't come true in this long fades, and another takes its place
WISH_MOOD = 20.0
WISH_RENOWN = 3.0
FAME_MIN = 6.0  # renown needed to be looked up to
RENOWN_DECAY = 0.98  # a day: what you did lately counts most
IMITATE_RADIUS = 15

# event kind -> (renown, who earns it)
_EVENT_RENOWN = {"discovery": 3.0, "invention": 3.0}


def add_renown(world, a: Agent, pts: float) -> None:
    a.renown = round(getattr(a, "renown", 0.0) + pts, 2)


def famous(world) -> Optional[Agent]:
    """The village's most renowned chit, if anyone is renowned enough to be looked up to."""
    best = max(world.agents.values(), key=lambda a: (getattr(a, "renown", 0.0), -a.born), default=None)
    return best if best is not None and best.renown >= FAME_MIN else None


# ---------------------------------------------------------------------------------------------- choosing a want
def _heard_of(world, a: Agent, key: str) -> bool:
    """Whether a chit could know a thing exists: where chits talk, anything the village has made; where they can't,
    only what it has seen or knows how to make itself."""
    return world.flags.get("say") or key in a.familiar or a.knows_recipe(key) or a.knows_design(key)


def _tool_want(world, a: Agent) -> Optional[Tuple[str, str]]:
    for key, cls in (("iron_axe", "axe"), ("copper_axe", "axe"), ("iron_pick", "pick"), ("copper_pick", "pick"),
                     ("stone_axe", "axe"), ("spear", "spear")):
        if f"recipe:{key}" not in world.first or not _heard_of(world, a, key):
            continue
        have = a.best_tool(cls)
        it = world.item(key)
        if have is None or world.item(have).tool_power < it.tool_power:
            art = "an" if item_name(key)[:1] in "aeiou" else "a"
            return key, f"{art} {item_name(key)}"
    return None


def options(world, a: Agent) -> List[Tuple[float, Dict[str, Any]]]:
    """(weight, want) for everything this chit might want now."""
    tr = a.traits
    out: List[Tuple[float, Dict[str, Any]]] = []
    home = world.structures.get(a.home or "")
    if home is None or not home.functional:
        out.append((1.5 + tr.get("caution", 0.5), {"kind": "home", "key": "home", "text": "a home of your own"}))
    elif home.design in ("hut", "longhouse") and ("recipe:brick" in world.first or "design:brick_house" in world.first) \
            and (_heard_of(world, a, "brick") or _heard_of(world, a, "brick_house")):
        out.append((0.8 + tr.get("caution", 0.5) + 0.5 * tr.get("diligence", 0.5),
                    {"kind": "home", "key": "brick_house", "text": "a brick house of your own"}))
    tool = _tool_want(world, a)
    if tool:
        out.append((0.8 + tr.get("diligence", 0.5), {"kind": "item", "key": tool[0], "text": tool[1]}))
    out.append((0.3 + 1.5 * tr.get("curiosity", 0.5),
                {"kind": "first", "key": "", "text": "to be the first to discover something"}))
    if world.flags.get("teach") and sum(1 for k, v in a.knows.items() if v.get("how") != "instinct") >= 2:
        out.append((0.3 + tr.get("sociability", 0.5) + 0.5 * tr.get("generosity", 0.5),
                    {"kind": "stat", "key": "taught", "n": 3, "text": "to teach 3 chits something you know"}))
    if world.flags.get("write") and "recipe:clay_tablet" in world.first:
        out.append((0.2 + 0.8 * tr.get("curiosity", 0.5),
                    {"kind": "stat", "key": "wrote", "n": 1, "text": "to write down something you know on a tablet"}))
    if any(x["kind"] == "sheep" for x in getattr(world, "animals", {}).values()) and "design:pen" in world.first \
            and _heard_of(world, a, "pen"):
        out.append((0.4 + 0.5 * tr.get("generosity", 0.5),
                    {"kind": "stat", "key": "tamed", "n": 1, "text": "a pet sheep"}))
    p = (getattr(world, "civic", None) or {}).get("project")
    from .projects import knows

    if p and p["kind"] == "build" and knows(world, a, p):
        out.append((0.6 + tr.get("diligence", 0.5),
                    {"kind": "build", "key": p["key"], "text": f"to help raise the village's {DESIGNS[p['key']].name}"}))
    if a.age(world.tick) < 40 and home is not None and not any(o.parents and a.id in o.parents for o in world.agents.values()):
        out.append((0.4 + 0.4 * tr.get("sociability", 0.5), {"kind": "child", "key": "", "text": "a child of your own"}))
    return out


def choose(world, a: Agent) -> Dict[str, Any]:
    opts = options(world, a)
    old = a.want.get("text")
    opts = [(w, o) for w, o in opts if o["text"] != old] or opts
    rng = world.rng_for("wants")
    r = rng.random() * sum(w for w, _ in opts)
    pick = opts[-1][1]
    for w, o in opts:
        r -= w
        if r <= 0:
            pick = o
            break
    want = dict(pick, since=world.tick)
    if want["kind"] == "stat":
        want["base"] = a.stats.get(want["key"], 0)
    a.want = want
    return want


# ---------------------------------------------------------------------------------------------- coming true
def fulfilled(world, a: Agent, w: Dict[str, Any]) -> bool:
    kind, key, since = w.get("kind"), w.get("key"), w.get("since", 0)
    if kind == "home":
        home = world.structures.get(a.home or "")
        return home is not None and home.functional and (key == "home" or home.design == key)
    if kind == "item":
        return a.inventory.get(key, 0) > 0
    if kind == "first":
        return any(f.get("by") == a.id and f.get("tick", -1) >= since for f in world.first.values())
    if kind == "stat":
        return a.stats.get(key, 0) - w.get("base", 0) >= w.get("n", 1)
    if kind == "build":
        return any(s.design == key and s.complete and s.completed >= since and a.id in s.builders
                   for s in world.structures.values())
    if kind == "child":
        return a.last_birth_tick >= since
    return False


def fulfil(world, a: Agent) -> None:
    w = a.want
    a.mood = min(100.0, a.mood + WISH_MOOD)
    add_renown(world, a, WISH_RENOWN)
    a.remember(world.tick, f"I got what I wanted: {w['text']}", 4, "wish")
    a.set_emote("🌟", world.tick, 40)
    said = w["text"].replace("your own", "their own").replace("you know", "they know")
    world.emit("wish", f"{a.name} got what they wanted: {said}", 3, a.id, a.x, a.y, want=w.get("kind"), key=w.get("key"))
    a.want = {}


def scene_line(a: Agent) -> str:
    w = getattr(a, "want", None) or {}
    return f"You want: {w['text']}." if w.get("text") else ""


# ---------------------------------------------------------------------------------------------- upkeep
def _scan_renown(world) -> None:
    """Renown for what the chronicle shows: discoveries, inventions, first buildings, teaching."""
    last = world.civic.get("renown_seq", 0)
    fresh = []
    for ev in reversed(world.events):
        if ev.seq <= last:
            break
        fresh.append(ev)
    world.civic["renown_seq"] = world.seq
    for ev in reversed(fresh):
        if ev.kind in _EVENT_RENOWN and ev.actor in world.agents:
            pts = _EVENT_RENOWN[ev.kind]
            if ev.kind == "discovery" and ev.data.get("how") == "insight":
                pts = 1.0  # an idea that came from what it knew, not a find
            add_renown(world, world.agents[ev.actor], pts)
        elif ev.kind == "built" and ev.data.get("first"):
            for aid in ev.data.get("builders") or []:
                if aid in world.agents:
                    add_renown(world, world.agents[aid], 1.0)
        elif ev.kind == "learned" and ev.data.get("how") == "taught" and ev.data.get("source") in world.agents:
            add_renown(world, world.agents[ev.data["source"]], 1.0)


def tick(world) -> None:
    _scan_renown(world)
    if world.tick % 30:
        return
    for a in list(world.agents.values()):
        if a.want and fulfilled(world, a, a.want):
            fulfil(world, a)


def new_day(world) -> None:
    t = world.tick
    for a in world.agents.values():
        a.renown = round(getattr(a, "renown", 0.0) * RENOWN_DECAY, 2)
        if a.is_child(t):
            continue
        if not a.want or t - a.want.get("since", t) > WANT_DAYS * TICKS_PER_DAY:
            choose(world, a)
