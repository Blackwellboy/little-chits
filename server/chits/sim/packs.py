"""Content packs: a JSON file that adds items and recipes to one world's own catalogue (docs/modding.md).

A pack is data only. Nothing in it is ever run, imported or used as a path. It is read once, checked against the same
rules the base tables are held to (every item has a use and a way to get it, every input and station exists) plus
size limits, and then copied into the world's `Catalog` beside its inventions. The shared tables (ITEMS, RECIPES,
DESIGNS) are never touched, so a world without the pack cannot see any of it.

The pack travels with the world: it is in the save, the run manifest and the replay bundle, and every world of a
match gets the same one. Experiment runs refuse packs (runtime.py).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .artifacts import ARTIFACTS  # (importing it registers the artifacts in ITEMS)
from .items import DESIGNS, GATHER_RULES, ITEMS, RECIPES, STATIONS, Catalog, Item, Recipe, normalize_design, normalize_item

SCHEMA = 1
MAX_BYTES = 64 * 1024
MAX_ITEMS = 32
MAX_RECIPES = 32
MAX_PROPS = 6
MAX_INPUT_KINDS = 4
MAX_INPUT_TOTAL = 5  # the largest base recipe (the steam engine): experiments and the planners are sized for it
MAX_FOOD = 100.0
MAX_TOOL_POWER = 4.0  # an iron tool
MAX_CARRY_BONUS = 16  # a cart
MAX_WEIGHT = 4
MAX_QTY = 4
MAX_WORK = 30
TOOLS = ("axe", "pick", "spear", "light")  # the tool classes the world has a use for

_ID = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
# names and properties reach the models' prompts: lower-case words only, nothing that could pass for an instruction
_WORDS = re.compile(r"^[a-z][a-z0-9' -]{0,31}$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,19}$")
_TOP = {"schema", "id", "name", "version", "description", "author", "items", "recipes"}
_ITEM = {"key", "name", "props", "food", "tool", "tool_power", "carry_bonus", "weight", "icon"}
_RECIPE = {"makes", "inputs", "station", "qty", "work"}
# what can be obtained without a recipe (tests/test_item_uses.py): gathering, hunting, tame sheep, harvesting farms
_FOUND = set(GATHER_RULES) | {"meat", "wool", "grain"}


class PackError(ValueError):
    """Why a pack was refused, in words a pack author can act on."""


def _fail(msg: str) -> None:
    raise PackError(f"content pack refused: {msg}")


def _no_constants(name: str) -> None:
    _fail(f"{name} is not a JSON number")


def parse(text: Any) -> Dict[str, Any]:
    """JSON text (or bytes) -> the raw pack. Size-limited, and strict: no NaN, no Infinity, an object at the top."""
    if isinstance(text, bytes):
        if len(text) > MAX_BYTES:
            _fail(f"the file is larger than {MAX_BYTES // 1024} KiB")
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            _fail("the file is not UTF-8 text")
    if not isinstance(text, str):
        _fail("not JSON text")
    if len(text.encode("utf-8")) > MAX_BYTES:
        _fail(f"the file is larger than {MAX_BYTES // 1024} KiB")
    try:
        raw = json.loads(text, parse_constant=_no_constants)
    except PackError:
        raise
    except (ValueError, RecursionError) as e:
        _fail(f"not valid JSON ({e})")
    if not isinstance(raw, dict):
        _fail("the top level must be a JSON object")
    return raw


def load_file(path: Any) -> Dict[str, Any]:
    """Read and validate a pack file. The path comes from the person running the server (CHITS_PACK or the checker),
    never from a pack or a web request."""
    p = Path(path)
    try:
        if not p.is_file():
            _fail(f"no such file: {p}")
        if p.stat().st_size > MAX_BYTES:
            _fail(f"the file is larger than {MAX_BYTES // 1024} KiB")
        data = p.read_bytes()
    except OSError as e:
        _fail(f"could not read {p}: {e}")
    return validate(parse(data))


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) and v == v and abs(v) != float("inf")


def _only(d: Any, allowed: set, what: str) -> Dict[str, Any]:
    if not isinstance(d, dict):
        _fail(f"{what} must be an object")
    extra = sorted(set(d) - allowed)
    if extra:
        _fail(f"{what} has unknown field(s): {', '.join(map(str, extra))}")
    return d


def _text(v: Any, what: str, limit: int, required: bool = False) -> str:
    if v is None and not required:
        return ""
    if not isinstance(v, str):
        _fail(f"{what} must be text")
    s = " ".join(v.split())
    if required and not s:
        _fail(f"{what} is empty")
    if len(s) > limit:
        _fail(f"{what} is longer than {limit} characters")
    if any(ord(ch) < 32 or ch in "<>" for ch in s):
        _fail(f"{what} has characters that are not allowed")
    return s


def _item(raw: Any, check_base: bool) -> Dict[str, Any]:
    d = _only(raw, _ITEM, "an item")
    key = d.get("key")
    if not isinstance(key, str) or not _KEY.match(key):
        _fail(f"item key {key!r}: use 2-32 of a-z, 0-9 and _, starting with a letter")
    what = f"item {key}"
    if key.startswith("inv_"):
        _fail(f"{what}: keys starting with inv_ are kept for inventions")
    name = d.get("name")
    if not isinstance(name, str) or not _WORDS.match(name) or name != " ".join(name.split()):
        _fail(f"{what}: the name must be 1-32 lower-case letters, digits, spaces, ' or -")
    if check_base:
        if key in ITEMS or key in DESIGNS or key in STATIONS:
            _fail(f"{what}: that key is already used by the game")
        for label in (key, name):
            if normalize_item(label) or normalize_design(label):
                _fail(f"{what}: \"{label}\" already means something in the game")
    props = d.get("props")
    if not isinstance(props, list) or not 1 <= len(props) <= MAX_PROPS:
        _fail(f"{what}: props must be a list of 1 to {MAX_PROPS} properties")
    for p in props:
        if not isinstance(p, str) or not _WORDS.match(p) or p != " ".join(p.split()):
            _fail(f"{what}: a property must be 1-32 lower-case letters, digits, spaces, ' or -")
    if len(set(props)) != len(props):
        _fail(f"{what}: a property is listed twice")
    if "invented" in props or any(p.startswith("for ") for p in props):
        _fail(f"{what}: \"invented\" and \"for ...\" are kept for inventions")
    food = d.get("food", 0)
    if not _is_num(food) or not 0 <= food <= MAX_FOOD:
        _fail(f"{what}: food must be a number from 0 to {MAX_FOOD:g}")
    tool = d.get("tool")
    if tool is not None and tool not in TOOLS:
        _fail(f"{what}: tool must be one of {', '.join(TOOLS)}")
    power = d.get("tool_power", 1.0 if tool else 0.0)
    if not _is_num(power) or not 0 <= power <= MAX_TOOL_POWER:
        _fail(f"{what}: tool_power must be a number from 0 to {MAX_TOOL_POWER:g}")
    if tool and power <= 0:
        _fail(f"{what}: a tool needs a tool_power above 0")
    if not tool and power:
        _fail(f"{what}: tool_power without a tool")
    carry = d.get("carry_bonus", 0)
    if not _is_int(carry) or not 0 <= carry <= MAX_CARRY_BONUS:
        _fail(f"{what}: carry_bonus must be a whole number from 0 to {MAX_CARRY_BONUS}")
    weight = d.get("weight", 1)
    if not _is_int(weight) or not 1 <= weight <= MAX_WEIGHT:
        _fail(f"{what}: weight must be a whole number from 1 to {MAX_WEIGHT}")
    icon = d.get("icon", "")
    if not isinstance(icon, str) or len(icon) > 8 or any(ord(ch) < 128 for ch in icon):
        _fail(f"{what}: icon must be one emoji (or left out)")
    return {"key": key, "name": name, "props": list(props), "food": float(food), "tool": tool,
            "tool_power": float(power), "carry_bonus": carry, "weight": weight, "icon": icon}


def _recipe(raw: Any, pack_items: Dict[str, Any], check_base: bool) -> Dict[str, Any]:
    d = _only(raw, _RECIPE, "a recipe")
    makes = d.get("makes")
    if not isinstance(makes, str) or makes not in pack_items:
        _fail(f"recipe for {makes!r}: a pack recipe makes one of the pack's own items")
    what = f"recipe for {makes}"
    inputs = d.get("inputs")
    if not isinstance(inputs, dict) or not 1 <= len(inputs) <= MAX_INPUT_KINDS:
        _fail(f"{what}: inputs must be an object of 1 to {MAX_INPUT_KINDS} items and amounts")
    for k, n in inputs.items():
        if not isinstance(k, str) or not _KEY.match(k):
            _fail(f"{what}: input {k!r} is not an item")
        if check_base and k not in pack_items and k not in ITEMS:
            _fail(f"{what}: input {k} is not an item of the game or of this pack")
        if check_base and k not in pack_items and _is_artifact(k):
            _fail(f"{what}: {k} is an artifact, which nothing is made from")
        if not _is_int(n) or n < 1:
            _fail(f"{what}: the amount of {k} must be a whole number of 1 or more")
    if sum(inputs.values()) > MAX_INPUT_TOTAL:
        _fail(f"{what}: at most {MAX_INPUT_TOTAL} things go into one recipe")
    if makes in inputs:
        _fail(f"{what}: it can't be made from itself")
    station = d.get("station")
    if station is not None and station not in STATIONS:
        _fail(f"{what}: station must be one of {', '.join(STATIONS)} (or left out)")
    qty = d.get("qty", 1)
    if not _is_int(qty) or not 1 <= qty <= MAX_QTY:
        _fail(f"{what}: qty must be a whole number from 1 to {MAX_QTY}")
    work = d.get("work", 6)
    if not _is_int(work) or not 1 <= work <= MAX_WORK:
        _fail(f"{what}: work must be a whole number from 1 to {MAX_WORK}")
    return {"makes": makes, "inputs": {k: inputs[k] for k in sorted(inputs)}, "station": station, "qty": qty,
            "work": work}


def _is_artifact(key: str) -> bool:
    return key in ARTIFACTS


def _clash(a_inputs: Dict[str, int], a_station: Optional[str], b_inputs: Dict[str, int], b_station: Optional[str]) -> bool:
    """Would one experiment fit both recipes? The same things in the same amounts, at stations that can be the same
    place (a recipe that needs no station works at any)."""
    return a_inputs == b_inputs and (a_station is None or b_station is None or a_station == b_station)


def _has_use(item: Dict[str, Any], recipes: List[Dict[str, Any]]) -> bool:
    return bool(item["food"] or item["tool"] or item["carry_bonus"]
                or ("wearable" in item["props"] and "warm" in item["props"])
                or any(item["key"] in r["inputs"] for r in recipes))


def validate(raw: Any, check_base: bool = True) -> Dict[str, Any]:
    """Check a raw pack and return it in its one normal form (defaults filled in, sorted, with its sha256).

    `check_base=False` is for a pack read back from a save: its shape and limits are checked again, but not whether
    its keys are still free in the base tables (a later version of the game may have taken one; the base wins then)."""
    d = _only(raw, _TOP | {"sha256"}, "the pack")
    if d.get("schema") != SCHEMA or isinstance(d.get("schema"), bool):
        _fail(f"\"schema\" must be {SCHEMA}")
    pid = d.get("id")
    if not isinstance(pid, str) or not _ID.match(pid):
        _fail("\"id\" must be 2-32 of a-z, 0-9, _ and -, starting with a letter")
    name = _text(d.get("name"), "\"name\"", 60, required=True)
    version = d.get("version", "1")
    if not isinstance(version, str) or not _VERSION.match(version):
        _fail("\"version\" must be up to 20 letters, digits, dots, - or _ (as text, like \"1.0\")")
    description = _text(d.get("description"), "\"description\"", 400)
    author = _text(d.get("author"), "\"author\"", 60)

    raw_items = d.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ITEMS:
        _fail(f"\"items\" must be a list of 1 to {MAX_ITEMS} items")
    items: Dict[str, Dict[str, Any]] = {}
    taken: set = set()  # every way an item of this pack can be called
    for it in (_item(x, check_base) for x in raw_items):
        if it["key"] in items:
            _fail(f"item {it['key']} is listed twice")
        labels = {it["key"].replace("_", " "), it["name"].replace("-", " ")}
        if labels & taken:
            _fail(f"item {it['key']}: its key or name is already used in this pack")
        taken |= labels
        items[it["key"]] = it

    raw_recipes = d.get("recipes")
    if not isinstance(raw_recipes, list) or not 1 <= len(raw_recipes) <= MAX_RECIPES:
        _fail(f"\"recipes\" must be a list of 1 to {MAX_RECIPES} recipes")
    recipes: Dict[str, Dict[str, Any]] = {}
    for r in (_recipe(x, items, check_base) for x in raw_recipes):
        if r["makes"] in recipes:
            _fail(f"{r['makes']} has two recipes: an item is made one way")
        recipes[r["makes"]] = r
    made = list(recipes.values())

    # the rules of the base tables (tests/test_item_uses.py)
    for it in items.values():
        if it["key"] not in recipes:
            _fail(f"item {it['key']} has no way to get it: add a recipe that makes it")
        if not _has_use(it, made):
            _fail(f"item {it['key']} has no use: make it food, a tool, a container, something warm to wear, "
                  "or an input of another recipe")
    have = set(ITEMS) if check_base else {k for r in made for k in r["inputs"] if k not in items}
    left = dict(recipes)
    while left:  # every item must come, in the end, from things the base game has
        ready = [k for k, r in left.items() if all(i in have for i in r["inputs"])]
        if not ready:
            _fail(f"{', '.join(sorted(left))} can only be made from each other: nothing could ever start the chain")
        for k in ready:
            have.add(k)
            del left[k]
    for i, r in enumerate(made):
        for o in made[i + 1:]:
            if _clash(r["inputs"], r["station"], o["inputs"], o["station"]):
                _fail(f"the recipes for {r['makes']} and {o['makes']} take the same things at the same place")
        if check_base:
            for b in RECIPES.values():
                if _clash(r["inputs"], r["station"], dict(b.inputs), b.station):
                    _fail(f"the recipe for {r['makes']} takes the same things as the game's recipe for {b.key}")
            if r["station"] and r["station"] != "fire" and not any(dd.station == r["station"] for dd in DESIGNS.values()):
                _fail(f"recipe for {r['makes']}: nothing in the game is a {r['station']}")

    out = {"schema": SCHEMA, "id": pid, "name": name, "version": version, "description": description, "author": author,
           "items": [items[k] for k in sorted(items)], "recipes": [recipes[k] for k in sorted(recipes)]}
    if len(canonical(out)) > MAX_BYTES:
        _fail(f"the pack is larger than {MAX_BYTES // 1024} KiB")
    out["sha256"] = digest(out)
    return out


def canonical(pack: Dict[str, Any]) -> bytes:
    return json.dumps({k: v for k, v in pack.items() if k != "sha256"}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()


def digest(pack: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(pack)).hexdigest()


def describe(pack: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What the manifest, the replay bundle and the observer say about a run's pack (None: no pack)."""
    if not pack:
        return None
    return {"id": pack["id"], "name": pack["name"], "version": pack["version"], "sha256": pack["sha256"],
            "items": [i["key"] for i in pack["items"]], "recipes": [r["makes"] for r in pack["recipes"]]}


def tables(pack: Dict[str, Any]) -> Tuple[Dict[str, Item], Dict[str, Recipe]]:
    items = {i["key"]: Item(i["key"], i["name"], tuple(i["props"]), food=float(i["food"]), tool=i["tool"],
                            tool_power=float(i["tool_power"]), carry_bonus=int(i["carry_bonus"]),
                            weight=int(i["weight"]), icon=i["icon"] or "📦") for i in pack["items"]}
    recipes = {r["makes"]: Recipe(r["makes"], tuple(sorted(r["inputs"].items())), r["station"], int(r["qty"]),
                                  int(r["work"])) for r in pack["recipes"]}
    return items, recipes


def apply(catalog: Catalog, pack: Dict[str, Any]) -> None:
    """Put a validated pack into one world's catalogue. The shared base tables are not touched."""
    catalog.pack_items, catalog.pack_recipes = tables(pack)


def main(argv: Optional[List[str]] = None) -> int:
    """`python -m chits.sim.packs FILE`: check a pack and say what is in it."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m chits.sim.packs PACK.json")
        return 2
    try:
        pack = load_file(args[0])
    except PackError as e:
        print(e)
        return 1
    cat = Catalog()
    apply(cat, pack)
    print(f"OK: {pack['name']} ({pack['id']} {pack['version']}), sha256 {pack['sha256'][:16]}")
    for r in cat.pack_recipes.values():
        print(f"  {cat.describe(r)}" + (f" x{r.qty}" if r.qty > 1 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
