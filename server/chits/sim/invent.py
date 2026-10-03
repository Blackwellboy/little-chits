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


def mentions(text: str, kw: str) -> bool:
    """A purpose keyword counts only as a whole word (a plural too). Matched as a substring, "sick" was in "stick" (so a
    pointed stick to catch fish was judged as healing), "eat" in "heat" and "hoe" in "shoe"."""
    return re.search(r"\b" + re.escape(kw) + r"(?:s|es)?\b", text) is not None


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
        return True, pid, {"food": round(sum(look(k).food * n for k, n in bag.items() if n > 0) * 1.15)}, "It works!"
    props = {p for it in items for p in it.props}
    for need in required:
        if not props & need:
            return False, pid, {}, f"It didn't work for {pid} — it seemed to need something {' or '.join(sorted(need))}"
    effect = dict(effect)
    if "tool_power" in effect:  # better materials, better tool: metal beats stone beats wood
        effect["tool_power"] = round(effect["tool_power"] * (1.6 if "metal" in props else 1.2 if "hard" in props else 1.0), 2)
    return True, pid, effect, "It works!"


def invention_props(bag: Dict[str, int], purpose_id: str, catalog: Optional[Catalog] = None) -> Tuple[str, ...]:
    look = catalog.item if catalog is not None else ITEMS.get
    seen: List[str] = []
    for k in sorted(bag):
        it = look(k)
        for p in (it.props if it else ()):
            if p not in seen and p != "invented" and not p.startswith("for "):
                seen.append(p)
    return ("invented", "for " + purpose_id) + tuple(seen[:3])


def register_invention(world, key: str, name: str, inputs: Dict[str, int], props: Tuple[str, ...], effect: dict):
    """Add an invented item and its recipe to *this world's* catalogue only."""
    from .items import Item, Recipe

    it = Item(key, name, tuple(props), food=float(effect.get("food", 0)), tool=effect.get("tool"),
              tool_power=float(effect.get("tool_power", 0.0)), carry_bonus=int(effect.get("carry_bonus", 0)), icon="💡")
    r = Recipe(key, tuple(sorted(inputs.items())), None, 1, 8)
    world.catalog.items[key] = it
    world.catalog.recipes[key] = r
    return r
