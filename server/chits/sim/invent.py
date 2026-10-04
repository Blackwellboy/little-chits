"""Open invention (T20): a chit proposes a name and a purpose, and the world judges it by physical law.

Cognition proposes, the simulator decides. A purpose is only met when the inputs have the properties it needs.
This is invention *within authored affordances*: the model picks the inputs, the name and the purpose, and the
world checks it against a fixed list of purposes. A later task can replace the buckets with composable
affordances (material + shape + mechanism).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .items import ITEMS, Catalog

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


def strength(pid: str, effect: dict, units) -> dict:
    """The effect of a `pid` invention made of these parts (`units`: one Item per piece), with its numbers."""
    e, t = dict(effect), tier(units)
    if "tool_power" in e:
        e["tool_power"] = round(e["tool_power"] * TOOL_TIER[t], 2)
    if pid == "defence":
        e["defence"] = DEFENCE_ODDS[t]
    elif pid == "farming":
        e["farming"] = FARMING_GRAIN[t]
    elif pid == "carrying":
        e["carry_bonus"] = min(CARRY_MAX, CARRY_BASE + CARRY_PER_CONTAINER * _count(units, CONTAINING))
    elif pid == "warmth":
        e["warmth"] = WARMTH_BY_INSULATORS[min(_count(units, INSULATING), len(WARMTH_BY_INSULATORS) - 1)]
    elif pid == "speed":
        heavy = sum(it.weight for it in units) > SPEED_HEAVY_OVER
        e["speed"] = round(max(SPEED_MIN, SPEED_BASE + (SPEED_ROLLING if _count(units, ROLLING) else 0.0)
                               - (SPEED_HEAVY if heavy else 0.0)), 2)
    elif pid == "healing":
        e["heal"] = min(HEAL_MAX, HEAL_BASE + HEAL_PER_EXTRA * max(0, _count(units, REMEDY) - 1))
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
    stem, last = re.escape(kw), re.escape(kw[-1])
    forms = rf"{stem}(?:s|es|ed|er|ers|ing|{last}ing|{last}er|{last}ers|{last}ed)?"
    if kw.endswith("e"):
        forms += rf"|{re.escape(kw[:-1])}ing"
    return re.search(rf"\b(?:{forms})\b", text) is not None


def judge(bag: Dict[str, int], purpose_text: str, catalog: Optional[Catalog] = None) -> Tuple[bool, Optional[str], dict, str]:
    """Would these items, put together, serve this purpose? Returns (ok, purpose_id, effect, feedback)."""
    look = catalog.item if catalog is not None else ITEMS.get
    total = sum(n for n in bag.values() if n > 0)
    kinds = [k for k, n in bag.items() if n > 0]
    if not 2 <= total <= 4 or len(kinds) > 3:
        return False, None, {}, "An invention needs 2 to 4 items in total (at most 3 kinds)."
    text = (purpose_text or "").lower()
    pick = next((p for p in PURPOSES if any(mentions(text, kw) for kw in p[1])), None)
    if pick is None:
        return False, None, {}, f"Nobody could see what it would be for. The world understands {UNDERSTOOD}."
    pid, _, required, effect = pick
    items = [look(k) for k in kinds]
    if any(it is None for it in items):
        return False, pid, {}, "Some of those aren't real items."
    if pid == "food":
        if not all("edible" in it.props for it in items):
            return False, pid, {}, "It didn't work for food — every part of it has to be edible."
        return True, pid, {"food": round(sum(look(k).food * n for k, n in bag.items() if n > 0) * FOOD_GAIN)}, "It works!"
    props = {p for it in items for p in it.props}
    for need in required:
        if not props & need:
            return False, pid, {}, f"It didn't work for {pid} — it seemed to need something {' or '.join(sorted(need))}"
    return True, pid, strength(pid, effect, _units(bag, look)), "It works!"


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
