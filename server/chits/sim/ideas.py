"""Invented buildings: a chit's own idea for a building, built as a named variant of a design its world already has.

A world-local *design* would need every lookup of the shared DESIGNS table to go through the world first
(docs/INVENTION_STRUCTURES.md counts them). A variant needs none of that: the structure it puts up has the design of
an existing building (its "base"), so every rule keyed by a design's name treats it as that building, and only its
name, its materials and who thought of it are the chit's own. They live in `world.building_ideas`, never in DESIGNS,
so twin worlds never share one.

How an invention becomes one (`conceive`, from sim.actions._do_invent): the thing itself is a building (its name ends
in one, "Wind Hall", or its purpose starts with one, "a granary for..."), the words of both choose what the building is
for (the one they say most about), and that chooses the base: the most advanced design of that kind somebody in this
world already knows. Its parts must be building materials; they say what it is built from, scaled up until it takes at
least as much as the base does (and a base material none of them is, like a brick house's bricks, is still needed):
never cheaper.

The inventor learns "idea:<key>", which is taught, written and read like any other knowledge (and whoever helps build
one learns it), and `build` takes the idea's name for whoever knows it.
"""

from __future__ import annotations

import math
import re
import zlib
from typing import Any, Dict, List, Optional, Tuple

from .invent import _mention
from .items import DESIGNS, normalize_design

INVENTED_BUILDINGS = True  # (off in tests/identity_runner.py: a world where nobody invents is unchanged either way)
INSTINCT_SHARE = 2  # instinct builds a known idea instead of its base one time in this many, when it can afford both

# (what it is for, nouns that name a building of that kind, words that only say what it is for, bases best first)
KINDS: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("worship", ("shrine", "temple", "altar", "chapel", "sanctuary"),
     ("worship", "pray", "prayer", "holy", "sacred", "god", "gods", "spirit", "spirits"), ("shrine",)),
    ("learning", ("library", "school", "academy", "schoolhouse", "archive"),
     ("learn", "teach", "study", "book", "read", "write", "knowledge", "lesson"), ("library", "school")),
    ("trade", ("market", "marketplace", "bazaar", "plaza", "square"),
     ("trade", "barter", "sell", "buy", "meet", "meeting"), ("market", "plaza")),
    ("making", ("workshop", "smithy", "forge", "workhouse"), ("craft", "make", "tools", "work"), ("workshop",)),
    ("storage", ("storehouse", "shed", "depot", "stockpile", "warehouse", "larder", "cellar"),
     ("store", "storage", "keep", "stock", "hoard"), ("warehouse", "stockpile")),
    ("food", ("granary", "barn", "farmstead", "orchard", "garden", "field"),
     ("food", "grow", "crop", "grain", "harvest", "farm", "sow"), ("granary", "farm")),
    ("defence", ("tower", "watchtower", "wall", "fort", "fortress", "palisade", "stockade", "lookout", "rampart"),
     ("defend", "defence", "defense", "guard", "watch", "protect", "wolf", "wolves"), ("watchtower", "palisade")),
    ("shelter", ("shelter", "hut", "house", "home", "hall", "lodge", "cabin", "dwelling", "longhouse", "cottage",
                 "tent"), ("live", "sleep", "rest", "family", "roof"),
     ("two_storey_house", "brick_house", "longhouse", "hut")),
    ("warmth", ("hearth", "firepit", "bonfire", "fireplace"), ("warm", "warmth", "heat", "fire", "cook"),
     ("campfire",)),
    ("light", ("beacon", "lamppost", "streetlight"), ("light", "glow", "bright"), ("street_lamp",)),
)
# what a building can be made of: what some building already is
MATERIALS = frozenset(m for d in DESIGNS.values() for m, _ in d.materials)


def on(world) -> bool:
    return INVENTED_BUILDINGS and bool(getattr(world, "building_ideas", None))


NOUNS = tuple(n for _, nouns, _, _ in KINDS for n in nouns)
ARTICLES = ("a", "an", "the", "our", "my", "their", "one")


def _a_building(word: str) -> bool:
    return any(_mention(word, n) for n in NOUNS)


def is_building(name: str, purpose_text: str) -> bool:
    """Is the thing itself a building? Its name ends in one ("Wind Hall", "Ash's Tower"), or its purpose starts with one
    ("a hall to keep the wind out"). Only naming one is not enough: a "Hut Heater", "something to heat the hut", is a
    thing for a hut."""
    words = re.findall(r"[a-z]+", str(name).lower().replace("'s", ""))
    said = re.findall(r"[a-z]+", str(purpose_text).lower())
    while said and said[0] in ARTICLES:
        said = said[1:]
    return bool(words and _a_building(words[-1])) or bool(said and _a_building(said[0]))


def _kinds(text: str) -> List[Tuple[str, Tuple[str, ...]]]:
    """The kinds of building a text names, the one it says most about first, then the one it names earliest."""
    found = []
    for i, (kind, nouns, words, bases) in enumerate(KINDS):
        at = [m.start() for w in nouns + words if (m := _mention(text, w))]
        if at:
            found.append((-len(at), min(at), i, kind, bases))
    return [(kind, bases) for _, _, _, kind, bases in sorted(found)]


def _known_here(world, base: str) -> bool:
    k = f"design:{base}"
    return world.rules.allows_knowledge(k) and any(k in o.knows for o in world.agents.values())


def archetype(world, name: str, purpose_text: str) -> Optional[Tuple[str, str]]:
    """(what it is for, its base design) for an invention that is a building, or None: it names no building, or none
    of the kinds it names has a base anybody here knows (it is then judged as an item, as before)."""
    if not is_building(name, purpose_text):
        return None
    for kind, bases in _kinds(f"{name} {purpose_text}".lower()):
        base = next((b for b in bases if b in DESIGNS and _known_here(world, b)), None)
        if base:
            return kind, base
    return None


def materials(bag: Dict[str, int], base: str) -> Dict[str, int]:
    """What the building takes: the base's own materials that none of the parts is, and the parts, scaled up until the
    whole is at least the base's."""
    own = {m: n for m, n in DESIGNS[base].materials if m not in bag}
    need = sum(n for _, n in DESIGNS[base].materials) - sum(own.values())
    scale = max(1, math.ceil(need / max(1, sum(bag.values()))))
    out = {k: n * scale for k, n in sorted(bag.items())}
    out.update(own)
    return out


def by_name(world, text: Any) -> Optional[Dict[str, Any]]:
    """A building idea of this world, by key or name (case-insensitive, "a"/"the" left off)."""
    ideas = getattr(world, "building_ideas", None)
    if not INVENTED_BUILDINGS or not ideas or not text:
        return None
    s = str(text).strip()
    if s.startswith("idea:"):
        s = s[5:]
    if s in ideas:
        return ideas[s]
    low = s.lower()
    for p in ("a ", "an ", "the "):
        if low.startswith(p) and low[len(p):]:
            low = low[len(p):]
    return next((i for i in ideas.values() if i["name"].lower() == low), None)


def conceive(world, a, bag: Dict[str, int], name: str, purpose_text: str):
    """An invention that is a building: None when it is not one (the item judge decides), a refusal (str), or
    (the idea's record, whether it is new): the same parts for the same base are the idea someone here had already."""
    pick = archetype(world, name, purpose_text)
    if pick is None:
        return None
    kind, base = pick
    odd = [k for k in sorted(bag) if k not in MATERIALS]
    if odd:
        return (f"a building can't be made of {', '.join(world.item_name(k) for k in odd)}: build it from what "
                f"buildings are made of (wood, stone, fiber, cord, clay, brick...)")
    same = next((i for i in world.building_ideas.values() if i["base"] == base and i["inputs"] == bag), None)
    if same is not None:
        return same, False
    key = f"idea_{world.id.lower()}_{len(world.building_ideas) + 1}"
    rec = {"key": key, "name": name, "base": base, "purpose": kind, "purpose_text": purpose_text,
           "inputs": dict(bag), "materials": materials(bag, base), "by": a.id, "by_name": a.name, "tick": world.tick}
    world.building_ideas[key] = rec
    return rec, True


def load(raw: Any) -> Dict[str, Dict[str, Any]]:
    """Building ideas from a save (untrusted): one without a name, a base this build knows or its materials is left
    out, and a structure built as it is then simply its base."""
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in (raw or {}).items() if isinstance(raw, dict) else ():
        if not isinstance(v, dict):
            continue
        mats = v.get("materials")
        if not (isinstance(v.get("name"), str) and v.get("base") in DESIGNS and isinstance(mats, dict) and mats
                and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in mats.values())):
            continue
        out[str(k)] = {**v, "key": str(k), "materials": {str(m): n for m, n in mats.items()},
                       "inputs": dict(v.get("inputs") or {}), "by_name": str(v.get("by_name") or "someone")}
    return out


def mark(world, st, idea: Dict[str, Any]) -> None:
    """A site that is going up as this idea: its name, and the idea's materials in place of the base's."""
    st.idea, st.title = idea["key"], idea["name"]
    st.needs = dict(idea["materials"])
    world.dirty_struct.add(st.id)


def name_of(st) -> str:
    """What a structure is called: its own name for an invented one, else its design's."""
    return st.title or DESIGNS[st.design].name


def built(world, st, who: str) -> Optional[Tuple[str, bool]]:
    """An invented building's completion: its text ("Ash built the first Wind Hall, Rible's idea") and whether it is
    the first of that idea; None for a structure that is not one."""
    idea = world.building_ideas.get(st.idea) if st.idea else None
    if idea is None:
        return None
    first = "built" not in idea
    if first:
        idea["built"], idea["built_by"] = world.tick, who
        return f"{who} built the first {idea['name']}, {idea['by_name']}'s idea", True
    return f"{who} finished a {idea['name']}", False


def describe(world, idea: Dict[str, Any], a) -> str:
    """One line for a chit that knows it: what it is, and what it takes (what it is a kind of only when the chit knows
    that building too: a chit is told the name of nothing it hasn't found)."""
    mats = ", ".join(f"{n} {world.item_name(m)}" for m, n in idea["materials"].items())
    kind = f"a kind of {DESIGNS[idea['base']].name}; " if a.knows_design(idea["base"]) else ""
    return f"{idea['name']} ({idea['by_name']}'s idea: {kind}{mats})"


def known(world, a) -> List[Dict[str, Any]]:
    """The building ideas this chit knows, oldest first."""
    if not on(world):
        return []
    return [i for k, i in world.building_ideas.items() if f"idea:{k}" in a.knows]


def _affords(a, mats: Dict[str, int]) -> bool:
    return all(a.inventory.get(k, 0) >= n for k, n in mats.items())


def instead(world, a, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Instinct's plan with a known idea built in place of its base, when the chit carries enough for both, one time in
    INSTINCT_SHARE (by a hash of who and when: nothing random is drawn, so a world without ideas is unchanged)."""
    mine = known(world, a)
    if not mine:
        return steps
    out = []
    for s in steps:
        what = s.get("what") if s.get("do") == "build" and not s.get("site") else None
        base = normalize_design(what) if isinstance(what, str) else None
        pick = next((i for i in mine if i["base"] == base), None) if base else None
        if pick and _affords(a, DESIGNS[base].material_map) and _affords(a, pick["materials"]) \
                and zlib.crc32(f"{a.id}:{world.tick}:{pick['key']}".encode()) % INSTINCT_SHARE == 0:
            s = dict(s, what=pick["name"])
        out.append(s)
    return out
