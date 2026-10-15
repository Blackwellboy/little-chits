"""Invented buildings: a chit's own idea for a building, built as a named variant of a design its world already has.

A world-local *design* would need every lookup of the shared DESIGNS table to go through the world first
(docs/INVENTION_STRUCTURES.md counts them). A variant needs none of that: the structure it puts up has the design of
an existing building (its "base"), so every rule keyed by a design's name treats it as that building, and only its
name, its materials and who thought of it are the chit's own. They live in `world.building_ideas`, never in DESIGNS,
so twin worlds never share one.

How an invention becomes one (`conceive`, from sim.actions._do_invent): the thing itself is a building (its name ends
in one, "Wind Hall", or its purpose starts with one, "a granary for..."), the words of both choose what the building is
for (the one they say most about), and that chooses the base: the most advanced design of that kind somebody in this
world already knows. Its parts must be building materials; they say what it is built from, scaled up until they are as
many pieces as the base takes, and it never takes less of any of the base's own materials than the base does (a brick
house's bricks stay): never cheaper, in any material.

The inventor learns "idea:<key>", which is taught, written and read like any other knowledge (and whoever helps build
one learns it), and `build` takes the idea's name for whoever knows it.
"""

from __future__ import annotations

import math
import re
import zlib
from typing import Any, Dict, List, Optional, Tuple

from .invent import _mention
from . import buildings as BLD
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
    """What the building takes: the parts, scaled up until they alone are as many pieces as the base takes, and never
    less of any of the base's own materials than the base needs (scaling only adds: its bricks or glass can't be
    swapped for wood). The parts come first, the most of them first (what it is mended with), then the base's rest."""
    base_mats = DESIGNS[base].material_map
    scale = max(1, math.ceil(sum(base_mats.values()) / max(1, sum(bag.values()))))
    out = {k: max(n * scale, base_mats.get(k, 0)) for k, n in sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))}
    for m, n in DESIGNS[base].materials:
        out.setdefault(m, n)
    return out


def plain(name: Any) -> str:
    """A name as it is compared: lower case, single spaces, a leading "a", "an" or "the" left off."""
    low = " ".join(str(name or "").lower().split())
    for p in ("a ", "an ", "the "):
        if low.startswith(p) and low[len(p):]:
            return low[len(p):]
    return low


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
    low = plain(s)  # (both sides alike: "The Wind Hall" is found as "wind hall", "a wind hall" or itself)
    return next((i for i in ideas.values() if plain(i["name"]) == low), None)


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
    key = _new_key(world)
    rec = {"key": key, "name": name, "base": base, "purpose": kind, "purpose_text": purpose_text,
           "inputs": dict(bag), "materials": materials(bag, base), "by": a.id, "by_name": a.name, "tick": world.tick}
    world.building_ideas[key] = rec
    return rec, True


def _new_key(world) -> str:
    """A key no idea of this world has had: from the world's own counter (saved with its counters), past every key
    still in use by an idea or a structure (a save from before the counter, or one whose idea was left out on load:
    a structure built as it must never be renamed by a new idea)."""
    prefix = f"idea_{world.id.lower()}_"
    used = set(world.building_ideas) | {st.idea for st in world.structures.values() if st.idea}
    seen = [int(k[len(prefix):]) for k in used if k.startswith(prefix) and k[len(prefix):].isdigit()]
    n = max([world.counters.get("idea", 0)] + seen) + 1
    while f"{prefix}{n}" in used:
        n += 1
    world.counters["idea"] = n
    return f"{prefix}{n}"


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


def title_of(st) -> str:
    """An invented building's own name, or "" (also with the switch off: it is then simply its base)."""
    return st.title if INVENTED_BUILDINGS else ""


def idea_of(world, st) -> Optional[Dict[str, Any]]:
    """The idea a structure was built as, if it is one of this world's and the switch is on."""
    return world.building_ideas.get(st.idea) if INVENTED_BUILDINGS and st.idea else None


def name_of(st) -> str:
    """What a structure is called: its own name for an invented one, else its design's."""
    return title_of(st) or DESIGNS[st.design].name


def plan_of(world, st) -> List[Tuple[str, int]]:
    """What a structure is built (and mended) from: its idea's materials, else its design's."""
    idea = idea_of(world, st)
    return list(idea["materials"].items()) if idea else list(DESIGNS[st.design].materials)


def teachable(world, k: str) -> bool:
    """Can this knowledge be taught or written here? An idea only when it is one of this world's (one a chit brought
    over the sea names a building nobody here could find)."""
    return not k.startswith("idea:") or by_name(world, k) is not None


def built(world, st, who: str) -> Optional[Tuple[str, bool]]:
    """An invented building's completion: its text ("Ash built the first Wind Hall, Rible's idea") and whether it is
    the first of that idea; None for a structure that is not one."""
    idea = idea_of(world, st)
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
        if pick and BLD.upgrade_instead(world, a, base, s):  # (a planned upgrade of its home stays one)
            pick = None
        if pick and _affords(a, DESIGNS[base].material_map) and _affords(a, pick["materials"]) \
                and zlib.crc32(f"{a.id}:{world.tick}:{pick['key']}".encode()) % INSTINCT_SHARE == 0:
            s = dict(s, what=pick["name"])
        out.append(s)
    return out
