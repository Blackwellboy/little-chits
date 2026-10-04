"""Research at libraries (RimWorld's research bench): study the tablets, and the village gets ideas.

A chit that studies at a library holding tablets earns insight for its village: more with practice ("scholar"
skill), as the village's scholar, and the more tablets there are to study. When the village's insight crosses a
threshold its scholars have a HINT about one thing nobody has made yet, from things someone in the village has
handled. The hint is worded through properties, never as the recipe itself: "something that burns very hot, with
something that melts in great heat, at a furnace, might make something new". Chits still have to work out which
things those are, and try them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .agent import Agent
from .items import ITEMS, RECIPES, STORES, normalize_design
from .items import LIBRARIES

HINT_FIRST = 8.0  # insight for the first hint...
HINT_STEP = 4.0  # ...and each later one needs this much more
HINT_CAP = 24.0
ACTIVE_HINTS = 2  # hints still waiting to come true, at most
STUDY_WORK = 10.0  # ticks of study per session

_VAGUE = {"tool", "small", "light", "hard", "flat", "edible", "container", "metal", "raw"}
_VERBISH = {"can", "burns", "melts", "hardens", "holds", "conducts", "cuts", "breaks", "reaches", "pulls", "turns",
            "makes", "glows", "rolls", "spins"}
_NUM = {2: "two of ", 3: "three of "}
_STUDY_WORDS = {"library", "tablets", "tablet", "books", "research", "scholars", "knowledge", "here"}


def threshold(world) -> float:
    return min(HINT_CAP, HINT_FIRST + HINT_STEP * world.civic.get("hints_given", 0))


def _prop_count(p: str) -> int:
    return sum(1 for it in ITEMS.values() if p in it.props)


def clue(key: str) -> str:
    """The property that best hints at an item: shared by a few things (a real puzzle), not by none or by many."""
    props = [p for p in ITEMS[key].props if p not in _VAGUE] or list(ITEMS[key].props)
    return min(props, key=lambda p: (abs(_prop_count(p) - 2), -len(p)))


def something(p: str, n: int = 1) -> str:
    head = _NUM.get(n, "")
    if p.split(" ", 1)[0] in _VERBISH:
        return f"{head}something that {p}"
    if " " in p and not p.startswith("very "):
        return f"{head}something with {p}"
    return f"{head}something {p}"


def hint_text(parts: List[Tuple[str, int]], station: Optional[str]) -> str:
    bits = [something(p, n) for p, n in parts]
    what = bits[0] if len(bits) == 1 else bits[0] + ", with " + " and ".join(bits[1:])
    at = f", at a {station}," if station else ""
    return f"Scholars at the library think {what}{at} might make something new."


def village_handled(world) -> set:
    seen: set = set()
    for a in world.agents.values():
        seen |= set(a.familiar)
    for s in world.structures.values():
        if s.design in STORES and s.functional:  # (warehouses too)
            seen |= {k for k, n in s.storage.items() if n > 0}
    return seen


def candidates(world, a: Optional[Agent] = None) -> List[str]:
    """Undiscovered base recipes whose every input someone in the village has handled: the project's target first
    (the project of the scholar's own village), then those that can be made at a station the village has, simplest
    first."""
    from . import projects

    known = {k.split(":", 1)[1] for a in world.agents.values() for k in a.knows if k.startswith("recipe:")}
    handled = village_handled(world)
    active = {h["recipe"] for h in world.civic.get("hints", []) if not h.get("found")}
    have = set()
    for s in world.structures.values():
        have |= s.stations()
    p = (projects.current(world, a) if a is not None else projects.of(world)) or {}
    target = p.get("key") if p.get("kind") == "discover" else None
    out = []
    for k, r in RECIPES.items():
        if k in known or k in active:
            continue
        if not all(i in handled for i, _ in r.inputs):
            continue
        out.append(((k != target), (r.station is not None and r.station not in have), len(r.inputs), r.work, k))
    return [c[-1] for c in sorted(out)]


def give_hint(world, a: Optional[Agent]) -> Optional[Dict[str, Any]]:
    cands = candidates(world, a)
    if not cands:
        return None
    k = cands[0]
    r = RECIPES[k]
    parts = [(clue(i), n) for i, n in r.inputs]
    h = {"id": f"h{world.civic.get('hints_given', 0) + 1}", "recipe": k, "parts": [list(x) for x in parts],
         "station": r.station, "text": hint_text(parts, r.station), "tick": world.tick, "by": a.id if a else "",
         "by_name": a.name if a else "", "found": 0}
    world.civic.setdefault("hints", []).append(h)
    world.civic["hints_given"] = world.civic.get("hints_given", 0) + 1
    if a is not None:
        from .wants import add_renown

        add_renown(world, a, 2.0)
        a.remember(world.tick, f"Studying at the library, an idea came to me: {h['text'].split('think ', 1)[-1]}", 4, "learn")
        a.set_emote("💡", world.tick, 30)
    world.emit("hint", f"{a.name if a else 'The scholars'} had an idea at the library: {h['text']}", 4,
               a.id if a else None, a.x if a else None, a.y if a else None, hint=h["id"], recipe=k)
    return h


def add_insight(world, a: Optional[Agent], pts: float) -> Optional[Dict[str, Any]]:
    world.civic["insight"] = world.civic.get("insight", 0.0) + pts
    need = threshold(world)
    active = [h for h in world.civic.get("hints", []) if not h.get("found")]
    if world.civic["insight"] < need or len(active) >= ACTIVE_HINTS:
        return None
    h = give_hint(world, a)
    if h is not None:
        world.civic["insight"] -= need
    return h


def study_gain(world, a: Agent, tablets: int) -> float:
    from .buildings import study_mult

    scholar = 1.5 if a.job == "scholar" else 1.0
    return round(scholar * (1.0 + a.skill("scholar") / 50.0) * (1.0 + 0.1 * min(10, tablets)) * study_mult(world, a), 2)


def active_hints(world, a: Optional[Agent] = None) -> List[Dict[str, Any]]:
    """Hints not yet come true. Where chits talk, word gets round; elsewhere only those who study know them."""
    hs = [h for h in (getattr(world, "civic", None) or {}).get("hints", []) if not h.get("found")]
    if a is not None and not world.flags.get("say") and not a.stats.get("studied"):
        return []
    return hs


def scene_lines(world, a: Agent) -> List[str]:
    return [f"Scholars' hint: {h['text'].split('think ', 1)[-1]}" for h in active_hints(world, a)[-ACTIVE_HINTS:]]


def tick(world) -> None:
    for h in world.civic.get("hints", []):
        if h.get("found"):
            continue
        kk = f"recipe:{h['recipe']}"
        finder = min((a for a in world.agents.values() if kk in a.knows), key=lambda a: a.knows[kk]["tick"], default=None)
        if finder is not None:
            h["found"] = world.tick
            world.emit("hint_true", f"The scholars' idea came true: {finder.name} found what they had hinted at", 3,
                       finder.id, finder.x, finder.y, hint=h["id"], recipe=h["recipe"])
    del world.civic["hints"][:-20]


# ---------------------------------------------------------------------------------------------- the verb
def do_study(world, a: Agent, step: Dict[str, Any], s: Dict[str, Any]) -> str:
    from .actions import DONE, RUNNING, _do_inspect, _goto_structure, _work

    if s.get("inspect"):
        return _do_inspect(world, a, step, s)
    lib = world.structures.get(s.get("lib") or "")
    if lib is None:
        ref = str(step.get("target") or step.get("at") or step.get("what") or "").strip()
        st = world.structures.get(ref)
        if st is not None and st.design in LIBRARIES:
            lib = st
        elif ref and ref.lower().split(" ")[-1] not in _STUDY_WORDS and normalize_design(ref) not in LIBRARIES:
            s["inspect"] = True  # "study the hut", "study Nul", "study my pot": that's inspecting it
            return _do_inspect(world, a, step, s)
        else:
            lib = next((x for x in world.structures_near(a.x, a.y, 30, "library") if x.functional
                        and any(t in world.tablets for t in x.shelf) and world.same_land(a, x)), None)
        if lib is None and not ref:
            s["inspect"] = True  # no library to study at: look for something else to study, as "study" always did
            return _do_inspect(world, a, step, s)
        if lib is None:
            return "there is no library with tablets nearby to study at"
        s["lib"] = lib.id
    if not lib.functional:
        return "the library has fallen into ruin"
    tablets = sum(1 for t in lib.shelf if t in world.tablets)
    if not tablets:
        return "the library holds no tablets to study"
    mv = _goto_structure(world, a, s, lib)
    if mv == "blocked":
        return "couldn't reach the library"
    if mv != "arrived":
        return RUNNING
    a.activity = "studying at the library"
    a.set_emote("📚", world.tick, 3)
    if not _work(a, 1.0, STUDY_WORK):
        return RUNNING
    gain = study_gain(world, a, tablets)
    a.practice("scholar", 1.0)
    a.bump("studied")
    h = add_insight(world, a, gain)
    if h is not None:
        s["note"] = f"Studied the {tablets} tablets at the library, and had an idea: {h['text'].split('think ', 1)[-1]}"
    else:
        s["note"] = (f"Studied the {tablets} tablets at the library (the village's scholars are "
                     f"{world.civic['insight']:.0f}/{threshold(world):.0f} of the way to a new idea)")
    return DONE
