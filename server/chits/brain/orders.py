"""Orders: a possessed chit follows the observer's clicks and one-liners as ordinary plan steps.

The observer may possess one chit per world (see ``runtime.Runtime.possessed``) and give it age-gate orders. An order
becomes real plan steps the simulator already understands (``sim/actions.py`` VERBS), built with instinct's own
helpers (``_craft_steps``, ``_fetch_steps``, ``_need_steps``, ``_supply_steps``) and the road to the next age
(``sim/projects.py`` ``road``). No new verbs.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from .. import diag
from ..sim import projects
from ..sim.agent import Agent
from ..sim.actions import METAL_OF
from ..sim.items import DESIGNS, ITEMS, RECIPES, item_name, normalize_design, normalize_item
from .instinct import _craft_steps, _fetch_steps, _need_steps, _supply_steps, tools_first

ORDERS = ("mine", "smelt", "forge", "build", "teach", "haul", "cancel")

# survival steps a "cancel" may leave in place (they are routine, not a side quest; a bare "go" usually leads to one)
_ROUTINE = ("eat", "sleep", "rest", "shelter", "store", "drop", "refuel")

# a player's free-text mining target -> the item key the gather step needs
_MINE_TARGET = {
    "iron": "iron_ore", "copper": "ore", "ore": "ore", "ores": "ore", "clay": "clay", "sand": "sand",
    "stone": "stone", "rock": "stone", "wood": "wood", "logs": "wood", "coal": "wood", "charcoal": "wood",
}

_RAW_PRIORITY = ("iron_ore", "ore", "stone", "clay", "sand", "wood", "fiber")

_ORDER_NOT_UNDERSTOOD = "I didn't understand that; try mine/smelt/forge/build/teach/haul/cancel"


# ---------------------------------------------------------------------------------------------- parsing
def parse_order(text: Any) -> Tuple[str, Optional[str]]:
    """A deterministic keyword mapper for the natural-language field. No model. Returns ``(action, target)``."""
    raw = str(text or "").strip()
    t = " ".join(raw.lower().split())
    if not t:
        raise ValueError(_ORDER_NOT_UNDERSTOOD)
    words = t.split()
    raw_words = raw.split()
    first = words[0]
    if t in ("stop", "cancel", "drop it", "never mind", "halt", "stop the order") \
            or first in ("stop", "cancel", "halt", "cease") or t.startswith("drop it"):
        return "cancel", None
    strong = {
        "mine": ("mine", "dig", "chop", "gather", "collect", "extract", "quarry"),
        "smelt": ("smelt", "melt"),
        "forge": ("forge", "smith"),
        "build": ("build", "raise", "construct", "erect"),
        "teach": ("teach", "instruct", "show"),
        "haul": ("haul", "carry", "deliver", "transport", "fetch", "store", "stash", "deposit"),
    }
    for action in ORDERS:
        if action in strong and first in strong[action]:
            return action, _extract_target(words, raw_words, action)
    if first in ("make", "craft", "create", "produce", "fabricate"):
        return "forge", _extract_target(words, raw_words, "forge")
    raise ValueError(_ORDER_NOT_UNDERSTOOD)


def _extract_target(words: List[str], raw_words: List[str], action: str) -> Optional[str]:
    rest = words[1:]
    rrest = raw_words[1:]
    if action == "mine":
        for w in rest:
            if w in _MINE_TARGET:
                return _MINE_TARGET[w]
        return None
    if action == "smelt":
        for w in rest:
            if w in ("ore", "ores", "copper"):
                return "copper"
            if w == "iron":
                return "iron"
        return None
    if action == "forge":
        for w in rest:
            n = normalize_item(w)
            if n in ("steel", "gear", "engine", "iron", "copper", "alloy"):
                return n
        return None
    if action == "build":
        for w in rest:
            d = normalize_design(w)
            if d:
                return d
        return None
    if action == "teach":
        for w in rrest:  # a chit's name (title case) first
            if w and w[0].isupper() and normalize_design(w) is None and normalize_item(w) is None:
                return w
        for w in rest:
            if w in ITEMS or w in DESIGNS:
                return w
        return None
    return None  # haul


# ---------------------------------------------------------------------------------------------- helpers
def _unfinished_road(world) -> List[Dict[str, Any]]:
    road = projects.road(world)
    if not road:
        return []
    return [s for s in road["steps"] if not s["done"]]


def _add_raw(world, key: str, raw: set, depth: int) -> None:
    from ..sim.items import GATHER_RULES

    if depth > 4:
        return
    if key in GATHER_RULES and key not in RECIPES:
        raw.add(key)
    elif key in RECIPES:
        for m, _ in RECIPES[key].inputs:
            _add_raw(world, m, raw, depth + 1)


def _road_raw_materials(world) -> set:
    raw: set = set()
    for s in _unfinished_road(world):
        if s["kind"] == "design":
            for m, _ in DESIGNS[s["key"]].materials:
                _add_raw(world, m, raw, 0)
        else:
            r = RECIPES.get(s["key"])
            if r:
                for m, _ in r.inputs:
                    _add_raw(world, m, raw, 0)
    return raw


def _nearest_stockpile(world, a: Agent):
    piles = [p for p in world.structures_near(a.x, a.y, 25, "stockpile") if p.functional and world.same_land(a, p)]
    return min(piles, key=lambda p: p.dist(a.x, a.y), default=None)


def _stockpiles_near(world, a: Agent) -> List:
    return [p for p in world.structures_near(a.x, a.y, 25, "stockpile") if p.functional and world.same_land(a, p)]


def _open_sites(world, a: Agent, radius: int = 25) -> List:
    return [s for s in world.structures_near(a.x, a.y, radius) if not s.complete and world.same_land(a, s)]


def _plan(goal: str, thought: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"goal": goal, "thought": thought, "steps": steps}


# ---------------------------------------------------------------------------------------------- each order
def _mine_plan(world, a: Agent, target: Optional[str]) -> Dict[str, Any]:
    raw = _road_raw_materials(world)
    what = None
    if target:
        t = str(target).strip().lower()
        what = t if t in _MINE_TARGET.values() else _MINE_TARGET.get(t)
    if what is None:
        what = next((k for k in _RAW_PRIORITY if k in raw), "ore")
    steps = [{"do": "gather", "what": what, "qty": 6}]
    steps = tools_first(world, a, steps)  # a pick before the ore
    pile = _nearest_stockpile(world, a)
    if pile is not None:
        steps.append({"do": "store", "what": what, "qty": 6, "target": pile.id})
    return _plan(f"mine {item_name(what)}", f"Dig up some {item_name(what)} for the road ahead.", steps)


def _smelt_plan(world, a: Agent, target: Optional[str]) -> Dict[str, Any]:
    metals = ["copper", "iron"]
    if target in metals:
        metals = [target] + [m for m in metals if m != target]
    for m in metals:
        if a.knows_recipe(m):
            steps = _craft_steps(a, m, world=world)
            if steps:
                return _plan(f"smelt {item_name(m)}", f"Turn ore into {item_name(m)} at the furnace.", steps)
    for tool, metal in METAL_OF.items():
        if metal in ("copper", "iron") and a.inventory.get(tool, 0) > 1 and target is None:
            return _plan(f"smelt down a spare {item_name(tool)}", f"I have a spare {item_name(tool)}; melt it back.",
                         [{"do": "smelt", "what": tool}])
    raise ValueError(f"{a.name} knows no ore recipe to smelt yet")


def _forge_plan(world, a: Agent, target: Optional[str]) -> Dict[str, Any]:
    candidates: List[str] = []
    if target:
        n = normalize_item(target)
        if n and a.knows_recipe(n) and RECIPES.get(n) and RECIPES[n].station == "forge":
            candidates = [n]
    else:
        for s in _unfinished_road(world):
            r = RECIPES.get(s["key"]) if s["kind"] == "recipe" else None
            if r and r.station == "forge" and a.knows_recipe(s["key"]):
                candidates.append(s["key"])
    if not candidates:
        for k in a.knows:
            if k.startswith("recipe:"):
                key = k.split(":", 1)[1]
                r = RECIPES.get(key)
                if r and r.station == "forge":
                    candidates.append(key)
    if not candidates:
        raise ValueError(f"{a.name} knows no forge recipe yet")
    key = candidates[0]
    steps = _craft_steps(a, key, world=world)
    if not steps:
        raise ValueError(f"{a.name} can't forge {item_name(key)} here")
    return _plan(f"forge {item_name(key)}", f"Work the forge into {item_name(key)}.", steps)


def _build_design(world, a: Agent, key: str, goal: str) -> Dict[str, Any]:
    mats = DESIGNS[key].material_map
    steps = _need_steps(a, mats, world)[:4] + [{"do": "build", "what": key}]
    return _plan(goal, f"Build the {DESIGNS[key].name}.", steps)


def _help_site_plan(world, a: Agent, site, goal: str) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    room = a.free_space()
    for k, n in list(site.needs.items())[:2]:
        have = a.inventory.get(k, 0)
        if have < n:
            want = min(n - have, 3 if (k in RECIPES and a.knows_recipe(k)) else 8)
            steps += _fetch_steps(world, a, k, want, room)
            it = world.item(k)
            room -= want * max(1, it.weight if it else 1)
    steps.append({"do": "help", "site": site.id})
    return _plan(goal, "Pitch in on the build.", steps)


def _build_plan(world, a: Agent, target: Optional[str]) -> Dict[str, Any]:
    if target:
        d = normalize_design(target)
        if d is None or not a.knows_design(d):
            raise ValueError(f"{a.name} doesn't know how to build {target}")
        return _build_design(world, a, d, f"build a {DESIGNS[d].name}")
    for s in _unfinished_road(world):
        if s["kind"] == "design" and a.knows_design(s["key"]):
            return _build_design(world, a, s["key"], f"build the {s['name']}")
    sites = _open_sites(world, a)
    if sites:
        s = min(sites, key=lambda x: x.dist(a.x, a.y))
        return _help_site_plan(world, a, s, f"help build the {DESIGNS[s.design].name}")
    if a.knows_design("stockpile"):
        return _build_design(world, a, "stockpile", "build a stockpile")
    raise ValueError(f"{a.name} knows nothing left to build")


def _teach_plan(world, a: Agent, target: Optional[str]) -> Dict[str, Any]:
    others = [o for o in world.agents.values() if o.id != a.id]
    if not others:
        raise ValueError(f"{a.name} has no one to teach")
    road_keys = {f"{s['kind']}:{s['key']}" for s in _unfinished_road(world)}

    def teachable() -> List[str]:
        crit = [k for k in a.knows if k in road_keys and a.knows[k]["how"] != "instinct"]
        rest = [k for k in a.knows if a.knows[k]["how"] != "instinct" and k not in road_keys]
        return crit + rest

    def dist(o) -> int:
        return max(abs(o.x - a.x), abs(o.y - a.y))

    learner: Optional[Agent] = None
    what: Optional[str] = None
    if target:
        by_name = next((o for o in others if o.name.lower() == target.lower()), None)
        tkey = f"recipe:{target}" if f"recipe:{target}" in a.knows else (
            f"design:{target}" if f"design:{target}" in a.knows else None)
        if by_name is not None:
            learner = by_name
            opts = [k for k in teachable() if k not in learner.knows]
            if not opts:
                raise ValueError(f"{learner.name} already knows everything {a.name} could teach")
            what = opts[0]
        elif tkey is not None:
            what = tkey
            learner = min((o for o in others if tkey not in o.knows), key=dist, default=None)
            if learner is None:
                raise ValueError(f"everyone already knows {target}")
        else:
            raise ValueError(f"{a.name} knows nothing called {target} to teach")
    else:
        opts = teachable()
        if not opts:
            raise ValueError(f"{a.name} knows nothing worth teaching")
        learners = [o for o in others if any(k not in o.knows for k in opts)]
        if not learners:
            raise ValueError(f"everyone already knows what {a.name} does")
        learner = min(learners, key=dist)
        what = next(k for k in opts if k not in learner.knows)

    kind, key = what.split(":", 1)
    nm = world.item_name(key) if kind == "recipe" else (DESIGNS[key].name if key in DESIGNS else key.replace("_", " "))
    return _plan(f"teach {learner.name} {nm}", f"{learner.name} doesn't know about {nm} yet.",
                 [{"do": "teach", "to": learner.name, "what": what}])


def _haul_plan(world, a: Agent, target: Optional[str]) -> Dict[str, Any]:
    mats = [k for k, n in a.inventory.items() if n > 0 and (it := a._item(k)) and not it.tool and not it.carry_bonus]
    if mats:
        pile = _nearest_stockpile(world, a)
        if pile is not None:
            return _plan("store my load", "Carry these to the stockpile.",
                         [{"do": "store", "what": "all", "target": pile.id}])
        raise ValueError(f"{a.name} is carrying things but no stockpile is in reach")
    sites = _open_sites(world, a)
    if sites:
        site = min(sites, key=lambda x: x.dist(a.x, a.y))
        for k, n in site.needs.items():
            pile = next((p for p in _stockpiles_near(world, a) if p.storage.get(k, 0) > 0), None)
            if pile is not None:
                qty = min(n, pile.storage.get(k, 0))
                return _plan(f"haul {item_name(k)} to the build", f"The build needs {item_name(k)}.",
                             [{"do": "take", "what": k, "qty": qty, "target": pile.id},
                              {"do": "help", "site": site.id}])
    raise ValueError(f"{a.name} has nothing to haul")


def order_plan(world, a: Agent, action: str, target: Optional[str] = None) -> Dict[str, Any]:
    """Build the plan for an order, or raise ValueError with a friendly reason when it can't be done."""
    if action == "mine":
        return _mine_plan(world, a, target)
    if action == "smelt":
        return _smelt_plan(world, a, target)
    if action == "forge":
        return _forge_plan(world, a, target)
    if action == "build":
        return _build_plan(world, a, target)
    if action == "teach":
        return _teach_plan(world, a, target)
    if action == "haul":
        return _haul_plan(world, a, target)
    if action == "cancel":
        return _plan("", "", [])
    raise ValueError(f"unknown order {action!r}; try one of {', '.join(ORDERS)}")


# ---------------------------------------------------------------------------------------------- applying
def apply_order(world, a: Agent, action: str, plan: Dict[str, Any], mind=None) -> Dict[str, Any]:
    """Set the plan the order built, or (for "cancel") clear the side quest. Marks every step as the player's."""
    if action == "cancel":
        return _apply_cancel(world, a, mind)
    a.plan = list(plan.get("steps") or [])
    for step in a.plan:
        step["_origin"] = "player"
    a.goal = plan.get("goal") or a.goal
    a.thought = plan.get("thought") or a.thought
    a.plan_source = "player"
    a.plan_started = world.tick
    a.plan_id = uuid.uuid4().hex
    if a.pending_plan is not None:
        a.pending_plan = None
        rec = getattr(a, "_decision", None)
        if rec is not None:
            rec["stale_why"] = "player order"
            if mind is not None:
                mind._resolve(rec, "stale", world.tick)
    a.bump_rev("player order")
    diag.of(world).authorship["player"] += 1
    world.emit("player", f"{a.name} takes an order: {a.goal}", 2, a.id, a.x, a.y)
    return plan


def _apply_cancel(world, a: Agent, mind=None) -> Dict[str, Any]:
    a.plan = [s for s in a.plan if s.get("do") in _ROUTINE]
    if a.pending_plan is not None:
        a.pending_plan = None
        rec = getattr(a, "_decision", None)
        if rec is not None:
            rec["stale_why"] = "player order"
            if mind is not None:
                mind._resolve(rec, "stale", world.tick)
    a.objective = ""
    a.objective_since = -1
    a.goal = ""
    a.thought = "Side quest dropped."
    a.plan_source = "player"
    a.plan_started = world.tick
    a.plan_id = uuid.uuid4().hex
    a.bump_rev("player: cancel sidequest")
    diag.of(world).authorship["player"] += 1
    world.emit("player", f"{a.name} dropped their side quest", 2, a.id, a.x, a.y)
    return _plan("", "", [])
