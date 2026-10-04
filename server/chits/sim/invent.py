"""Open invention (T20): a chit proposes a name and a purpose, and the world judges it by physical law.

Cognition proposes, the simulator decides. A purpose is only met when the inputs can do what it needs.

Two engines, chosen by COMPOSE below:
- composition (F34, the one in use): what each part can do (items.FUNCTIONS) is put through a table of rules (RULES)
  that says everything the parts can be, at the station they are made at. The purpose text only chooses among those
  readings. What the thing then does is a number that comes from its materials (the table under "how strong").
- keywords (T20's first engine, kept for comparison): the first purpose whose keyword the text holds is the only one
  considered, and the parts' properties are checked against that purpose's sets (PURPOSES).
Both are invention within authored affordances: the model picks the parts, the name and the purpose; it cannot make
the world do what no rule here describes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import permutations
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .items import ITEMS, Catalog, described_as, functions

# (purpose_id, keywords, required property sets, effect). Order matters: the first keyword match wins.
PURPOSES: List[Tuple[str, Tuple[str, ...], List[Set[str]], dict]] = [
    # (Invention 2.0) purposes with real hooks: defence counts against wolves, farming adds to every harvest, speed
    # quickens the holder's walk, healing mends the holder over time
    ("defence", ("defend", "defence", "defense", "weapon", "guard", "protect", "shield", "club", "fight", "wolf", "wolves"),
     [{"hard", "sharp", "pointed", "metal"}, {"sturdy", "long", "strong"}], {"tool": "weapon", "tool_power": 1.0, "defence": 1}),
    ("farming", ("farm", "plough", "plow", "hoe", "sow", "harvest", "crop", "field", "till"),
     [{"hard", "sharp", "metal"}, {"sturdy", "long"}], {"farming": 3}),
    ("healing", ("heal", "medicine", "remedy", "salve", "poultice", "cure", "bandage", "tonic", "sick"),
     [{"soft", "edible", "flexible", "stringy", "woven"}], {"heal": 1}),
    ("speed", ("fast", "speed", "run", "shoe", "sled", "sledge", "cart", "travel", "wheel", "quick"),
     [{"sturdy", "long", "woven", "flexible", "strong", "round"}], {"speed": 1.2}),
    ("fishing", ("fish", "catch", "net", "trap", "hook"),
     [{"stringy", "binding", "flexible"}, {"sturdy", "long", "pointed", "sharp"}], {"tool": "spear", "tool_power": 1.2}),
    ("cutting", ("cut", "chop", "saw", "blade", "knife"), [{"sharp"}, {"sturdy", "long", "hard"}],
     {"tool": "axe", "tool_power": 1.5}),
    ("digging", ("dig", "mine", "quarry", "break rock"), [{"hard", "metal"}, {"sturdy", "long"}],
     {"tool": "pick", "tool_power": 1.5}),
    ("carrying", ("carry", "bag", "sack", "sling", "pack", "hold"), [{"flexible", "woven", "stringy", "container"}],
     {"carry_bonus": 5}),
    ("warmth", ("warm", "cloak", "coat", "cloth", "blanket", "wrap"), [{"flexible", "soft", "woven", "strong"}],
     {"warmth": 0.5}),
    ("light", ("light", "torch", "lamp", "glow"), [{"flammable", "burns very hot"}, {"sturdy", "long", "container", "fired"}],
     {"tool": "light", "tool_power": 0.5}),
    ("food", ("eat", "food", "meal", "stew", "snack", "dish"), [], {}),
    ("joy", ("music", "drum", "flute", "song", "art", "toy", "ornament", "jewel", "decoration", "paint", "game", "joy", "fun",
             "play", "dance", "sing", "pretty", "beauty"), [],
     {"mood": 8}),
]

UNDERSTOOD = ("catching fish, cutting, digging, carrying, keeping warm, light, food, defence, farming, healing, "
              "speed, or joy (music, toys, art)")

# ---------------------------------------------------------------------------- how strong an effect is (F34)
# One table. What an invention does is a NUMBER that comes from what it is made of: better material, a better tool;
# more insulating parts, a warmer coat; something that rolls, a faster walk. (Before, every magnitude was thrown away:
# any speed invention was x1.2, any farming one +3 grain, any warm one halved the cold, and "defence" was read nowhere.)
HARD_PROPS = frozenset({"hard", "very hard", "holds an edge"})
TOOL_TIER = {"metal": 1.6, "hard": 1.2, "plain": 1.0}  # a tool's base power is multiplied by this: metal > stone > wood
FARMING_GRAIN = {"metal": 3, "hard": 2, "plain": 1}  # extra grain from every harvest while it is carried
DEFENCE_ODDS = {"metal": 0.85, "hard": 0.75, "plain": 0.65}  # the chance its holder drives a wolf off
LIGHT_HOT = 1.25  # a light whose fuel burns very hot is this much brighter
HOT_FUEL = frozenset({"burns very hot", "burns violently"})
FOOD_GAIN = 1.15  # a dish feeds this much more than its parts eaten one by one
CARRY_BASE, CARRY_PER_CONTAINER, CARRY_MAX = 5, 2, 12  # a sack; each part that is a container adds; less than a cart
CONTAINING = frozenset({"container", "holds food"})
WARMTH_BY_INSULATORS = (0.7, 0.6, 0.5, 0.4)  # the share of the cold that gets through, by insulating parts: 0, 1, 2, 3+
INSULATING = frozenset({"warm", "woven", "fluffy", "wearable"})
SPEED_BASE, SPEED_ROLLING, SPEED_HEAVY, SPEED_MIN = 1.15, 0.1, 0.05, 1.05  # walking speed is multiplied by the result
SPEED_HEAVY_OVER = 4  # the parts' weight above which it slows its holder down again
ROLLING = frozenset({"round", "rolls", "slides"})
HEAL_BASE, HEAL_PER_EXTRA, HEAL_MAX = 1.0, 0.5, 2.0  # a remedy; each further edible or soft part makes it richer
REMEDY = frozenset({"edible", "soft"})
JOY_BASE, JOY_PER_FINE, JOY_MAX = 8, 2, 14  # mood points; each fine part adds
FINE = frozenset({"shiny", "clear", "smooth", "round", "fluffy", "woven"})
# what the numbers do while the thing is carried (world.py, actions.py and animals.py read them through these)
HEAL_PER_STRENGTH = 0.12  # health per tick for a remedy of strength 1 (on top of the body's own mending)
MOOD_PER_POINT = 0.0025  # mood per tick for each mood point (8 points: the +0.02 a tick that T20 specified)
LOWER_IS_BETTER = frozenset({"warmth"})  # of two warm things, the one that lets less cold through counts
CARRIED_EFFECTS = ("warmth", "speed", "heal", "farming", "mood", "defence")  # the effects that live outside the Item
PROPS_KEPT = 8  # how many of its parts' properties an invention keeps (all of them, up to this many)
METALS = ("alloy", "steel", "iron", "copper")  # (best first) what a mended invention keeps and a smelted one gives back


def tier(units) -> str:
    """The best material among these parts: metal, hard or plain."""
    props = {p for it in units for p in it.props}
    return "metal" if "metal" in props else "hard" if props & HARD_PROPS else "plain"


def _count(units, wanted) -> int:
    return sum(1 for it in units if wanted & set(it.props))


def strength(pid: str, effect: dict, units, head=None) -> dict:
    """The effect of a `pid` invention made of these parts (`units`: one Item per piece), with its numbers. `head`:
    the piece that does the work (a blade, a pick's head), whose material then sets a tool's strength; without one the
    best material among the parts does."""
    e, t = dict(effect), tier([head] if head is not None else units)
    if "tool_power" in e:
        hot = LIGHT_HOT if pid == "light" and _count(units, HOT_FUEL) else 1.0
        e["tool_power"] = round(e["tool_power"] * TOOL_TIER[t] * hot, 2)
    if pid == "defence":
        e["defence"] = DEFENCE_ODDS[t]
    elif pid == "farming":
        e["farming"] = FARMING_GRAIN[t]
    elif pid == "carrying":
        e["carry_bonus"] = min(CARRY_MAX, int(e.get("carry_bonus", CARRY_BASE)) + CARRY_PER_CONTAINER * _count(units, CONTAINING))
    elif pid == "warmth":
        e["warmth"] = WARMTH_BY_INSULATORS[min(_count(units, INSULATING), len(WARMTH_BY_INSULATORS) - 1)]
    elif pid == "speed":
        heavy = sum(it.weight for it in units) > SPEED_HEAVY_OVER
        e["speed"] = round(max(SPEED_MIN, SPEED_BASE + (SPEED_ROLLING if _count(units, ROLLING) else 0.0)
                               - (SPEED_HEAVY if heavy else 0.0)), 2)
    elif pid == "healing":
        e["heal"] = min(HEAL_MAX, max(HEAL_BASE, float(e.get("heal", 0))) + HEAL_PER_EXTRA * max(0, _count(units, REMEDY) - 1))
    elif pid == "joy":
        e["mood"] = min(JOY_MAX, JOY_BASE + JOY_PER_FINE * _count(units, FINE))
    return e


def _units(bag: Dict[str, int], look) -> list:
    """One Item per piece in the bag, in the order of the keys."""
    return [look(k) for k in sorted(bag) for _ in range(max(0, bag[k]))]


def mentions(text: str, kw: str) -> bool:
    """A purpose keyword counts only as a whole word, in any of its plain forms: "cut", "cuts", "cutting", "cutter";
    "carry", "carrying"; "dance", "dancing". Matched as a substring, "sick" was in "stick" (so a pointed stick to catch
    fish was judged as healing), "eat" in "heat" and "hoe" in "shoe"; matched as the bare word and its plural only, the
    guide's own "cutting", "digging", "carrying", "farming" and "healing" were not understood (Codex, #69)."""
    return _mention(text, kw) is not None


def _mention(text: str, kw: str):
    """Where `text` holds the keyword as a whole word (a match, or None)."""
    stem, last = re.escape(kw), re.escape(kw[-1])
    forms = rf"{stem}(?:s|es|ed|er|ers|ing|{last}ing|{last}er|{last}ers|{last}ed)?"
    if kw.endswith("e"):
        forms += rf"|{re.escape(kw[:-1])}ing"
    return re.search(rf"\b(?:{forms})\b", text)


SIZE_RULE = "An invention needs 2 to 4 items in total (at most 3 kinds)."
NOT_REAL = "Some of those aren't real items."
WORKS = "It works!"


def _keywords(bag: Dict[str, int], purpose_text: str, look) -> Tuple[bool, Optional[str], dict, str]:
    """The first engine (T20, kept behind COMPOSE = False for comparison): the first purpose whose keyword the text
    holds wins, and the parts' properties are then checked against that purpose's sets."""
    kinds = [k for k, n in bag.items() if n > 0]
    text = (purpose_text or "").lower()
    pick = next((p for p in PURPOSES if any(mentions(text, kw) for kw in p[1])), None)
    if pick is None:
        return False, None, {}, f"Nobody could see what it would be for. The world understands {UNDERSTOOD}."
    pid, _, required, effect = pick
    items = [look(k) for k in kinds]
    if any(it is None for it in items):
        return False, pid, {}, NOT_REAL
    if pid == "food":
        if not all("edible" in it.props for it in items):
            return False, pid, {}, "It didn't work for food — every part of it has to be edible."
        return True, pid, {"food": round(sum(look(k).food * n for k, n in bag.items() if n > 0) * FOOD_GAIN)}, WORKS
    props = {p for it in items for p in it.props}
    for need in required:
        if not props & need:
            return False, pid, {}, f"It didn't work for {pid} — it seemed to need something {' or '.join(sorted(need))}"
    return True, pid, strength(pid, effect, _units(bag, look)), WORKS


# ---------------------------------------------------------------------------- composition (F34)
# What a combination of parts CAN do is worked out from what each part can do (items.FUNCTIONS) and where it is made.
# Each rule names a kind of thing, the parts it needs (each need met by a different piece; the first is the working
# end, the "head", whose material sets the strength) and, for some, the station it must be made at. A bag of parts
# usually satisfies several rules. The chit's purpose text then only chooses among those readings (and names the
# thing); it can no longer be the gate. With COMPOSE off the first engine above judges instead, for comparison.
COMPOSE = True

# words that name a purpose only to the composing engine (the first engine's keyword lists are left as they were)
MORE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "warmth": ("heat",), "carrying": ("haul", "cart", "barrow", "basket"), "cutting": ("axe",), "digging": ("pick",),
    "light": ("lantern", "candle"), "defence": ("hunt",)}
IN_WORDS = {"fishing": "catching fish", "cutting": "cutting", "digging": "digging", "carrying": "carrying",
            "warmth": "keeping warm", "light": "light", "food": "food", "defence": "defence", "farming": "farming",
            "healing": "healing", "speed": "speed", "joy": "joy"}
NET_POWER, FISH_SPEAR_POWER, TRAP_POWER = 1.2, 0.9, 1.0  # as a spear (the real spear: 1.0)
BLADE_POWER, HAND_BLADE_POWER = 1.5, 1.2  # as an axe (a stone axe: 2.0)
PICK_POWER = 1.5  # as a pick (a stone pick: 2.0)
FORGED_POWER = 1.75  # a metal head worked at a bench: below the real copper tools (3.0) even in metal (x1.6)
CLUB_POWER, SLING_POWER, FORGED_WEAPON_POWER = 1.0, 0.8, 1.5  # as a weapon (the musket: 3.0)
TORCH_POWER, LAMP_POWER = 0.5, 0.8  # as a light (the lantern: 1.0)
CART_CARRY = 9  # a thing on a wheel carries this much more (before its containers)
TONIC_HEAL = 2.0  # a remedy brewed over a fire
COOKED_GAIN = 1.3  # a dish made at a fire feeds this much more than its parts


@dataclass(frozen=True)
class Rule:
    key: str
    purpose: str
    what: str  # in plain words
    needs: Tuple[FrozenSet[str], ...]  # each met by a different piece; the first is the head
    effect: dict
    station: Optional[str] = None  # where it has to be made (and made again)
    every: Optional[str] = None  # a function every piece must have
    gain: float = 0.0  # (food) how much more the dish feeds than its parts


def _rule(key: str, purpose: str, what: str, needs: Tuple[str, ...], effect: dict, station: Optional[str] = None,
          every: Optional[str] = None, gain: float = 0.0) -> Rule:
    return Rule(key, purpose, what, tuple(frozenset(n.split("|")) for n in needs), effect, station, every, gain)


# In order of preference within a purpose: what a station makes possible first, then the better thing.
RULES: Tuple[Rule, ...] = (
    _rule("net", "fishing", "a net or a line on a frame", ("binds", "long|rigid"), {"tool": "spear", "tool_power": NET_POWER}),
    _rule("fish_spear", "fishing", "a point on a shaft", ("pierces", "long"), {"tool": "spear", "tool_power": FISH_SPEAR_POWER}),
    _rule("fish_trap", "fishing", "a trap on a line", ("holds", "binds"), {"tool": "spear", "tool_power": TRAP_POWER}),
    _rule("forged_blade", "cutting", "a metal blade worked at the bench", ("metal", "long"),
          {"tool": "axe", "tool_power": FORGED_POWER}, station="workshop"),
    _rule("hafted_blade", "cutting", "an edge on a handle", ("cuts", "long"), {"tool": "axe", "tool_power": BLADE_POWER}),
    _rule("hand_blade", "cutting", "an edge with a grip", ("cuts", "rigid"), {"tool": "axe", "tool_power": HAND_BLADE_POWER}),
    _rule("forged_pick", "digging", "a metal pick worked at the bench", ("metal", "long"),
          {"tool": "pick", "tool_power": FORGED_POWER}, station="workshop"),
    _rule("pick", "digging", "a hard head on a handle", ("hard|metal", "long"), {"tool": "pick", "tool_power": PICK_POWER}),
    _rule("forged_weapon", "defence", "a metal weapon worked at the bench", ("metal", "long"),
          {"tool": "weapon", "tool_power": FORGED_WEAPON_POWER}, station="workshop"),
    _rule("club", "defence", "a hard, heavy or sharp head on a shaft", ("hard|metal|heavy|cuts|pierces", "long"),
          {"tool": "weapon", "tool_power": CLUB_POWER}),
    _rule("sling", "defence", "a stone on a cord", ("hard|heavy", "binds"), {"tool": "weapon", "tool_power": SLING_POWER}),
    _rule("hoe", "farming", "a hard or sharp head on a handle", ("hard|metal|cuts", "long"), {"farming": FARMING_GRAIN["plain"]}),
    _rule("tonic", "healing", "a remedy brewed in a pot over a fire", ("edible", "holds-liquid"), {"heal": TONIC_HEAL},
          station="fire"),
    _rule("poultice", "healing", "a soft remedy with something to hold it", ("soft|edible", "binds|soft|holds"),
          {"heal": HEAL_BASE}),
    _rule("bandage", "healing", "a binding", ("binds|insulates", "binds|insulates"), {"heal": HEAL_BASE}),
    _rule("wheels", "speed", "something that rolls under a frame", ("rolls", "long|rigid"), {"speed": SPEED_BASE}),
    _rule("runners", "speed", "long pieces underfoot", ("long", "long|binds"), {"speed": SPEED_BASE}),
    _rule("sandals", "speed", "bindings underfoot", ("binds", "binds|insulates|soft"), {"speed": SPEED_BASE}),
    _rule("handcart", "carrying", "a frame on something that rolls", ("rolls", "long|rigid"), {"carry_bonus": CART_CARRY}),
    _rule("pannier", "carrying", "a container with a strap or a pole", ("holds", "binds|long|rigid"), {"carry_bonus": CARRY_BASE}),
    _rule("sack", "carrying", "a bag of bindings", ("binds", "binds"), {"carry_bonus": CARRY_BASE}),
    _rule("garment", "warmth", "something that insulates, held together", ("insulates", "insulates|binds"), {"warmth": 1.0}),
    _rule("mat", "warmth", "a plaited wrap", ("binds", "binds"), {"warmth": 1.0}),
    _rule("lamp", "light", "a flame in a holder", ("burns", "holds|transparent"), {"tool": "light", "tool_power": LAMP_POWER}),
    _rule("torch", "light", "a flame on a stick", ("burns", "long|rigid"), {"tool": "light", "tool_power": TORCH_POWER}),
    _rule("cooked_dish", "food", "a dish cooked at a fire", (), {}, station="fire", every="edible", gain=COOKED_GAIN),
    _rule("dish", "food", "a dish", (), {}, every="edible", gain=FOOD_GAIN),
    _rule("ornament", "joy", "a toy, an ornament or something to make music with", (), {"mood": JOY_BASE}),
)
RULE: Dict[str, Rule] = {r.key: r for r in RULES}
_TIER_RANK = {"plain": 0, "hard": 1, "metal": 2}


def _fit(rule: Rule, units, fns) -> Optional[Tuple[int, ...]]:
    """Which piece meets which need (each need a different piece), choosing the best material for the head. None: the
    parts don't make this."""
    if rule.every and not all(rule.every in f for f in fns):
        return None
    best, rank = None, -1
    for perm in permutations(range(len(units)), len(rule.needs)):
        if all(need & fns[i] for need, i in zip(rule.needs, perm)):
            r = _TIER_RANK[tier([units[perm[0]]])] if perm else 0
            if r > rank:
                best, rank = perm, r
    return best


def _lacks(rule: Rule, fns) -> Tuple[int, Optional[FrozenSet[str]]]:
    """How many of the rule's needs these pieces leave unmet at best, and the first of them."""
    worst = (len(rule.needs), rule.needs[0] if rule.needs else None)
    for perm in permutations(range(len(fns)), min(len(rule.needs), len(fns))):
        missing = [need for need, i in zip(rule.needs, perm) if not need & fns[i]] + list(rule.needs[len(perm):])
        if len(missing) < worst[0]:
            worst = (len(missing), missing[0] if missing else None)
    return worst


def _made(rule: Rule, units, fit: Tuple[int, ...]) -> dict:
    if rule.every == "edible":
        return {"food": round(sum(u.food for u in units) * rule.gain)}
    return strength(rule.purpose, rule.effect, units, units[fit[0]] if fit else None)


def readings(bag: Dict[str, int], catalog: Optional[Catalog] = None, stations=()) -> Dict[str, Tuple[Rule, dict]]:
    """Everything these parts can be at these stations: purpose -> (the rule that makes it, its effect). The first
    rule in the table's order that fits is the one for its purpose."""
    look = catalog.item if catalog is not None else ITEMS.get
    units = _units(bag, look)
    if any(u is None for u in units):
        return {}
    fns = [functions(u) for u in units]
    out: Dict[str, Tuple[Rule, dict]] = {}
    for rule in RULES:
        if rule.purpose in out or (rule.station and rule.station not in stations):
            continue
        fit = _fit(rule, units, fns)
        if fit is not None:
            out[rule.purpose] = (rule, _made(rule, units, fit))
    return out


def _named(text: str) -> List[str]:
    """The purposes a text names: the one it says most about first ("a cart to carry more" is about carrying, "a cart
    to travel fast" about speed), then the one it names earliest."""
    found = []
    for pid, kws, _, _ in PURPOSES:
        at = [m.start() for kw in kws + MORE_KEYWORDS.get(pid, ()) if (m := _mention(text, kw))]
        if at:
            found.append((-len(at), min(at), pid))
    return [pid for _, _, pid in sorted(found)]


def _list(words: List[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


NEED_WORDS = 5  # how many properties the feedback names for one missing need


def _good_for(bag: Dict[str, int], catalog, stations, can: Dict[str, Tuple[Rule, dict]]) -> str:
    """What these parts could be instead, in the purposes' own words (never a base recipe: only what the invent rules
    make of them), and whether a station would make more of them."""
    here = [IN_WORDS[p] for p in can if p != "joy"] or [IN_WORDS[p] for p in can]
    out = f" These parts could make something for {_list(here)}." if here else ""
    more = sorted({r.station for r in RULES if r.station and r.station not in stations
                   and r.purpose not in can and r.purpose in readings(bag, catalog, (r.station,))})
    if more:
        out += f" Made at a {_list(more)} they might do more."
    return out


def _compose(bag: Dict[str, int], purpose_text: str, catalog: Optional[Catalog], stations) -> Dict[str, object]:
    look = catalog.item if catalog is not None else ITEMS.get
    named = _named((purpose_text or "").lower())
    real = all(look(k) is not None for k, n in bag.items() if n > 0)
    can = readings(bag, catalog, stations) if real else {}
    if not named:
        return {"ok": False, "purpose": None, "effect": {}, "rule": None, "station": None,
                "feedback": f"Nobody could see what it would be for. The world understands {UNDERSTOOD}."
                            + _good_for(bag, catalog, stations, can)}
    if not real:
        return {"ok": False, "purpose": named[0], "effect": {}, "feedback": NOT_REAL, "rule": None, "station": None}
    for pid in named:  # the first purpose it names that these parts can serve
        if pid in can:
            rule, effect = can[pid]
            return {"ok": True, "purpose": pid, "effect": effect, "feedback": WORKS, "rule": rule.key, "station": rule.station}
    pid = named[0]
    fns = [functions(u) for u in _units(bag, look)]
    rules = [r for r in RULES if r.purpose == pid and (not r.station or r.station in stations)]
    if rules and all(r.every for r in rules):
        why = f"It didn't work for {pid} — every part of it has to be {rules[0].every}."
    else:
        lacks = min((_lacks(r, fns) for r in rules if not r.every), key=lambda x: x[0])  # (the nearest miss; ties: the first)
        words = [p for f in sorted(lacks[1] or ()) for p in described_as(f)][:NEED_WORDS]
        why = f"It didn't work for {pid} — it seemed to need something {' or '.join(words)}."
    return {"ok": False, "purpose": pid, "effect": {}, "feedback": why + _good_for(bag, catalog, stations, can),
            "rule": None, "station": None}


def verdict(bag: Dict[str, int], purpose_text: str, catalog: Optional[Catalog] = None, stations=()) -> Dict[str, object]:
    """judge(), with what the simulator needs to register the thing: {"ok", "purpose", "effect", "feedback", "rule",
    "station"} (the rule that made it and the station it needs to be made again, None for neither)."""
    total = sum(n for n in bag.values() if n > 0)
    if not 2 <= total <= 4 or sum(1 for n in bag.values() if n > 0) > 3:
        return {"ok": False, "purpose": None, "effect": {}, "feedback": SIZE_RULE, "rule": None, "station": None}
    if COMPOSE:
        return _compose(bag, purpose_text, catalog, frozenset(stations or ()))
    ok, pid, effect, feedback = _keywords(bag, purpose_text, catalog.item if catalog is not None else ITEMS.get)
    return {"ok": ok, "purpose": pid, "effect": effect, "feedback": feedback, "rule": None, "station": None}


def judge(bag: Dict[str, int], purpose_text: str, catalog: Optional[Catalog] = None,
          station=None) -> Tuple[bool, Optional[str], dict, str]:
    """Would these items, put together, serve this purpose? Returns (ok, purpose_id, effect, feedback).
    `station`: the station (or stations) it is made at, if any."""
    v = verdict(bag, purpose_text, catalog, (station,) if isinstance(station, str) else (station or ()))
    return v["ok"], v["purpose"], v["effect"], v["feedback"]


def invention_props(bag: Dict[str, int], purpose_id: str, catalog: Optional[Catalog] = None) -> Tuple[str, ...]:
    """What the new thing is like: "invented", what it is for, and its parts' own properties (all of them, in the
    order of the parts, up to PROPS_KEPT), so that a thing made from an invention has something to work with. (It
    kept three: a net of fiber and wood was flexible, stringy and light, and no longer sturdy or long.)"""
    look = catalog.item if catalog is not None else ITEMS.get
    seen: List[str] = []
    for k in sorted(bag):
        it = look(k)
        for p in (it.props if it else ()):
            if p not in seen and p != "invented" and not p.startswith("for "):
                seen.append(p)
    return ("invented", "for " + purpose_id) + tuple(seen[:PROPS_KEPT])


def invention_metal(inv: Optional[dict]) -> Optional[str]:
    """The metal in an invention: what mending it keeps and smelting it gives back (None: there is none in it)."""
    inputs = (inv or {}).get("inputs") or {}
    return next((m for m in METALS if inputs.get(m, 0) > 0), None)


def effect_words(effect: Optional[dict]) -> List[str]:
    """What an invention does, in plain words with its numbers (for the observer's entry and a chit's own list)."""
    e, out = effect or {}, []
    if e.get("tool"):
        out.append(f"works as {'an' if e['tool'][0] in 'aeiou' else 'a'} {e['tool']} (power {float(e.get('tool_power', 0)):g})")
    if e.get("carry_bonus"):
        out.append(f"its holder carries {int(e['carry_bonus'])} more")
    if e.get("food"):
        out.append(f"food worth {float(e['food']):g} hunger")
    if e.get("warmth"):
        out.append(f"keeps out {round((1 - float(e['warmth'])) * 100)}% of the cold")
    if e.get("speed"):
        out.append(f"its holder walks {round((float(e['speed']) - 1) * 100)}% faster")
    if e.get("heal"):
        out.append(f"mends its holder (strength {float(e['heal']):g})")
    if e.get("farming"):
        out.append(f"+{int(e['farming'])} grain from every harvest")
    if e.get("mood"):
        out.append(f"lifts its holder's mood ({float(e['mood']):g} points)")
    d = e.get("defence")
    if d and 0 < d < 1:
        out.append(f"drives a wolf off {round(d * 100)} times in 100")
    return out


def carried_effect(inv: Optional[dict]) -> bool:
    """Does this invention do something for whoever carries it (beyond being a tool, a container or food)?"""
    eff = (inv or {}).get("effect") or {}
    return any(eff.get(k) for k in CARRIED_EFFECTS)


def register_invention(world, key: str, name: str, inputs: Dict[str, int], props: Tuple[str, ...], effect: dict):
    """Add an invented item and its recipe to *this world's* catalogue only."""
    from .items import Item, Recipe

    it = Item(key, name, tuple(props), food=float(effect.get("food", 0)), tool=effect.get("tool"),
              tool_power=float(effect.get("tool_power", 0.0)), carry_bonus=int(effect.get("carry_bonus", 0)), icon="💡")
    r = Recipe(key, tuple(sorted(inputs.items())), None, 1, 8)
    world.catalog.items[key] = it
    world.catalog.recipes[key] = r
    return r
