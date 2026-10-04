"""Step executor: turns a brain's proposed plan into physical consequences.

Each step is a dict like {"do": "gather", "what": "wood", "qty": 5}. ``advance``
runs one tick of it and returns RUNNING, DONE or a failure string. The world is
authoritative — a brain can ask for anything, but only lawful things happen.
"""

from __future__ import annotations

import math
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from .. import diag
from . import buildings as BLD
from . import terrain as T
from .agent import Agent, TICKS_PER_DAY
from .items import (
    ORE_KINDS,
    HOME_STORES,
    ACTION_USES, DESIGNS, GATHER_RULES, ITEMS, RECIPES, STATIONS, STORES, item_name, match_recipe, normalize_design,
    normalize_item,
)

RUNNING = "running"
DONE = "done"

VERBS = (
    "gather", "eat", "sleep", "craft", "experiment", "build", "upgrade", "help", "store", "take", "give", "say", "teach",
    "write", "read", "inspect", "explore", "go", "refuel", "plant", "harvest", "repair", "rest", "wander", "warm_up",
    "drop", "mark", "shelter", "invent", "pray", "preach", "trade", "steal", "guard", "fight", "pickup", "sail", "hunt", "tame",
    "prospect",
    "work", "study", "smelt",
)

VERB_ALIASES = {
    "collect": "gather", "chop": "gather", "mine": "gather", "pick": "gather", "forage": "gather", "fish": "gather",
    "get": "gather", "cut": "gather", "dig": "gather", "chase": "hunt", "domesticate": "tame", "herd": "tame",
    "consume": "eat", "make": "craft", "create": "craft", "combine": "experiment", "try": "experiment",
    "test": "experiment", "devise": "invent", "innovate": "invent", "imagine": "invent", "construct": "build", "contribute": "help", "assist": "help",
    "deliver": "help", "join": "help", "deposit": "store", "stash": "store", "withdraw": "take", "fetch": "take",
    "talk": "say", "speak": "say", "tell": "say", "message": "say", "shout": "say", "chat": "say",
    "share": "teach", "show": "teach", "inscribe": "write", "record": "write", "research": "study", "examine": "inspect",
    "look": "inspect", "observe": "inspect", "scout": "explore", "move": "go", "walk": "go", "goto": "go",
    "travel": "go", "visit": "go", "fuel": "refuel", "stoke": "refuel", "sow": "plant", "reap": "harvest",
    "fix": "repair", "maintain": "repair", "wait": "rest", "idle": "rest", "roam": "wander", "warm": "warm_up",
    "improve": "upgrade", "enlarge": "upgrade", "expand": "upgrade", "extend": "upgrade", "rebuild": "upgrade",
    "gift": "give", "hand": "give", "barter": "trade", "swap": "trade", "exchange": "trade", "discard": "drop", "throw": "drop",
    "sign": "mark", "signpost": "mark", "label": "mark",
    "rob": "steal", "pilfer": "steal", "raid": "steal", "protect": "guard", "watch": "guard", "defend": "guard",
    "attack": "fight", "hit": "fight", "brawl": "fight",
    "voyage": "sail", "row": "sail", "set_sail": "sail",
    "pick_up": "pickup", "grab": "pickup", "collect_item": "pickup", "loot": "pickup",
    "take_cover": "shelter", "go_inside": "shelter", "hide": "shelter", "cover": "shelter",
    "operate": "work", "man": "work", "tend": "work", "run": "work",
    "melt": "smelt", "melt_down": "smelt", "recycle": "smelt", "scrap": "smelt", "mend": "repair", "resharpen": "repair",
}

STOCKPILE_CAP = 240
GOODS_SHARE = 0.7  # materials may fill at most this share of a stockpile; the rest is kept for food


STORE_CAP = {"warehouse": STOCKPILE_CAP * 4}  # (a stockpile or an outpost camp's store holds STOCKPILE_CAP)


def store_cap(st) -> int:
    return STORE_CAP.get(st.design, STOCKPILE_CAP)


def stockpile_room(st, item: Optional[str] = None, catalog=None) -> int:
    """How many more of `item` (or of any material, if None) this stockpile will take. `catalog`: the world's, so
    that a content pack's food counts as food here too."""
    cap = store_cap(st)
    space = cap - sum(st.storage.values())
    if item is not None and is_food(item, catalog):
        return max(0, space)
    goods = sum(n for k, n in st.storage.items() if not is_food(k, catalog))
    return max(0, min(space, int(cap * GOODS_SHARE) - goods))
SIGN_SYMBOLS = ("food", "wood", "stone", "clay", "ore", "fish", "danger", "home", "build", "meet")
SIGN_ALIASES = {"berries": "food", "berry": "food", "warning": "danger", "gather": "meet", "copper": "ore",
                "house": "home", "logs": "wood", "rock": "stone"}
SIGN_TTL = 720  # signs weather away after three days
SCARCE = ("sand", "clay", "ore", "iron_ore")
SCARCE_RADIUS = 72  # tiles a chit will walk for a scarce material its mind asked for
CAMP_SLEEP, CAMP_FAR = 12, 30  # a chit this far from home sleeps at an outpost camp this close

FOODS = ("loaf", "bread", "berry_tart", "cooked_meat", "cooked_fish", "meat", "fish", "berries", "grain")


def is_food(key: str, catalog=None) -> bool:
    """Food as the stores see it: the base foods, a content pack's items that feed (sim/packs.py) and this world's
    invented dishes (F34: they were stored as goods, and taken out by nobody). Without a pack or an invented dish this
    is exactly `key in FOODS`."""
    if key in FOODS:
        return True
    if catalog is None:
        return False
    dish = catalog.items.get(key) if catalog.items else None
    if dish is not None:
        return dish.food > 0
    packed = catalog.pack_items.get(key) if catalog.pack_items else None
    return packed is not None and packed.food > 0 and key not in ITEMS


def foods_of(world) -> Tuple[str, ...]:
    """What a hungry chit looks for in a store or on the ground: the base foods, then this world's invented dishes.
    Without one this is FOODS itself."""
    made = world.catalog.items
    if not made:
        return FOODS
    return FOODS + tuple(k for k, it in made.items() if it.food > 0)


def kept_in_hand(world, key: str) -> int:
    """How many of these stay with the chit when it puts its load down: a bite of food, and one of an invention that
    does something while carried (a coat, a remedy, a hoe). Tools and containers are never part of the load."""
    if world.catalog.items and world.invention_carried(key):
        return 1
    return 2 if is_food(key, world.catalog) else 0


def metal_of(world, tool: Optional[str]) -> Optional[str]:
    """The metal in a metal tool: a base tool's (METAL_OF), or an invented tool's own (invent.METALS)."""
    if tool in METAL_OF:
        return METAL_OF[tool]
    inv = world.invention(tool) if world.catalog.items and tool else None
    if inv is None or not (it := world.item(tool)) or not it.tool:
        return None
    from .invent import invention_metal

    return invention_metal(inv)


def food_items(a: Agent) -> List[str]:
    # a world's own invented dishes (T20) count as food too; they're filling, so they go first
    # (and so does food from a content pack, sim/packs.py)
    packed = a.catalog.pack_items if a.catalog is not None else {}
    mine = [k for k, n in a.inventory.items() if n > 0 and (k.startswith("inv_") or k in packed)
            and (it := a._item(k)) and it.food > 0]
    return mine + [f for f in FOODS if a.inventory.get(f, 0) > 0]


def normalize_verb(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in VERBS:
        return s
    if s in VERB_ALIASES:
        return VERB_ALIASES[s]
    s2 = s.split("_")[0]
    if s2 in VERBS:
        return s2
    return VERB_ALIASES.get(s2)


# ---------------------------------------------------------------------------- driver

def run(world, a: Agent) -> None:
    t = world.tick
    if a.emote and t > a.emote_until:
        a.emote = ""
    if a.say and t > a.say_until:
        a.say = ""
    if not a.plan:
        a.activity = "thinking" if a.thinking else "idle"
        return
    step = a.plan[0]
    step.setdefault("_step_id", uuid.uuid4().hex)
    step.setdefault("_tick_started", world.tick)
    try:
        res = advance(world, a, step)
    except Exception as e:  # never let one bad step crash the world
        res = f"something went wrong ({type(e).__name__})"
    if res == RUNNING:
        return
    diag.action_finished(world, a, step, res)
    a.plan.pop(0)
    a.path = []
    a.work_acc = 0.0
    if res == DONE:
        diag.step_done(world, a, str(step.get("do")))
        note = step.get("_s", {}).get("note")
        if note:
            a.last_result = note
        return
    # failure: remember it, drop the rest of the plan so the brain can rethink
    diag.step_failed(world, a, str(step.get("do")), str(res), str(step.get("what") or step.get("target") or ""),
                     "reflex" if step.get("_reflex") else str(step.get("_origin") or a.plan_source or ""))
    a.bump_rev("a step failed")
    a.last_result = f"Could not {describe_step(step)}: {res}"
    a.remember(t, a.last_result, 2, "failure")
    a.bump("failures")
    if step.get("_reflex"):
        # a failed reflex came straight back the next tick, forever (one chit failed the same pickup 384 times):
        # rest it briefly so the chit's own plan gets a turn
        kind = REFLEX_KIND.get(str(step.get("do")), str(step.get("do")))
        a.reflex_rest[kind] = max(a.reflex_rest.get(kind, 0), world.tick + REFLEX_RETRY)
    if step.get("_origin") in ("model_generated", "model_selected"):
        # bounded action repair (research plan item 40): the model hears exactly why, once (brain/mind.py _ask); a
        # repaired plan that fails again gets no second repair
        a.__dict__["_repair"] = {"failed": describe_step(step), "reason": str(res), "tick": t,
                                 "decision_id": step.get("_decision_id"),
                                 "dropped": [describe_step(s) for s in a.plan if not s.get("_filler")][:5]}
    if not step.get("_reflex"):
        a.plan.clear()
    elif step.get("do") in ("shelter", "warm_up") and ("nowhere" in str(res) or "couldn't reach" in str(res)):
        a.reflex_rest[str(step["do"])] = t + REFLEX_REST


def describe_step(step: Dict[str, Any]) -> str:
    v = step.get("do", "?")
    if v == "work":
        at = step.get("at") or step.get("what") or step.get("target")
        return f"work at the {at}" if at else "work"
    bits = [v]
    for k in ("what", "with", "to", "target", "site", "dir", "at", "purpose", "text"):
        if step.get(k):
            val = step[k]
            if isinstance(val, list):
                val = " + ".join(str(x) for x in val)
            bits.append(str(val) if k != "text" else f'"{str(val)[:40]}"')
    if step.get("qty"):
        bits.append(f"x{step['qty']}")
    return " ".join(bits)


REFLEX_KIND = {"eat": "food", "harvest": "food", "gather": "food", "pickup": "food", "store": "room", "drop": "room"}
REFLEX_RETRY = 20
SNACK_BELOW = 40  # a chit carrying food eats it when hunger falls below this
MEAL_RADIUS = 12  # ...or walks this far to a stockpile with food  # ticks a reflex waits after its step failed
REFLEX_REST = 60  # ticks (6 in-game hours) a shelter/warm_up reflex stays quiet after finding nowhere to go


def reflexes(world, a: Agent) -> None:
    """Survival reflexes shared by every brain. They interrupt, they don't plan."""
    n = len(a.plan)
    _reflexes(world, a)
    if len(a.plan) > n:
        a.bump_rev("a survival reflex took over")  # the situation changed enough to interrupt: a plan asked for before this is stale


def _reflexes(world, a: Agent) -> None:
    head = a.plan[0] if a.plan else {}
    if head.get("_reflex"):
        # ...except that starving beats waiting out the weather, warming up or sleeping (chits starved under
        # those reflexes, which only end when the weather clears or they're warm or rested), or carrying a load to
        # the store (one starved on a 120-tile walk to a stockpile a bridge had put within reach)
        if head.get("do") in ("shelter", "warm_up", "sleep", "store") and a.hunger < 8:
            food = _food_reflex(world, a)
            if food.get("do") != "explore":
                a.plan.insert(0, dict(food, _reflex=True))
        elif head.get("do") == "shelter" and a.energy < 7 and world.sheltered(a):
            a.plan.insert(0, {"do": "sleep", "_reflex": True})  # sleeping under cover is still under cover
        return
    hv = head.get("do")
    # already fetching food is fine, unless it's nearly too late and there's food in hand: chits starved at
    # hunger 8 carrying berries while they gathered more
    fetching = hv == "gather" and head.get("what") in ("berries", "fish") and not (a.hunger < 10 and food_items(a))
    if SNACK_BELOW > a.hunger >= 16 and food_items(a) and hv not in ("eat", "sleep") and not fetching \
            and a.activity != "sleeping":
        # a bite of what it carries: instinct eats below 45, but a model-driven chit only ate when starving and
        # lived at hunger 16-45, never fed enough to have children
        a.plan.insert(0, {"do": "eat", "_reflex": True})
        return
    if SNACK_BELOW > a.hunger >= 16 and hv not in ("eat", "sleep", "harvest") and not fetching \
            and a.activity != "sleeping" and a.reflex_rest.get("food", 0) <= world.tick \
            and _stockpile_with(world, a, foods_of(world), MEAL_RADIUS):
        # mealtime: World A kept 185 grain and 81 berries in store while its model-driven adults sat at hunger 11-40,
        # too hungry to have children (instinct eats below 45; a model plan rarely says "eat")
        a.plan.insert(0, {"do": "eat", "_reflex": True})
        return
    if a.hunger < 16 and hv not in ("eat", "harvest") and not fetching and a.reflex_rest.get("food", 0) <= world.tick:
        a.plan.insert(0, dict(_food_reflex(world, a), _reflex=True))
        a.set_emote("😣", world.tick, 20)
        return
    if a.energy < 7 and hv != "sleep" and a.reflex_rest.get("sleep", 0) <= world.tick:
        a.plan.insert(0, {"do": "sleep", "_reflex": True})
        return
    wx = getattr(world, "weather", "clear")
    if (wx == "storm" or (wx == "snow" and a.warmth < 60)) and hv not in ("shelter", "sleep", "eat", "warm_up") \
            and not world.sheltered(a) and a.reflex_rest.get("shelter", 0) <= world.tick:
        # common sense, for every mind: get out of the weather
        a.plan.insert(0, {"do": "shelter", "_reflex": True})
        a.set_emote("⛈" if wx == "storm" else "🌨", world.tick, 20)
        return
    if hv in ("gather", "pickup", "take") and a.free_space() <= 0 and a.reflex_rest.get("room", 0) <= world.tick:
        # arms full: put the load down before gathering more (a body reflex, whoever is thinking)
        pile = _stockpile_with_room(world, a)
        if pile:
            a.plan.insert(0, {"do": "store", "what": "all", "target": pile.id, "_reflex": True})
        else:
            junk = max((k for k in a.inventory if a.inventory[k] > 0 and not world.item(k).tool and not world.item(k).carry_bonus
                        and k not in FOODS and not (world.catalog.items and (world.invention_carried(k) or world.item(k).food))),
                       key=lambda k: a.inventory[k], default=None)
            if junk:
                a.plan.insert(0, {"do": "drop", "what": junk, "qty": max(1, a.inventory[junk] // 2), "_reflex": True})
        return
    if a.warmth < 22 and hv not in ("warm_up", "sleep") and world.temperature() < 0.42 \
            and a.reflex_rest.get("warm_up", 0) <= world.tick:
        a.plan.insert(0, {"do": "warm_up", "_reflex": True})
        a.set_emote("🥶", world.tick, 20)


def _stockpile_with_room(world, a: Agent):
    for p in world.structures_near(a.x, a.y, 25, "stockpile"):
        if p.functional and stockpile_room(p, None, world.catalog) > 10 and a.reflex_rest.get("unreach:" + p.id, 0) <= world.tick:
            return p
    return None


def _food_reflex(world, a: Agent) -> Dict[str, Any]:
    if food_items(a):
        return {"do": "eat"}
    # the nearest food, not always the stockpile first: from hunger 16 a chit has ~70 ticks, and an exhausted one
    # walks 0.4 tiles a tick, so chits starved on the way to a pile 30 tiles off with berries a few tiles away
    here = (a.x, a.y)
    d = lambda x, y: max(abs(x - here[0]), abs(y - here[1]))
    opts = []
    foods = foods_of(world)
    pile = _stockpile_with(world, a, foods, 30)
    if pile:
        opts.append((d(*pile.center()), {"do": "eat"}))
    farm = _farm_ready(world, a)
    if farm:
        opts.append((d(*farm.center()), {"do": "harvest", "target": farm.id}))
    ground = next(((px, py, k) for px, py, p in world.piles_near(a.x, a.y, FORAGE_RADIUS)
                   for k in foods if p.get(k, 0) > 0 and world.same_land_xy(a, px, py)
                   and a.reflex_rest.get(f"unreach:{px},{py}", 0) <= world.tick), None)
    if ground:
        opts.append((d(ground[0], ground[1]), {"do": "pickup", "what": ground[2]}))
    berry = world.nearest_resource(a.x, a.y, "berries", 34)
    if berry:
        opts.append((d(*berry) + 2, {"do": "gather", "what": "berries", "qty": 3}))  # +2: picking takes a moment
    if opts:
        best = min(opts, key=lambda o: o[0])[1]
        if best.get("do") == "gather" and a.best_tool("spear") and world.nearest_resource(a.x, a.y, "fish", 8):
            return {"do": "gather", "what": "fish", "qty": 3}
        return best
    if _farm_ready(world, a):
        return {"do": "harvest"}
    if a.best_tool("spear") and world.nearest_resource(a.x, a.y, "fish", 20):
        return {"do": "gather", "what": "fish", "qty": 3}
    if world.nearest_resource(a.x, a.y, "berries", 34):
        return {"do": "gather", "what": "berries", "qty": 3}
    return {"do": "explore"}


# ---------------------------------------------------------------------------- movement helpers

def _speed(world, a: Agent) -> float:
    sp = 0.55
    if world.catalog.items and (boost := world.invention_effect(a, "speed")):
        sp *= boost  # shoes, a sledge: an invention for speed, as fast as what it is made of (invent.py)
    if a.is_child(world.tick):
        sp *= 0.8
    if a.energy < 20:
        sp *= 0.7
    if a.load() > a.capacity() * 0.9:
        sp *= 0.85
    return sp


def move_toward(world, a: Agent, s: Dict[str, Any], goals: Set[Tuple[int, int]]) -> str:
    """Advance along a path to any goal tile. Returns 'arrived', 'moving' or 'blocked'."""
    if (a.x, a.y) in goals:
        return "arrived"
    if not a.path or s.get("goal_sig") != hash(frozenset(list(goals)[:30])):
        path = world.find_path(a.x, a.y, goals)
        if path is None:
            return "blocked"
        a.path = path
        s["goal_sig"] = hash(frozenset(list(goals)[:30]))
    a.activity = "walking"
    a.move_acc += _speed(world, a)
    moved = 0
    while a.path and moved < 4:
        nx, ny = a.path[0]
        c = world.move_cost(nx, ny) * (1.41 if nx != a.x and ny != a.y else 1.0)
        if a.move_acc < c:
            break
        if not world.passable(nx, ny):
            a.path = []
            return "moving"
        a.move_acc -= c
        a.x, a.y = nx, ny
        a.path.pop(0)
        moved += 1
    if (a.x, a.y) in goals:
        a.move_acc = 0.0
        return "arrived"
    if not a.path:
        return "blocked" if (a.x, a.y) not in goals and s.get("repath", 0) > 3 else _repath(s)
    return "moving"


LONG_WAY = 4.0  # a walk this many times the distance as the crow flies (and 40+ steps) is "a long way round"


def _long_way(a: Agent, s: Dict[str, Any], x: int, y: int) -> bool:
    """The walk just planned to (x, y) is far longer than the distance as the crow flies (checked once per place):
    round a lake, or over a bridge that joined the village to land that wraps a long way round. Food or a store that
    far isn't nearby: chits starved on 150-tile walks to berries 20 tiles away."""
    if s.get("way") == [x, y]:
        return False
    s["way"] = [x, y]
    return len(a.path) > max(40, LONG_WAY * max(abs(a.x - x), abs(a.y - y)))


def _repath(s: Dict[str, Any]) -> str:
    s["repath"] = s.get("repath", 0) + 1
    s.pop("goal_sig", None)
    return "moving"


def _goto_structure(world, a: Agent, s: Dict[str, Any], st) -> str:
    goals = world.stand_tiles_for_structure(st)
    if st.design in BLD.HOMES + ("farm", "stockpile", "campfire"):
        goals |= {c for c in st.cells() if world.passable(*c)}
    if st.design == "campfire":
        goals = {g for g in goals if g not in set(st.cells())} or goals
    return move_toward(world, a, s, goals)


def _work(a: Agent, amount: float, need: float) -> bool:
    a.work_acc += amount
    if a.work_acc >= need:
        a.work_acc -= need
        return True
    return False


def _stockpile_with(world, a: Agent, items, radius: int = 25):
    """The nearest working stockpile holding any of `items` that this chit can walk to."""
    for st in world.structures_near(a.x, a.y, radius, "stockpile"):
        if st.functional and any(st.storage.get(i, 0) > 0 for i in items) \
                and a.reflex_rest.get("unreach:" + st.id, 0) <= world.tick and world.same_land(a, st):
            return st
    return None


def _farm_ready(world, a: Agent):
    for st in world.structures_near(a.x, a.y, 30, "farm"):
        if st.functional and st.planted and st.growth >= 1.0 and a.reflex_rest.get("unreach:" + st.id, 0) <= world.tick:
            return st
    return None


def _find_structure(world, a: Agent, ref: Any, radius: int = 40, pred=None):
    """Resolve a structure reference: id, design name, or None = nearest matching pred."""
    if ref:
        r = str(ref).strip()
        st = world.structures.get(r)
        if st:
            return st
        dk = normalize_design(r)
        if dk:
            for st in world.structures_near(a.x, a.y, radius, dk):
                if pred is None or pred(st):
                    return st
            return None
    for st in world.structures_near(a.x, a.y, radius):
        if pred is None or pred(st):
            return st
    return None


def _qty(step: Dict[str, Any], default: int, lo: int = 1, hi: int = 30) -> int:
    try:
        return max(lo, min(hi, int(float(step.get("qty") or default))))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------- the verbs

def advance(world, a: Agent, step: Dict[str, Any]) -> str:
    verb = normalize_verb(step.get("do"))
    if not verb:
        return f"'{step.get('do')}' is not something a chit can do"
    step["do"] = verb
    s = step.setdefault("_s", {})
    s["ticks"] = s.get("ticks", 0) + 1
    if s["ticks"] > 900:
        return "it was taking far too long"
    fn = globals()[f"_do_{verb}"]
    return fn(world, a, step, s)


def _do_gather(world, a: Agent, step, s) -> str:
    kind = world.norm_item(step.get("what"))
    if kind is not None and kind not in GATHER_RULES and _stockpile_with(world, a, [kind], 30):
        # made things don't grow on the land: take them from the stockpile that holds them ("gather brick" x386)
        return _do_take(world, a, dict(step, do="take"), s)
    if kind is None or kind not in GATHER_RULES:
        if kind == "grain":
            return "grain doesn't grow wild: harvest a ripe farm, or take grain from a stockpile"
        return f"{step.get('what')} can't be gathered from the land"
    rule = GATHER_RULES[kind]
    tool = a.best_tool(rule["tool"]) if rule["tool"] else None
    if rule["requires"] and not tool:
        need = {"pick": "a pick", "spear": "a spear"}[rule["tool"]]
        how = {"pick": "stone_pick", "spear": "spear"}[rule["tool"]]
        hint = f" (you know how to make a {world.item_name(how)})" if a.knows_recipe(how) else ""
        return f"I need {need} to get {world.item_name(kind)}{hint}"
    want = s.setdefault("want", _qty(step, 5))
    got = s.setdefault("got", 0)
    if got >= want:
        s["note"] = f"Gathered {got} {world.item_name(kind)}"
        return DONE
    if a.free_space() < world.item(kind).weight and kind in FOODS and a.hunger < 40:
        _drop_for_room(world, a, world.item(kind).weight)
    if a.free_space() < world.item(kind).weight:
        s["note"] = f"Gathered {got} {world.item_name(kind)} (hands full)"
        return DONE if got else "my hands are full"
    if s.get("mine"):
        mine = world.structures.get(s["mine"])
        if mine is not None and mine.functional and (mine.storage.get(kind, 0) > 0 or kind in BLD.DEEP_DIG):
            return _dig_mine(world, a, s, mine, tool, rule, kind)
        s.pop("mine", None)
    tgt = s.get("tile")
    if tgt is None or world.res_amt[tgt] <= 0:
        pos = world.nearest_resource(a.x, a.y, kind, 34 if kind in ("berries", "fish") else 26, set(s.setdefault("avoid", [])))
        if pos is None and kind in BLD.PIT_OF:
            mine = BLD.mine_near(world, a, BLD.PIT_REACH, kind)  # (26 left pits sited 27-30 away unused, Codex #32)
            if mine is not None:  # the deposits near here are dug out: the mine's seam (or the sand pit)
                s["mine"] = mine.id
                return _dig_mine(world, a, s, mine, tool, rule, kind)
        if pos is None and kind in SCARCE and (str(a.plan_source).startswith("model")):
            # sand lies only by coasts and lakes: on a 512 map World B's village was 32 tiles from it, and "no sand
            # anywhere nearby" kept every brick house from being built. When its mind decides sand is worth the
            # walk, it goes. (Instinct stays local: sending it far cost 2 discoveries and 9 chits per 30 days.)
            pos = world.nearest_resource(a.x, a.y, kind, SCARCE_RADIUS, set(s["avoid"]))
        if pos is None:
            if got:
                s["note"] = f"Gathered {got} {world.item_name(kind)}; no more nearby"
                return DONE
            a.reflex_rest["scarce:" + kind] = world.tick + TICKS_PER_DAY  # instinct won't plan on it for a day
            seen = remembered_place(world, a, kind)
            if seen:
                camp = " (or an outpost camp beside it)" if a.knows_design("outpost") else ""
                return (f"there is no {world.item_name(kind)} nearby; you remember some at ({seen[0]},{seen[1]}), "
                        f"{max(abs(seen[0] - a.x), abs(seen[1] - a.y))} tiles away: go there{camp}")
            if kind in ORE_KINDS and any(m.functional for m in world.structures_near(a.x, a.y, 26, "mine")):
                return "the mine's seam is dug out for today; it fills again tomorrow"
            if kind in ORE_KINDS and a.knows_design("mine"):
                return f"there is no {world.item_name(kind)} anywhere nearby — a mine dug by the rocks would give some every day"
            return f"there is no {world.item_name(kind)} anywhere nearby — maybe explore"
        tgt = pos[1] * world.w + pos[0]
        s["tile"] = tgt
        a.path = []
    tx, ty = tgt % world.w, tgt // world.w
    mv = move_toward(world, a, s, world.stand_tiles_for(tx, ty))
    if mv == "moving" and _long_way(a, s, tx, ty):
        mv = "blocked"  # a long way round isn't nearby: look for some closer on foot
    if mv == "blocked":
        s["avoid"].append(tgt)
        s.pop("tile", None)
        a.path = []
        return RUNNING
    if mv != "arrived":
        return RUNNING
    a.activity = f"gathering {world.item_name(kind)}"
    power = world.item(tool).tool_power if tool else 1.0
    if not _work(a, a.skill_speed("gathering") * (1.1 if a.mood > 70 else 1.0), float(rule["work"])):
        return RUNNING
    i = tgt
    if kind == "seeds":
        # rummaging through fiber-grass for seed heads
        n = 1 if world.rng_for("agents").random() < 0.55 else 0
        if world.rng_for("agents").random() < 0.3:
            world.res_amt[i] -= 1
            world.dirty_res.add(i)
    else:
        n = min(world.res_amt[i], max(1, int(round(power))))
        world.res_amt[i] -= n
        world.dirty_res.add(i)
        if kind == "berries" and world.rng_for("agents").random() < 0.22 and not seeds_plenty(world, a.x, a.y):
            a.add("seeds", 1)  # (the pips: kept only while the stores are short of seed)
        if kind == "wood" and n and BLD.sawn(world, a.x, a.y):
            n *= 2  # (the sawmill cuts each log into twice the wood: the forest isn't felled any faster)
        if kind == "fish" and n and BLD.fished(world, a.x, a.y):
            n *= 2  # (a harbour's boats bring in as many again)
    added = a.add(kind, n) if n else 0
    s["got"] = got + added
    a.practice("gathering", 0.4)
    a.bump(f"gathered_{kind}", added)
    if kind == "fish":
        a.bump("fish", added)
    if tool:
        _wear(world, a, tool)
    world.notice_items(a)
    if world.res_amt[i] <= 0:
        s.pop("tile", None)
        if kind == "wood" and world.rng_for("agents").random() < 0.02:
            world.emit("note", f"{a.name} felled the last tree of a grove", 1, a.id, a.x, a.y)
    return RUNNING


def _dig_mine(world, a: Agent, s, mine, tool, rule, kind: str = "ore") -> str:
    """Dig ore from a mine's seam (or sand from a sand pit): like working a deposit (the same work per swing, tool and
    wear)."""
    place = DESIGNS[mine.design].name
    mv = _goto_structure(world, a, s, mine)
    if mv == "blocked":
        a.reflex_rest["unreach:" + mine.id] = world.tick + TICKS_PER_DAY
        s.pop("mine", None)
        return f"couldn't reach the {place}"
    if mv != "arrived":
        return RUNNING
    deep = mine.storage.get(kind, 0) <= 0 and kind in BLD.DEEP_DIG  # the day's seam is out: dig deeper, slowly
    a.activity = f"digging {'deep ' if deep else ''}in the {place}"
    power = world.item(tool).tool_power if tool else 1.0
    work = float(rule["work"]) * (BLD.DEEP_DIG[kind] if deep else 1.0)
    if not _work(a, a.skill_speed("gathering") * (1.1 if a.mood > 70 else 1.0), work):
        return RUNNING
    if deep:
        n = min(max(1, int(round(power))), s["want"] - s["got"])
    else:
        n = min(mine.storage.get(kind, 0), max(1, int(round(power))), s["want"] - s["got"])
        mine.storage[kind] = mine.storage.get(kind, 0) - n
    world.dirty_struct.add(mine.id)
    added = a.add(kind, n) if n > 0 else 0
    s["got"] += added
    a.practice("gathering", 0.4)
    a.bump(f"gathered_{kind}", added)
    a.bump("mined", added)
    if tool:
        _wear(world, a, tool)
    world.notice_items(a)
    if not added:
        return "my hands are full" if a.free_space() <= 0 else f"the {place} is dug out for today"
    if s["got"] >= s["want"]:
        s["note"] = f"Dug {s['got']} {world.item_name(kind)} from the {place}"
        return DONE
    return RUNNING


def _drop_for_room(world, a: Agent, need: int) -> None:
    """A hungry chit puts down its least precious load to make room for food: raw materials first, then other goods
    (chits starved beside stores of grain holding 22 charcoal from a kiln), then spare tools (they starved carrying 8
    stone picks). What it drops stays on the ground."""
    from . import artifacts as ART

    order = ["stone", "sand", "wood", "clay", "fiber", "ore", "iron_ore", "seeds"]
    kept = (lambda k: world.invention_carried(k)) if world.catalog.items else (lambda k: False)  # a coat, a hoe: like a tool
    order += sorted((k for k, n in a.inventory.items() if k not in order and k not in FOODS and (it := world.item(k))
                     and not it.tool and not it.carry_bonus and not it.food and not ART.is_artifact(k) and not kept(k)),
                    key=lambda k: (-a.inventory[k], k))
    order += sorted(k for k, n in a.inventory.items() if n > 1 and world.item(k) and (world.item(k).tool or kept(k)))
    dropped = []
    for k in order:
        keep = 1 if world.item(k) and (world.item(k).tool or kept(k)) else 0
        while a.free_space() < need and a.inventory.get(k, 0) > keep:
            a.remove(k, 1)
            world.put_ground(a.x, a.y, k, 1)
            dropped.append(k)
    if dropped:
        a.remember(world.tick, f"I dropped {len(dropped)} {world.item_name(dropped[0])} to make room for food", 2, "event")


WEAR_PLAIN, WEAR_METAL = 60, 140  # uses before a tool of stone or wood breaks, and one of metal


def tool_wear_limit(tool: str, world=None) -> int:
    """How many uses a tool lasts. With `world`, an invented tool lasts as long as what it is made of (without it, as
    before, every invention counted as metal: a net of fiber and wood outlasted two stone axes)."""
    if world is not None and world.catalog.items and world.invention(tool) is not None:
        return WEAR_METAL if metal_of(world, tool) else WEAR_PLAIN
    return WEAR_PLAIN if tool.startswith("stone") or tool == "spear" else WEAR_METAL


# a metal tool's metal: what mending keeps and smelting gives back (issue #5: worn tools only ever vanished, and in long
# runs the iron went into replacement axes and picks instead of steel)
METAL_OF: Dict[str, str] = {k: m for k, r in RECIPES.items() if "metal" in (ITEMS[k].props if k in ITEMS else ())
                            and (ITEMS[k].tool or "tool" in ITEMS[k].props)  # (the plough too, Codex #18)
                            for m, _ in r.inputs if m in ("copper", "iron", "steel", "alloy")}
MEND_AT, SMELT_AT = "workshop", "furnace"


def _wear(world, a: Agent, tool: str) -> None:
    a.tool_wear[tool] = a.tool_wear.get(tool, 0) + 1
    limit = tool_wear_limit(tool, world)
    if a.tool_wear[tool] >= limit:
        a.tool_wear[tool] = 0
        a.remove(tool, 1)
        a.remember(world.tick, f"My {world.item_name(tool)} broke", 3, "tool")
        world.emit("tool_broke", f"{a.name}'s {world.item_name(tool)} broke", 1, a.id, a.x, a.y)


FORAGE_RADIUS = 12


def _forage(world, a: Agent, s) -> str:
    """Nothing to eat in hand or in a store nearby: fetch food lying close by, or pick berries, and then eat.
    Models plan "eat" with empty hands; in World A that failed 41 times a day while chits starved beside berries."""
    sub = s.get("forage")
    if sub is None:
        pile = next(((px, py, k) for px, py, p in world.piles_near(a.x, a.y, FORAGE_RADIUS)
                     for k in foods_of(world) if p.get(k, 0) > 0 and world.same_land_xy(a, px, py)
                     and a.reflex_rest.get(f"unreach:{px},{py}", 0) <= world.tick), None)
        if pile:
            sub = {"do": "pickup", "what": pile[2]}
        elif world.nearest_resource(a.x, a.y, "berries", FORAGE_RADIUS):
            sub = {"do": "gather", "what": "berries", "qty": 3}
        else:
            return "I have no food and none is stored or growing nearby"
        s["forage"], s["forage_s"] = sub, {}
        a.activity = "looking for food"
        if a.free_space() < 1:  # "eat: my hands are full" 31 times: make room for what it's about to fetch
            _drop_for_room(world, a, 1)
    fn = _do_pickup if sub["do"] == "pickup" else _do_gather
    res = fn(world, a, sub, s["forage_s"])
    if res == DONE:
        s.pop("forage")
        return RUNNING if food_items(a) else "I found no food I could carry"
    return res


def _do_eat(world, a: Agent, step, s) -> str:
    want = world.norm_item(step.get("what")) if step.get("what") else None
    foods = food_items(a)
    if want and want in foods:
        pick = want
    elif foods:
        pick = foods[0] if a.hunger < 50 else foods[-1]
        # don't waste a feast when merely peckish
        for f in reversed(foods):
            if world.item(f).food <= 100 - a.hunger + 10:
                pick = f
                break
    else:
        st = _stockpile_with(world, a, foods_of(world), 30)
        if not st:
            return _forage(world, a, s)
        mv = _goto_structure(world, a, s, st)
        if mv == "moving" and _long_way(a, s, st.x, st.y):
            mv = "blocked"  # a store a long way round: forage closer instead
        if mv == "blocked":
            # 11 of 12 starvation deaths on one map were chits failing to reach the same pile over and over
            a.reflex_rest["unreach:" + st.id] = world.tick + TICKS_PER_DAY
            s.clear()
            return _forage(world, a, s)
        if mv != "arrived":
            return RUNNING
        a.activity = "taking food"
        took = 0
        for f in foods_of(world):
            if st.storage.get(f, 0) > 0:
                if a.free_space() < world.item(f).weight:
                    _drop_for_room(world, a, world.item(f).weight)
                took = a.add(f, min(st.storage[f], 3))
                st.storage[f] -= took
                if st.storage[f] <= 0:
                    st.storage.pop(f)
                world.dirty_struct.add(st.id)
                break
        s["tries"] = s.get("tries", 0) + 1
        if not took and s["tries"] > 2:
            return "couldn't take food from the stockpile"
        return RUNNING
    a.activity = "eating"
    if not _work(a, 1.0, 3.0):
        return RUNNING
    a.remove(pick, 1)
    a.hunger = min(100.0, a.hunger + world.item(pick).food)
    a.bump("meals")
    if pick in ("bread", "berry_tart", "cooked_fish"):
        a.mood = min(100.0, a.mood + 4)
    if a.hunger < 70 and food_items(a) and s.get("ate", 0) < 4:
        s["ate"] = s.get("ate", 0) + 1
        return RUNNING
    s["note"] = f"Ate {world.item_name(pick)}; hunger now {a.hunger:.0f}/100"
    return DONE


def _home_for(world, a: Agent):
    h = world.structures.get(a.home or "")
    if h and h.functional:
        return h
    nearest = None
    for st in world.structures_near(a.x, a.y, 30):
        if st.functional and st.design in BLD.HOMES:
            nearest = nearest or st
            cap = BLD.HOME_CAP[st.design]
            residents = sum(1 for o in world.agents.values() if o.home == st.id)
            if residents < cap:
                a.home = st.id
                a.bump_rev("it found a home")
                a.remember(world.tick, f"I made the {DESIGNS[st.design].name} at ({st.x},{st.y}) my home", 3, "home")
                return st
    # every home is full: an exhausted chit still crashes in the nearest one for the night
    return nearest if a.energy < 15 else None


def kept_up(world, st, amount: float) -> None:
    """Things in use are looked after as they're used: a hut slept in, a farm worked, a kiln fired. World A spent its
    days on 763 ruins and 645 repairs; upkeep was the chore that crowded out everything else."""
    if st is not None and st.complete and 0 < st.durability < 100:
        st.durability = min(100.0, st.durability + amount)
        if world.tick % 20 == 0:
            world.dirty_struct.add(st.id)


def _do_sleep(world, a: Agent, step, s) -> str:
    if not s.get("settled"):
        home = world.structures.get(s.get("home") or "")
        if home is None or not home.functional:
            home = _home_for(world, a)
            s["home"] = home.id if home else None
            camp = next((c for c in world.structures_near(a.x, a.y, CAMP_SLEEP, "outpost") if c.functional), None)
            if camp is not None and (home is None or home.dist(a.x, a.y) > CAMP_FAR):
                home = camp  # far from home on a long trip: the camp's tent is nearer
                s["home"] = camp.id
        s["walked"] = s.get("walked", 0) + 1
        # an exhausted chit sleeps where it drops: walking home burns energy, and chits whose home was far
        # (or round a river) walked at zero energy until exhaustion killed them
        spent = a.energy < 5 and home is not None and home.dist(a.x, a.y) > 10
        if home and not spent and s["walked"] <= 120:
            goals = {c for c in home.cells() if world.passable(*c)}
            mv = move_toward(world, a, s, goals)
            if mv == "moving":
                return RUNNING
        else:
            fire = next((st for st in world.structures_near(a.x, a.y, 15) if st.lit), None)
            if fire and fire.dist(a.x, a.y) > 2:
                mv = _goto_structure(world, a, s, fire)
                if mv == "moving":
                    return RUNNING
        s["settled"] = True
    a.activity = "sleeping"
    a.emote = "💤"
    a.emote_until = world.tick + 2
    s["slept"] = s.get("slept", 0) + 1
    kept_up(world, world.in_home(a), 0.05)  # about +10 a night
    if a.hunger < 12:
        s["note"] = "Woke up hungry"
        return DONE
    if a.energy >= 99 or (not world.is_night and a.energy >= 75) or s["slept"] > 220:
        a.emote = ""
        s["note"] = f"Slept {'at home' if world.in_home(a) else 'outside'}; energy {a.energy:.0f}/100"
        return DONE
    return RUNNING


def _do_warm_up(world, a: Agent, step, s) -> str:
    tgt = s.get("tgt")
    st = world.structures.get(tgt) if tgt else None
    if st is None:
        near = world.structures_near(a.x, a.y, 30)
        # a fire must still be burning when the chit gets there (it burns ~0.14 a tick at night; a chit walks
        # ~0.5 tiles a tick): chits walked to fires that went out first and froze on the way
        warm = [x for x in near if (x.lit and getattr(x, "fuel", 100) > 0.14 * 2.5 * x.dist(a.x, a.y) + 5)
                or (x.functional and x.design in ("kiln", "furnace") + BLD.WARM_HOMES)]
        cands = warm or [x for x in near if x.lit or (x.functional and x.design in BLD.HOMES and x.id == a.home)]
        if not cands:
            h = _home_for(world, a)
            if h:
                cands = [h]
        if not cands:
            return "there is nowhere warm nearby — a campfire or hut would help"
        st = cands[0]
        s["tgt"] = st.id
    if st.design in BLD.HOMES:
        mv = move_toward(world, a, s, {c for c in st.cells() if world.passable(*c)})
    else:
        mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach somewhere warm"
    if mv != "arrived":
        return RUNNING
    a.activity = "warming up"
    if a.warmth >= 75 or world.temperature() >= 0.42:
        s["note"] = "Warmed up"
        return DONE
    if st.design == "campfire" and not st.lit:
        s.pop("tgt", None)
    return RUNNING


STATION_REACH = 45  # how far a chit goes to reach the station a craft needs (planners check the same reach)
# ...and how far instinct goes by choice, with no particular need: to tinker at a random station, bake, work a
# spare shift. Blind experiments at stations up to 45 tiles away cost the 60-day A/B 4.5 discoveries and 23% of
# goods made, all in walking (audit F5).
STATION_NEAR = 20
FAILED_MEMORY = 150  # failed experiments a chit keeps: at 30, a curious chit forgot and retried old ones within a season


def _gather_station(world, a: Agent, s, station: str) -> str:
    if station in world.stations_at(a.x, a.y):
        return "arrived"
    st = world.nearest_station(a.x, a.y, station, STATION_REACH)
    if not st:
        return "none"
    mv = _goto_structure(world, a, s, st)
    return mv


def _observers_learn(world, a: Agent, knowledge: str) -> None:
    for o in world.agents_near(a.x, a.y, 3, exclude=a.id):
        if knowledge in o.knows or o.activity == "sleeping":
            continue
        if world.rng_for("agents").random() < 0.12 + 0.25 * o.traits.get("curiosity", 0.5):
            world.learned(o, knowledge, "observed", a)


def _do_craft(world, a: Agent, step, s) -> str:
    key = world.norm_item(step.get("what"))
    if not key or world.recipe(key) is None:
        design = normalize_design(step.get("what"))
        if design:  # a common slip: a structure is built where it stands; build it
            return _do_build(world, a, dict(step, do="build", what=design), s)
        return f"'{step.get('what')}' is not something that can be crafted"
    r = world.recipe(key)
    if not a.knows_recipe(key):
        return f"I don't know how to make {world.item_name(key)} yet (experiment, inspect, or learn it)"
    want = s.setdefault("want", _qty(step, 1, 1, 10))
    made = s.setdefault("made", 0)
    if made >= want:
        s["note"] = f"Made {made} {world.item_name(key)}"
        return DONE
    missing = {k: n - a.inventory.get(k, 0) for k, n in r.inputs if a.inventory.get(k, 0) < n}
    if missing:
        st = _stockpile_with(world, a, list(missing), 25)
        if st:
            mv = _goto_structure(world, a, s, st)
            if mv == "blocked":
                return "couldn't reach the stockpile"
            if mv != "arrived":
                return RUNNING
            fetched = 0
            for k, n in missing.items():
                got = a.add(k, min(n, st.storage.get(k, 0)))
                if got:
                    st.storage[k] -= got
                    if st.storage[k] <= 0:
                        st.storage.pop(k)
                    fetched += got
            if not fetched:
                return "my hands are full"
            world.dirty_struct.add(st.id)
            world.notice_items(a)
            return RUNNING
        if made:
            s["note"] = f"Made {made} {world.item_name(key)}; ran out of materials"
            return DONE
        need = ", ".join(f"{n} {world.item_name(k)}" for k, n in missing.items())
        return f"missing {need}"
    if r.station:
        mv = _gather_station(world, a, s, r.station)
        if mv == "none":
            return f"it needs a {r.station} and there is none nearby"
        if mv == "blocked":
            return f"couldn't reach the {r.station}"
        if mv != "arrived":
            return RUNNING
    a.activity = f"crafting {world.item_name(key)}"
    if not _work(a, a.skill_speed("crafting") * BLD.craft_speed(world, a, key), float(r.work)):
        return RUNNING
    _make_one(world, a, r)
    s["made"] = made + 1
    a.bump("crafted")
    first_time = a.stats.get(f"made_{key}", 0) == 0
    a.bump(f"made_{key}")
    if first_time:
        world.emit("crafted", f"{a.name} made a {world.item_name(key)}", 1, a.id, a.x, a.y, item=key)
    _observers_learn(world, a, f"recipe:{key}")
    return RUNNING


def _make_one(world, a: Agent, r) -> int:
    """One batch of recipe r from what the chit carries; returns how many it made (a bakery's oven makes two for one).
    What doesn't fit in hand is still made: it's held, over the limit (nothing vanishes silently)."""
    for k, n in r.inputs:
        a.remove(k, n)
    qty = r.qty * BLD.bake_mult(world, a, r.key)  # (a bakery's oven: two for one)
    got = a.add(r.key, qty)
    if got < qty:
        a.inventory[r.key] = a.inventory.get(r.key, 0) + (qty - got)
    a.made_it_work(f"recipe:{r.key}", world.tick)
    a.practice("crafting", 1.0)
    world.notice_items(a)
    return qty


# ---------------------------------------------------------------------------- production: bills at stations
# A kiln, furnace or workshop used to be only a place where experiments could happen: nothing was ever produced
# there, and stores piled up (hundreds of clay, 27 ore and 23 charcoal). Working a shift runs one "bill": a recipe
# the worker knows for that station, fed from the stockpiles around it, with the goods put back into them.
WORK_SHIFT = 60  # ticks of work at the station in one shift
WORK_RADIUS = 20  # a station draws on (and fills) the stockpiles this close to it
WORK_REACH = STATION_REACH  # how far a chit goes to reach a station it was asked to work at (one reach, F5)
# raw materials a shift never takes the stores below: builders and experimenters need them too (without it pots and
# tablets emptied the stores of clay by day 25, where 30 or more lay in them without shifts)
SEED_PLENTY = 60  # seeds the stores near a picker hold before it stops keeping the pips from berries


def seeds_plenty(world, x: int, y: int) -> bool:
    """The stores here hold all the seed anyone will sow. Berry pips were the only seeds that never got used up:
    one live world held 20,311 seeds by day 2,900, 62% of everything in its stores (issue #7)."""
    return sum(p.storage.get("seeds", 0) for p in village_stores(world, x, y, 30)) >= SEED_PLENTY


KEEP_STOCK = {"wood": 10, "stone": 8, "fiber": 6, "clay": 12, "sand": 6, "ore": 4, "iron_ore": 4}
REPORT_EVERY = TICKS_PER_DAY // 2  # a station reports its work to the chronicle at most this often
STATION_WORDS = {"campfire": "fire", "camp fire": "fire", "bonfire": "fire", "hearth": "fire", "fireplace": "fire",
                 "oven": "kiln", "smelter": "furnace", "bench": "workshop", "workbench": "workshop", "millstone": "mill", "windmill": "mill",
                 "works": "factory"}
WORK_EMOTE = {"fire": "🍳", "kiln": "🔥", "furnace": "🔥", "workshop": "🔨", "forge": "⚒", "factory": "⚙", "mill": "🌾"}
COUNTABLE = {"brick", "pot", "basket", "clay_tablet", "sharp_stone", "berry_tart", "spear", "stone_axe", "stone_pick",
             "copper_axe", "copper_pick", "iron_axe", "iron_pick", "lantern", "cloak", "wheel", "cart", "gear", "engine", "loaf",
             "magnet", "dynamo", "lightbulb", "rocket_part"}


def _retarget(a: Agent, s) -> None:
    """Walking somewhere else next: forget the old path."""
    s.pop("goal_sig", None)
    s["repath"] = 0
    a.path = []


def _count_words(world, key: str, n: int) -> str:
    name = world.item_name(key)
    return f"{n} {name}{'s' if n != 1 and key in COUNTABLE else ''}"


def _plenty(world, key: str) -> int:
    """How many of an item the stores around a station should hold before a shift makes something else."""
    it = world.item(key)
    if it is not None and (it.tool or it.carry_bonus):
        return 3
    return 30 if it is not None and it.food else 24


def _useful(world, key: str) -> bool:
    """Worth making in bulk: food, a tool or container, or something that goes into a thing someone here has known
    how to make or build (charcoal once copper or iron is known: before that a shift just burns the wood; wheels
    once someone knows the cart)."""
    it = world.item(key)
    if it is None:
        return False
    if it.food or it.tool or it.carry_bonus or key in ACTION_USES:
        return True
    for k in world.first:
        kind, _, x = k.partition(":")
        if kind == "recipe" and (r := world.recipe(x)) is not None and any(i == key for i, _ in r.inputs):
            return True
        if kind == "design" and x in DESIGNS and key in DESIGNS[x].material_map:
            return True
    return False


def village_stores(world, x: int, y: int, radius: int, a: Optional[Agent] = None) -> List:
    """The village's working stores within `radius` (HOME_STORES: stockpiles and warehouses, not a far camp's), and
    for a chit only those it can walk to. The one definition of usable nearby storage (audit F10): hand-written store
    tuples had left warehouses out of project stock, research, spoilage and the "why not" panel."""
    return [p for p in world.structures_near(x, y, radius) if p.design in HOME_STORES and p.functional
            and (a is None or (world.same_land(a, p) and a.reflex_rest.get("unreach:" + p.id, 0) <= world.tick))]


def _station_piles(world, a: Agent, st) -> List:
    """The working stores around a station that this chit can walk to."""
    return village_stores(world, st.x, st.y, WORK_RADIUS, a)


def _bills(world, a: Agent, kinds: Set[str]) -> List:
    """The recipes this chit knows that can be made at these stations (the workshop also does bench work that needs
    no station: stone tools, baskets)."""
    out = []
    for k in sorted(a.knows):
        if not k.startswith("recipe:"):
            continue
        r = world.recipe(k.split(":", 1)[1])
        if r is not None and (r.station in kinds or (r.station is None and "workshop" in kinds)):
            out.append(r)
    return out


def _spare_load(world, a: Agent, keep) -> int:
    """The weight this chit could put down in a store (not its tools and containers, a bite of food, or `keep`)."""
    w = 0
    for k, n in a.inventory.items():
        it = world.item(k)
        if it is None or it.tool or it.carry_bonus or k in keep:
            continue
        w += it.weight * max(0, n - kept_in_hand(world, k))
    return w


def keep_stock(world) -> Dict[str, int]:
    """What a shift never takes the stores below: the raw materials others need (KEEP_STOCK), and, while the next
    era's key recipe is still undiscovered, its direct inputs (the steam engine's 2 steel, 2 gears and a pot). Gear
    shifts turned every steel in the stores into gears, so the engine's own steel was never there to try it with
    (audit F11)."""
    from .world import ERAS

    keep = dict(KEEP_STOCK)
    i = world.era()[0]
    if i + 1 < len(ERAS):
        kind, key = ERAS[i + 1][1].split(":", 1)
        r = world.recipe(key) if kind == "recipe" else None
        if r is not None:
            for k, q in r.inputs:
                keep[k] = max(keep.get(k, 0), q)
    return keep


def _batches(world, a: Agent, r, stock: Dict[str, int], keep: Optional[Dict[str, int]] = None) -> int:
    """How many batches of r one shift can make from the chit's hands and the stores, and still carry the inputs."""
    speed = a.skill_speed("crafting") * (1.1 if a.mood > 70 else 1.0)
    n = max(1, int(WORK_SHIFT * speed // max(1, r.work)))
    keep = keep_stock(world) if keep is None else keep
    for k, q in r.inputs:
        n = min(n, (a.inventory.get(k, 0) + max(0, stock.get(k, 0) - keep.get(k, 0))) // q)
    room = a.free_space() + _spare_load(world, a, {k for k, _ in r.inputs})

    def fetch(m: int) -> int:
        return sum(max(0, m * q - a.inventory.get(k, 0)) * (world.item(k).weight if world.item(k) else 1) for k, q in r.inputs)

    while n > 0 and fetch(n) > room:
        n -= 1
    return max(0, n)


PATH_WEIGHT = 3.0  # a bill for something on the way to the next era counts this much more


def era_path(world) -> Dict[str, int]:
    """What stands between this world and its next era (T22): the next era's key thing, what that is made from all
    the way down, and what a station it needs is built from while there is none. item -> steps from the key.
    World B sat in the Iron Age with a furnace, and ore and charcoal in its stores, because nobody made iron."""
    from .world import ERAS

    i = world.era()[0]
    if i + 1 >= len(ERAS):
        return {}
    kind, key = ERAS[i + 1][1].split(":", 1)
    have: Set[str] = set()
    for st in world.structures.values():
        have |= st.stations()
    depth: Dict[str, int] = {}
    todo = [(key, 0)] if kind == "recipe" else [(m, 1) for m, _ in DESIGNS[key].materials]
    while todo:
        k, d = todo.pop(0)
        if k in depth:
            continue
        depth[k] = d
        r = world.recipe(k)
        if r is None:
            continue
        todo += [(m, d + 1) for m, _ in r.inputs]
        if r.station and r.station not in have:  # no forge yet: the forge's bricks and iron are on the way too
            des = DESIGNS.get(r.station) or next((x for x in DESIGNS.values() if x.station == r.station), None)
            todo += [(m, d + 1) for m, _ in des.materials] if des is not None else []
    return depth


class Bill:
    """A shift someone could work now: at station `st` (as a `kind` station), `n` batches of recipe `r`. `lack` is how
    short the stores around the station are of its output (0 = plenty, 1 = none at all); `path` says its output is
    on the way to the world's next era."""

    def __init__(self, st, kind: str, r, n: int, lack: float, path: bool = False):
        self.st, self.kind, self.r, self.n, self.lack, self.path = st, kind, r, n, lack, path


def plan_bill(world, a: Agent, kinds: Optional[Set[str]] = None, target=None, prefer: Optional[str] = None,
              radius: int = WORK_REACH) -> Tuple[Optional[Bill], str]:
    """The shift this chit would work, and where. Asked for a kind of station, the nearest one it can walk to that
    has a bill it can run; asked for any, the best bill at any of them (nearest first on a tie). The best bill is
    the one whose output the stores hold least of against what its inputs could make, three times over when it is
    on the way to the next era (iron before there is a forge, then steel and gears). Returns (bill, "") or
    (None, why not)."""
    cands, across = [], False
    for st in world.structures_near(a.x, a.y, radius):
        ks = st.stations() & kinds if kinds else st.stations()
        if not ks:
            continue
        if a.reflex_rest.get("unreach:" + st.id, 0) > world.tick or not world.same_land(a, st):
            across = True
            continue
        cands.append((st, ks))
    if target is not None:
        tk = target.stations() & kinds if kinds else target.stations()
        cands = [c for c in cands if c[0] is not target]
        if tk and world.same_land(a, target):
            cands.insert(0, (target, tk))
    what = "/".join(sorted(kinds)) if kinds else "station"
    if not cands:
        return None, (f"the only {what} nearby is somewhere I can't walk to" if across else
                      f"there's no working {what} nearby" + (" (a campfire must be lit)" if kinds and "fire" in kinds else ""))
    known = False
    short: List[str] = []
    plenty: List[str] = []
    unneeded: List[str] = []
    full: List[str] = []
    path = era_path(world)
    best = None
    for st, ks in cands:
        bills = _bills(world, a, ks)
        if not bills:
            continue
        known = True
        piles = _station_piles(world, a, st)
        stock: Dict[str, int] = {}
        for p in piles:
            for k, n in p.storage.items():
                stock[k] = stock.get(k, 0) + n
        for r in bills:
            n = _batches(world, a, r, stock)
            if n < 1:
                short.append(f"{world.item_name(r.key)} needs " + " + ".join(
                    f"{q} {world.item_name(k)}" if q > 1 else world.item_name(k) for k, q in r.inputs))
                continue
            # the goods need somewhere to go: kiln shifts into full stores left chits holding 22 charcoal, and some
            # starved beside the grain with no hand free to take it
            n = min(n, sum(stockpile_room(p, r.key, world.catalog) for p in piles) // r.qty)
            if n < 1:
                full.append(world.item_name(r.key))
                continue
            have = stock.get(r.key, 0)
            on = r.key in path
            if r.key == prefer:
                return Bill(st, r.station or "workshop", r, n, max(0.0, 1 - have / _plenty(world, r.key)), on), ""
            if have >= _plenty(world, r.key):
                plenty.append(world.item_name(r.key))
                continue
            if not on and not _useful(world, r.key):  # (what's on the way to the next era is always needed)
                unneeded.append(world.item_name(r.key))
                continue
            # what the inputs in store could make, against what is stored already
            can = min((a.inventory.get(k, 0) + stock.get(k, 0)) // q for k, q in r.inputs) * r.qty
            score = can / (can + have) * (PATH_WEIGHT if on else 1.0)
            n = min(n, -(-(_plenty(world, r.key) - have) // r.qty))
            if best is None or score > best[0]:
                best = (score, Bill(st, r.station or "workshop", r, n, 1 - have / _plenty(world, r.key), on))
        if best is not None and kinds:
            return best[1], ""  # asked for a kind of station: the nearest one that has work
    if best is not None:
        return best[1], ""
    if not known:
        return None, f"I don't know how to make anything at a {what} yet (experiment there, or learn it from someone)"
    why = ([f"the stores already hold plenty of {', '.join(dict.fromkeys(plenty))}"] if plenty else []) + \
        ([f"the stores have no room for {', '.join(dict.fromkeys(full))}"] if full else []) + \
        [f"{x} (not in the stores nearby)" for x in dict.fromkeys(short)] + \
        ([f"{', '.join(dict.fromkeys(unneeded))} goes into nothing anyone here knows how to make or build"] if unneeded else [])
    return None, f"nothing to do at the {what}: " + "; ".join(why)


def _station_word(text: str) -> Tuple[Optional[str], Optional[str]]:
    """'kiln' / 'the workbench' / 'campfire' -> ("kiln"|"workshop"|"fire", None); a structure that is no station
    ('farm') -> (None, "farm plot"); anything else -> (None, None)."""
    low = text.lower().replace("_", " ").strip()
    for p in ("the ", "a ", "an "):
        if low.startswith(p):
            low = low[len(p):]
    kind = STATION_WORDS.get(low) or (low if low in STATIONS else None)
    if kind:
        return kind, None
    d = normalize_design(low)
    if d:
        return DESIGNS[d].station, (None if DESIGNS[d].station else DESIGNS[d].name)
    return None, None


def _work_place(world, step) -> Tuple[Optional[Set[str]], Any, Optional[str], str]:
    """What a work step asks for: station kinds (None = any), one particular structure, a preferred product."""
    kinds: Optional[Set[str]] = None
    target, prefer = None, None
    for raw in (step.get("target"), step.get("at"), step.get("what"), step.get("site")):
        if raw is None or isinstance(raw, (list, dict)) or not str(raw).strip():
            continue
        r = str(raw).strip()
        if r in world.structures:
            target = target or world.structures[r]
            continue
        kind, other = _station_word(r)
        item = world.norm_item(r) if not kind and not other else None
        if not kind and not other and not (item and world.recipe(item)):
            # "kiln making bricks" (a plan written as a sentence): look at the words one by one
            for w in r.replace(",", " ").split():
                kind = kind or _station_word(w)[0]
                it = world.norm_item(w)
                item = item or (it if it and world.recipe(it) else None)
        if kind:
            kinds = kinds or {kind}
        if item and world.recipe(item) is not None:
            prefer = prefer or item
        if kind or (item and world.recipe(item) is not None):
            continue
        if other:
            return None, None, None, (f"a {other} isn't a place to work a shift: that's a fire, kiln, furnace, "
                                      f"workshop, forge or factory")
        return None, None, None, f"'{r}' isn't a place to work: try a fire, kiln, furnace or workshop"
    if target is not None and not target.stations():
        nm = DESIGNS[target.design].name
        return None, None, None, (f"the {nm} isn't working (unfinished, in ruins or gone cold)" if DESIGNS[target.design].station
                                  else f"a {nm} isn't a place to work a shift")
    if prefer and not kinds and target is None:
        kinds = {world.recipe(prefer).station or "workshop"}
    return kinds, target, prefer, ""


def _report_work(world, a: Agent, st, r, n: int) -> None:
    """One chronicle line per shift, at most every half day per station, and a louder one the first time a station
    makes something."""
    first = st.produced.get(r.key, 0) == n
    if not first:
        for e in reversed(world.events):
            if world.tick - e.tick >= REPORT_EVERY:
                break
            if e.kind == "produced" and e.data.get("structure") == st.id:
                return
    it = world.item(r.key)
    props = set(it.props) if it else set()
    kind = r.station or "workshop"
    verb = ("baked" if "baked" in props else "cooked") if kind == "fire" else "fired" if kind == "kiln" and "fired" in props \
        else "smelted" if kind == "furnace" and "metal" in props else "forged" if kind == "forge" else "made"
    world.emit("produced", f"{a.name} {verb} {_count_words(world, r.key, n)} at the {DESIGNS[st.design].name}",
               2 if first else 1, a.id, *st.center(), structure=st.id, item=r.key, n=n, first=first)


def _do_work(world, a: Agent, step, s) -> str:
    """Work a shift at a station: fetch a bill's inputs from the stores around it, make the goods, store them."""
    if "bill" not in s:
        kinds, target, prefer, why = _work_place(world, step)
        if why:
            return why
        bill, why = plan_bill(world, a, kinds, target, prefer)
        if bill is None:
            return why
        s.update(st=bill.st.id, bill=bill.r.key, n=bill.n, made=0, took={}, tried=[], phase="fetch", worked=0)
        if prefer and prefer != bill.r.key:
            s["swap"] = f" ({world.item_name(prefer)} couldn't be made there)"
        _retarget(a, s)
    st = world.structures.get(s["st"])
    r = world.recipe(s["bill"])
    sname = DESIGNS[st.design].name if st is not None else "station"
    if r is None:
        return f"nobody here knows how to make {s['bill']} any more"
    if s["phase"] != "deliver" and (st is None or not st.functional):
        if not s["made"] and not s["took"]:
            return f"the {sname} is gone"
        s["phase"] = "deliver"
    if s["phase"] == "fetch":
        need = {k: q * s["n"] - a.inventory.get(k, 0) for k, q in r.inputs if a.inventory.get(k, 0) < q * s["n"]}
        if need and s.get("pile") is None:
            piles = [p for p in _station_piles(world, a, st) if p.id not in s["tried"] and any(p.storage.get(k, 0) for k in need)]
            if piles and len(s["tried"]) < 4:
                s["pile"] = min(piles, key=lambda p: p.dist(a.x, a.y)).id
                _retarget(a, s)
            else:  # someone else took them first: make what the inputs in hand allow
                s["n"] = min(a.inventory.get(k, 0) // q for k, q in r.inputs)
                need = {}
                if s["n"] < 1:
                    s["why"] = f"the stores near the {sname} ran out before I could fetch {world.catalog.describe(r)}"
                    s["phase"] = "deliver"
                    return RUNNING
        if need:
            pile = world.structures.get(s["pile"])
            mv = _goto_structure(world, a, s, pile) if pile is not None and pile.functional else "blocked"
            if mv == "moving":
                return RUNNING
            if mv == "blocked":
                if pile is not None:
                    a.reflex_rest["unreach:" + pile.id] = world.tick + TICKS_PER_DAY
            else:
                a.activity = f"fetching for the {sname}"
                w_need = sum(n * (world.item(k).weight if world.item(k) else 1) for k, n in need.items() if pile.storage.get(k, 0))
                if a.free_space() < w_need:
                    _do_store(world, a, {"do": "store", "what": "all", "target": pile.id}, {})  # put the load down first
                    need = {k: q * s["n"] - a.inventory.get(k, 0) for k, q in r.inputs if a.inventory.get(k, 0) < q * s["n"]}
                for k, n in need.items():
                    if pile.storage.get(k, 0) <= 0:
                        continue
                    before = a.inventory.get(k, 0)
                    _do_take(world, a, {"do": "take", "what": k, "qty": n, "target": pile.id}, {})
                    s["took"][k] = s["took"].get(k, 0) + a.inventory.get(k, 0) - before
            s["tried"].append(s.pop("pile"))
            _retarget(a, s)
            return RUNNING
        s["phase"] = "work"
        _retarget(a, s)
    if s["phase"] == "work":
        mv = _goto_structure(world, a, s, st)
        if mv == "blocked":
            a.reflex_rest["unreach:" + st.id] = world.tick + TICKS_PER_DAY
            s["why"] = f"couldn't reach the {sname}"
            s["phase"] = "deliver"
            _retarget(a, s)
            return RUNNING
        if mv != "arrived":
            return RUNNING
        speed = a.skill_speed("crafting") * (1.1 if a.mood > 70 else 1.0) * BLD.craft_speed(world, a, r.key)
        if s["worked"] == 0:
            st.worked_until = world.tick + int((s["n"] - s["made"]) * r.work / speed) + 2
            world.dirty_struct.add(st.id)
        s["worked"] += 1
        a.activity = f"working at the {sname}"
        a.emote = WORK_EMOTE.get(r.station or "workshop", "🔨")
        a.emote_until = world.tick + 2
        done = s["worked"] >= WORK_SHIFT * 2  # interrupted too often: call it a shift
        if _work(a, speed, float(r.work)):
            if all(a.inventory.get(k, 0) >= q for k, q in r.inputs):
                q = _make_one(world, a, r)
                kept_up(world, st, 5)  # a station in use is looked after as it's used
                # goods (a bakery's batch is two for one, Codex #33); a shift saved before they were counted made as
                # many in each batch so far
                s["out"] = s.get("out", s["made"] * q) + q
                s["made"] += 1  # (batches, against the bill's n)
                st.produced[r.key] = st.produced.get(r.key, 0) + q
                a.bump("produced", q)
                a.bump(f"produced_{r.key}", q)
                _observers_learn(world, a, f"recipe:{r.key}")
            done = done or s["made"] >= s["n"] or not all(a.inventory.get(k, 0) >= q for k, q in r.inputs)
        if not done:
            return RUNNING
        st.worked_until = world.tick
        world.dirty_struct.add(st.id)
        if s["made"]:
            a.bump("shifts")
            _report_work(world, a, st, r, s.get("out", s["made"] * r.qty))
        s["phase"] = "deliver"
        _retarget(a, s)
    # deliver: the goods, and any inputs left over, go into a store beside the station (or stay in hand)
    made = s.get("out", s["made"] * r.qty)
    stored = s.setdefault("stored", {})
    back = {r.key: min(a.inventory.get(r.key, 0), made)} if made else {}
    for k, n in s["took"].items():
        back[k] = min(a.inventory.get(k, 0), n)
    back = {k: n for k, n in back.items() if n > 0 and k not in stored}
    if back and s.get("dest") != "":
        if s.get("dest") is None:
            key = r.key if r.key in back else next(iter(back))
            piles = [p for p in (_station_piles(world, a, st) if st is not None else []) if stockpile_room(p, key, world.catalog) > 0]
            dest = min(piles, key=lambda p: p.dist(a.x, a.y)) if piles else _stockpile_with_room(world, a)
            s["dest"] = dest.id if dest is not None else ""
            _retarget(a, s)
        if s["dest"]:
            k = sorted(back, key=lambda k: k != r.key)[0]  # the goods first
            before = a.inventory.get(k, 0)
            res = _do_store(world, a, {"do": "store", "what": k, "qty": back[k], "target": s["dest"]}, s.setdefault("store_s", {}))
            if res == RUNNING:
                a.activity = f"carrying goods from the {sname}"
                return RUNNING
            stored[k] = before - a.inventory.get(k, 0)
            s.pop("store_s", None)
            _retarget(a, s)
            if res != DONE:
                s["dest"] = ""
            return RUNNING
    if not s["made"]:
        return s.get("why") or f"nothing got made at the {sname}"
    put = stored.get(r.key, 0)
    where = (", now in the stockpile" if put >= made else f" ({put} went into the stockpile; it was full)" if put
             else ": no stockpile nearby had room, so I kept them")
    s["note"] = f"Worked a shift at the {sname} and made {_count_words(world, r.key, made)}{where}{s.get('swap', '')}"
    return DONE


def _experiment_bag(step, world=None) -> List[str]:
    raw = step.get("with") or step.get("items") or step.get("what") or []
    if isinstance(raw, str):
        raw = [p for p in raw.replace("+", ",").replace(" and ", ",").split(",")]
    elif isinstance(raw, dict):
        raw = [raw] if "item" in raw or "what" in raw else [{"item": k, "qty": n} for k, n in raw.items()]
    if not isinstance(raw, list):
        return [None]
    norm = world.norm_item if world is not None else normalize_item
    out = []
    for x in raw:
        count, item = 1, x
        if isinstance(x, dict):
            item, count = x.get("item") or x.get("what"), x.get("qty", 1)
        elif isinstance(x, str) and x.strip()[:1].isdigit() and " " in x.strip():
            count, item = x.strip().split(" ", 1)
        try:
            n = int(count)
            if isinstance(count, bool) or float(count) != n or n <= 0 or len(out) + n > 6:
                return [None]
        except (TypeError, ValueError, OverflowError):
            return [None]
        out.extend([norm(item)] * n)
    return out


def _do_experiment(world, a: Agent, step, s) -> str:
    bag_list = _experiment_bag(step, world)
    if not bag_list:
        return "an experiment needs some items to combine"
    if any(k is None for k in bag_list):
        return "some of those aren't real items"
    bag: Dict[str, int] = {}
    for k in bag_list:
        bag[k] = bag.get(k, 0) + 1
    lacking = [k for k, n in bag.items() if a.inventory.get(k, 0) < n]
    if lacking:
        return f"I'm not carrying enough {', '.join(world.item_name(k) for k in lacking)}"
    station = str(step.get("at") or "").strip().lower() or None
    if station:
        station = {"campfire": "fire", "fire": "fire", "bench": "workshop", "workbench": "workshop"}.get(station, station)
        if station not in STATIONS:
            return f"'{station}' is not a known kind of station"
    if station:
        mv = _gather_station(world, a, s, station)
        if mv == "none":
            return f"there's no {station} nearby to experiment at"
        if mv == "blocked":
            return f"couldn't reach the {station}"
        if mv != "arrived":
            return RUNNING
    a.activity = "experimenting"
    a.emote = "🔬"
    a.emote_until = world.tick + 3
    if not _work(a, a.skill_speed("crafting"), 7.0):
        return RUNNING
    here = world.stations_at(a.x, a.y)
    tries = ([station] if station else []) + sorted(here) + [None]
    recipe = None
    for st in tries:
        if st is not None and st not in here:
            continue
        recipe = world.catalog.match(bag, st)
        if recipe:
            break
    combo = " + ".join(f"{n} {world.item_name(k)}" if n > 1 else world.item_name(k) for k, n in sorted(bag.items()))
    where = f" at the {station}" if station else ""
    a.bump("experiments")
    a.practice("crafting", 0.6)
    if recipe:
        for k, n in recipe.inputs:
            a.remove(k, n)
        got = a.add(recipe.key, recipe.qty)
        if got < recipe.qty:  # what didn't fit is still made: it's in hand, over the limit
            a.inventory[recipe.key] = a.inventory.get(recipe.key, 0) + (recipe.qty - got)
        world.notice_items(a)
        kk = f"recipe:{recipe.key}"
        nm = sanitize_name(step.get("name"))
        if nm and kk not in world.first and kk not in world.culture_names:
            world.culture_names[kk] = nm  # the first discoverer names it for their world
        if world.learned(a, kk, "discovered"):
            s["note"] = f"Experiment worked! {combo}{where} made {world.item_name(recipe.key)}"
        else:
            a.made_it_work(kk, world.tick)
            s["note"] = f"Made {world.item_name(recipe.key)} from {combo}"
        _observers_learn(world, a, f"recipe:{recipe.key}")
        return DONE
    hint = _experiment_hint(bag, here | ({station} if station else set()), world.catalog.physics())
    key = f"{combo}{where}"
    if key not in a.failed_experiments:
        a.failed_experiments.append(key)
        a.failed_experiments[:] = a.failed_experiments[-FAILED_MEMORY:]
    lost = ""
    cheap = [k for k in bag if not world.item(k).tool]
    if cheap and world.rng_for("agents").random() < 0.25:
        k = world.rng_for("agents").choice(cheap)
        a.remove(k, 1)
        lost = f" and a {world.item_name(k)} was ruined"
    s["note"] = f"Tried {combo}{where}: nothing useful happened{lost}. {hint}".strip()
    a.remember(world.tick, s["note"], 2, "experiment")
    return DONE


def _do_invent(world, a: Agent, step, s) -> str:
    """Imagine something new from 2-4 carried items (T20). The world judges it by the items' properties."""
    from .invent import invention_props, register_invention, verdict

    bag_list = _experiment_bag(step, world)
    if not bag_list:
        return "an invention needs some items to put together"
    if any(k is None for k in bag_list):
        return "some of those aren't real items"
    bag: Dict[str, int] = {}
    for k in bag_list:
        bag[k] = bag.get(k, 0) + 1
    lacking = [k for k, n in bag.items() if a.inventory.get(k, 0) < n]
    if lacking:
        return f"I'm not carrying enough {', '.join(world.item_name(k) for k in lacking)}"
    name = sanitize_name(step.get("name"))
    if not name:
        return "an invention needs a name (\"name\": what you call it)"
    taken = (normalize_item(name) or normalize_design(name) or world.invention_by_name(name)
             or world.catalog.pack_key(name))
    if taken:  # otherwise "wood" or "spear" would mean the invention for everyone here from now on
        return f"the name {name} is already taken by {world.item_name(taken) if normalize_item(name) or world.invention_by_name(name) or world.catalog.pack_key(name) else DESIGNS[taken].name}: give it a new name"
    purpose_text = str(step.get("purpose") or "").strip()
    # "at" (optional, F34): made at a station the same parts can make more (a metal blade at the bench, a dish or a
    # tonic over a fire); the chit walks there first, as for an experiment
    station = str(step.get("at") or "").strip().lower() or None
    if station:
        station = {"campfire": "fire", "fire": "fire", "bench": "workshop", "workbench": "workshop"}.get(station, station)
        if station not in STATIONS:
            return f"'{station}' is not a known kind of station"
        mv = _gather_station(world, a, s, station)
        if mv == "none":
            return f"there's no {station} nearby to invent at"
        if mv == "blocked":
            return f"couldn't reach the {station}"
        if mv != "arrived":
            return RUNNING
    a.activity = "inventing"
    a.set_emote("💡", world.tick, 4)
    if not _work(a, a.skill_speed("crafting"), 10.0):
        return RUNNING
    a.practice("crafting", 0.8)
    v = verdict(bag, purpose_text, world.catalog, world.stations_at(a.x, a.y))  # (what stands here counts, asked for or not)
    ok, pid, effect, feedback = v["ok"], v["purpose"], v["effect"], v["feedback"]
    combo =" + ".join(f"{n} {world.item_name(k)}" if n > 1 else world.item_name(k) for k, n in sorted(bag.items()))
    if not ok:
        a.remember(world.tick, f"I tried to invent a {name} from {combo}: {feedback}", 3, "experiment")
        return feedback
    # (one of this world's own: one brought from over the sea is its carrier's knowledge, in world.foreign, and nobody
    # here has had "the same idea")
    same = next((k for k, inv in world.inventions.items() if inv["purpose"] == pid and inv["inputs"] == bag
                 and inv.get("station") == v["station"]), None)
    for k, n in bag.items():
        a.remove(k, n)
    if same is not None:
        a.inventory[same] = a.inventory.get(same, 0) + 1
        if not world.learned(a, "recipe:" + same, "discovered"):
            a.made_it_work("recipe:" + same, world.tick)
        s["note"] = f"Made a {world.item_name(same)} (someone here had the same idea)"
        return DONE
    key = f"inv_{world.id.lower()}_{len(world.inventions) + 1}"
    props = invention_props(bag, pid, world.catalog)
    register_invention(world, key, name, bag, props, effect, v["station"])
    world.inventions[key] = {"key": key, "name": name, "inputs": dict(bag), "purpose": pid, "purpose_text": purpose_text,
                             "effect": effect, "props": list(props), "by": a.id, "by_name": a.name, "tick": world.tick,
                             # which of invent.RULES made it (None from the first engine), and the station that rule
                             # needs: the thing can only be made again there
                             "rule": v["rule"], "station": v["station"]}
    a.inventory[key] = a.inventory.get(key, 0) + 1
    world.learned(a, "recipe:" + key, "discovered")
    words = " and ".join(f"{n} {world.item_name(k)}" if n > 1 else world.item_name(k) for k, n in sorted(bag.items()))
    world.emit("invention", f"{a.name} invented the {name} ({pid}) from {words} — nothing like it exists anywhere else",
               5, a.id, a.x, a.y, key=key, name=name, purpose=pid, inputs=dict(bag))
    a.bump("inventions")
    a.remember(world.tick, f"I invented the {name} ({pid}) from {combo}", 5, "discovery")
    s["note"] = f"Invented the {name}"
    return DONE


def _do_pray(world, a: Agent, step, s) -> str:
    """Quiet time at a shrine (T21). A chit with no belief of its own may come to share the shrine's."""
    sh = world.structures.get(s.get("shrine") or str(step.get("target") or ""))
    if sh is None or sh.design != "shrine" or not sh.functional:
        sh = next((x for x in world.structures_near(a.x, a.y, 30, "shrine") if x.functional), None)
        if sh is None:
            return "there is no shrine nearby to pray at"
    s["shrine"] = sh.id
    mv = _goto_structure(world, a, s, sh)
    if mv == "blocked":
        return "couldn't reach the shrine"
    if mv != "arrived":
        return RUNNING
    a.activity = "praying"
    a.set_emote("🕯", world.tick, 4)
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 12:
        return RUNNING
    a.mood = min(100.0, a.mood + 6)
    bel = world.beliefs.get(sh.belief)
    if not a.belief and bel and world.convert(a, sh.belief, "prayed"):
        s["note"] = f"Prayed at the {sh.name or 'shrine'} and came to believe in {bel['name']}"
    else:
        s["note"] = f"Prayed at the {sh.name or 'shrine'} and felt calmer"
    return DONE


def _do_preach(world, a: Agent, step, s) -> str:
    if not world.flags.get("say"):
        return "in this world chits cannot talk, so there is no preaching"
    bel = world.beliefs.get(a.belief)
    if not bel:
        return "I don't believe in anything to preach about"
    a.activity = "preaching"
    if not _work(a, 1.0, 4.0):
        return RUNNING
    a.speak(bel["tenet"], world.tick)
    won = []
    for o in world.agents_near(a.x, a.y, 6, exclude=a.id):
        if o.belief or o.activity == "sleeping":
            continue
        if a.belief not in o.met_beliefs:
            o.met_beliefs.append(a.belief)
        p = max(0.05, min(0.9, 0.25 + o.affinity.get(a.id, 0.0) / 200))
        if world.rng_for("beliefs").random() < p and world.convert(o, a.belief, "preached"):
            won.append(o.name)
            o.like(a.id, 4)
    a.bump("preached")
    world.emit("speech", f'{a.name} preached: "{bel["tenet"]}"', 2, a.id, a.x, a.y, said=bel["tenet"], to="all")
    s["note"] = f"Preached {bel['name']}" + (f"; {', '.join(won)} came to believe" if won else "; nobody was moved")
    return DONE


def _trade_bag(world, raw: Any) -> Optional[Dict[str, int]]:
    """{"berries":3} | "stone axe" | ["wood","wood"] -> {key: n}; None if anything isn't a real item."""
    if raw is None or raw == "" or raw == {} or raw == []:
        return None
    out: Dict[str, int] = {}
    if isinstance(raw, dict):
        items = []
        for k, v in raw.items():
            try:
                n = max(1, min(99, int(v)))
            except (TypeError, ValueError):
                n = 1
            items.append((k, n))
    elif isinstance(raw, list):
        items = [(x, 1) for x in raw]
    else:
        items = [(raw, 1)]
    for k, n in items:
        key = world.norm_item(k)
        if not key:
            return None
        out[key] = out.get(key, 0) + n
    return out


def _words(world, bag: Dict[str, int]) -> str:
    return ", ".join(f"{n} {world.item_name(k)}" for k, n in bag.items())


BARTER_LOAD = 12  # a trader's hold: the most goods it takes home


def _trade_at_stores(world, a: Agent, step, s) -> str:
    """{"do":"trade","at":"stores"}: a trader from over the sea swaps its load at this village's stores for goods of
    the same worth (a silent trade, as between peoples with no common tongue: it works in any culture), preferring what
    it has never had."""
    if not a.origin or a.voyage_intent != "trade":
        return "only a trader from over the sea barters at the stores"
    if a.stats.get("traded_trip"):
        return "I've made my trade here: time to sail home"
    load = {k: n for k, n in a.inventory.items() if n > 0 and (it := world.item(k)) is not None and not it.tool
            and not it.carry_bonus}
    if not load:
        a.stats["traded_trip"] = 1
        return "I have nothing left to trade: time to sail home"
    # the boat may land far from the village: look over the whole island
    pile = _find_structure(world, a, step.get("target"), max(world.w, world.h), lambda x: x.design in STORES
                           and x.functional and any(k not in load and n > 0 for k, n in x.storage.items())
                           and world.same_land(a, x))
    if pile is None or pile.design not in STORES:
        a.stats["traded_trip"] = 1
        return "there are no stores here with anything to trade for: time to sail home"
    mv = _goto_structure(world, a, s, pile)
    if mv == "blocked":
        return "couldn't reach the stores"
    if mv != "arrived":
        return RUNNING
    base_value = world.catalog.value  # (a content pack's goods are worth what goes into them)
    worth = sum(base_value(k) * n for k, n in load.items())
    wares = sorted(((k, n) for k, n in pile.storage.items() if n > 0 and k not in load),
                   key=lambda kn: (kn[0] in a.familiar, -base_value(kn[0]), kn[0]))
    got: Dict[str, int] = {}
    left = worth
    for k, n in wares:
        v = base_value(k)
        take = min(n, int(left // v), BARTER_LOAD - sum(got.values()))
        if take > 0:
            got[k] = take
            left -= take * v
        if sum(got.values()) >= BARTER_LOAD or left < 1:
            break
    if not got:
        a.stats["traded_trip"] = 1
        return "nothing in these stores is worth as little as what I brought: time to sail home"
    for k, n in load.items():
        a.inventory.pop(k, None)
        pile.storage[k] = pile.storage.get(k, 0) + n
    for k, n in got.items():
        pile.storage[k] -= n
        if pile.storage[k] <= 0:
            pile.storage.pop(k)
        a.inventory[k] = a.inventory.get(k, 0) + n
    world.dirty_struct.add(pile.id)
    world.notice_items(a)
    a.bump("bartered")
    a.stats["traded_trip"] = 1
    world.incident(a, None, "trade")  # trade eases the islands' hostility (T34)
    home = a.homeland or a.origin
    world.emit("trade", f"{a.name}, a trader from over the sea, left {_words(world, load)} at the stores and took "
                        f"{_words(world, got)}", 3, a.id, a.x, a.y, overseas=True, homeland=home, give=load, get=got)
    s["note"] = f"Traded {_words(world, load)} for {_words(world, got)}"
    return DONE


def _who(world, a: Agent, s, name) -> Optional[Agent]:
    """The chit called `name` for this action: the nearest namesake, found once and kept. Looked up every tick, a
    nearer namesake could take over mid-way, and get a lesson nine ticks of which went to the other (Codex, #35)."""
    key = str(name or "").strip().lower()
    if s.get("_who") and s.get("_who_name") == key:
        return world.agents.get(s["_who"])  # (gone: the action fails rather than turning to another of that name)
    o = world.agent_by_name(name, near=a)
    if o is not None:
        s["_who"], s["_who_name"] = o.id, key
    return o


def _do_trade(world, a: Agent, step, s) -> str:
    """Barter (T25): no words needed, so it works in both worlds. The partner judges the deal by what it's worth to them."""
    if str(step.get("at") or "").strip().lower() in ("stores", "stockpile", "the stores"):
        return _trade_at_stores(world, a, step, s)
    other = _who(world, a, s, step.get("to") or step.get("target") or "")
    if not other or other is a or not other.alive:
        return f"there's nobody called {step.get('to')} to trade with"
    give = _trade_bag(world, step.get("give"))
    get = _trade_bag(world, step.get("get") or step.get("for") or step.get("what"))
    if not give or not get:
        return "a trade needs something to give and something to get (real items)"
    if any(a.inventory.get(k, 0) < n for k, n in give.items()):
        return f"I don't have {_words(world, give)} to give"
    if any(other.inventory.get(k, 0) < n for k, n in get.items()):
        return f"{other.name} doesn't have {_words(world, get)}"
    mv = _approach_agent(world, a, s, other, 1)
    if mv == "blocked" or s.get("ticks", 0) > 250:
        return f"couldn't reach {other.name}"
    if mv != "arrived":
        return RUNNING
    a.activity = "trading"
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 4:
        return RUNNING
    from . import ballots

    verdict = ballots.offer_verdict(world, a, other, give, get, s)  # a model-minded partner's own mind answers
    if verdict is None:
        return RUNNING
    if not verdict:
        a.like(other.id, -1)
        return f"{other.name} didn't want that deal"
    w_give = sum((world.item(k).weight if world.item(k) else 1) * n for k, n in give.items())
    w_get = sum((world.item(k).weight if world.item(k) else 1) * n for k, n in get.items())
    if a.free_space() + w_give < w_get or other.free_space() + w_get < w_give:
        return "one of us couldn't carry the result"
    for k, n in give.items():
        a.remove(k, n)
        other.inventory[k] = other.inventory.get(k, 0) + n
    for k, n in get.items():
        other.remove(k, n)
        a.inventory[k] = a.inventory.get(k, 0) + n
    world.notice_items(a)
    world.notice_items(other)
    a.like(other.id, 2)
    other.like(a.id, 2)
    a.bump("trades")
    other.bump("trades")
    world.emit("trade", f"{a.name} traded {_words(world, give)} to {other.name} for {_words(world, get)}", 2, a.id, a.x, a.y,
               to=other.id, give=give, get=get)
    world.record_trade(a, other, give, get)
    world.incident(a, other, "trade")
    other.remember(world.tick, f"I traded {_words(world, get)} to {a.name} for {_words(world, give)}", 2, "social")
    s["note"] = f"Traded {_words(world, give)} to {other.name} for {_words(world, get)}"
    return DONE


def _uniq(agents) -> List[Agent]:
    seen, out = set(), []
    for o in agents:
        if o is not None and o.id not in seen:
            seen.add(o.id)
            out.append(o)
    return out


def _watchers(world, st, radius: int, exclude: Agent) -> List[Agent]:
    return [o for o in world.agents.values() if o is not exclude and o.activity != "sleeping" and st.dist(o.x, o.y) <= radius]


def _do_steal(world, a: Agent, step, s) -> str:
    """Take from someone else's stockpile (T27). Guards may catch you; everyone who sees it remembers."""
    k = world.norm_item(step.get("what"))
    if not k:
        return f"'{step.get('what')}' isn't an item"
    st = _find_structure(world, a, step.get("target"), 30, lambda x: x.design in STORES and x.functional and x.storage.get(k, 0) > 0)
    if not st:
        return f"no stockpile nearby has {world.item_name(k)}"
    if st.founder == a.id:
        return "that's my own stockpile: I can just take from it"
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach the stockpile"
    if mv != "arrived":
        return RUNNING
    a.activity = "sneaking"
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 5:
        return RUNNING
    founder = world.agents.get(st.founder)
    nm = world.item_name(k)
    catcher = next((o for o in _watchers(world, st, 4, a) if o.activity == "guarding" or o.job == "guard"), None)
    if catcher:
        a.health = max(1.0, a.health - 10)
        for o in _uniq([catcher, founder]):
            o.like(a.id, -20)
            o.remember(world.tick, f"{a.name} tried to steal {nm} from the stockpile", 4, "grudge")
        a.remember(world.tick, f"{catcher.name} caught me stealing {nm}", 4, "grudge")
        a.like(catcher.id, -10)
        world.emit("caught", f"{catcher.name} caught {a.name} stealing {nm}", 3, catcher.id, *st.center(), thief=a.id, item=k)
        return f"{catcher.name} caught me stealing"
    n = min(st.storage.get(k, 0), _qty(step, 3), 3)
    got = a.add(k, n)
    if not got:
        return "my hands are full"
    st.storage[k] -= got
    if st.storage[k] <= 0:
        st.storage.pop(k, None)
    world.dirty_struct.add(st.id)
    for o in _uniq(_watchers(world, st, 6, a) + [founder]):
        if o is a:
            continue
        o.like(a.id, -25)
        o.remember(world.tick, f"{a.name} stole {got} {nm} from the stockpile", 4, "grudge")
    a.bump("stole")
    a.remember(world.tick, f"I stole {got} {nm} from the stockpile", 3, "event")
    world.emit("theft", f"{a.name} stole {got} {nm} from the stockpile", 3, a.id, *st.center(), item=k, n=got, stockpile=st.id)
    if a.origin:
        a.bump("stole_abroad", got)
    world.incident(a, founder, "theft")
    s["note"] = f"Stole {got} {nm}"
    return DONE


def _do_guard(world, a: Agent, step, s) -> str:
    st = _find_structure(world, a, step.get("target"), 30, lambda x: x.complete)
    if not st:
        return "there's nothing nearby to guard"
    if st.dist(a.x, a.y) > 2:
        mv = _goto_structure(world, a, s, st)
        if mv == "blocked":
            return "couldn't get there"
        if st.dist(a.x, a.y) > 2:
            return RUNNING
    a.activity = "guarding"
    s["t"] = s.get("t", 0) + 1
    if s["t"] < max(10, min(240, _qty(step, 60) if step.get("qty") else 60)):
        return RUNNING
    a.bump("guarded")
    s["note"] = f"Kept watch over the {DESIGNS[st.design].name} {st.id}"
    return DONE


def _strength(a: Agent) -> float:
    return 10 + 8 * (a.best_tool("spear") is not None) + 12 * (a.best_tool("weapon") is not None)


def _do_fight(world, a: Agent, step, s) -> str:
    """A scuffle (T27): it hurts and leaves grudges, but nobody is killed in a fight."""
    other = _who(world, a, s, step.get("to") or step.get("target") or "")
    if not other or other is a or not other.alive:
        return f"there's nobody called {step.get('to')} here"
    mv = _approach_agent(world, a, s, other, 1)
    if mv == "blocked" or s.get("ticks", 0) > 250:
        return f"couldn't reach {other.name}"
    if mv != "arrived":
        return RUNNING
    sa, sb = _strength(a), _strength(other)
    win, lose = (a, other) if world.rng_for("combat").random() * (sa + sb) < sa else (other, a)
    for x, dmg in ((lose, 20), (win, 5)):
        if x.health > 5:
            x.health = max(5.0, x.health - dmg)
    for x, y in ((a, other), (other, a)):
        x.mood = max(0.0, x.mood - 10)
        x.like(y.id, -30)
        x.remember(world.tick, f"I fought {y.name}" + (" and won" if x is win else " and lost"), 4, "grudge")
    raid = other.activity == "guarding"
    a.bump("fights")
    world.incident(a, other, "fight")
    world.emit("fight", f"{a.name} and {other.name} fought; {win.name} came out on top", 3, a.id, a.x, a.y,
               opponent=other.id, winner=win.id, raid=raid)
    s["note"] = f"Fought {other.name}; " + ("I won" if win is a else "I lost")
    return DONE


def _door_hut(world, a: Agent):
    """A hut or house right next to this chit that it could step inside (it isn't inside one already)."""
    if world.in_home(a):
        return None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            x, y = a.x + dx, a.y + dy
            sid = world.occupied.get(y * world.w + x) if world.inb(x, y) else None
            st = world.structures.get(sid) if sid else None
            if st and st.functional and st.design in BLD.HOMES and \
                    any(world.passable(*c) for c in st.cells()):
                return st
    return None


def _do_shelter(world, a: Agent, step, s) -> str:
    """Get indoors (own home, any hut/house) or, unless it's a storm, beside a lit fire; wait out the weather."""
    door = _door_hut(world, a) if not s.get("no_way_in") else None
    if door is not None:  # sheltered by the wall, but the cold only stays out inside: go in
        mv = move_toward(world, a, s, {c for c in door.cells() if world.passable(*c)})
        if mv == "blocked":
            s["no_way_in"] = True
        elif mv != "arrived":
            a.activity = "hurrying for shelter"
            return RUNNING
    if world.sheltered(a):
        a.activity = "sheltering"
        if world.weather not in ("storm", "snow") or s.get("waited", 0) >= 240:
            s["note"] = "Waited out the weather under cover"
            return DONE
        s["waited"] = s.get("waited", 0) + 1
        return RUNNING
    st = world.structures.get(s.get("tgt") or "")
    if st is None or not st.functional:
        cands = []
        home = world.structures.get(a.home or "")
        if home and home.functional:
            cands.append(home)
        cands += [x for x in world.structures_near(a.x, a.y, 30) if x.functional and x.design in BLD.HOMES]
        if not cands and world.weather != "storm":
            cands = [x for x in world.structures_near(a.x, a.y, 30, "campfire") if x.lit]
        if not cands:
            return "there is nowhere to shelter nearby — a hut would keep the weather out"
        st = cands[0]
        s["tgt"] = st.id
    if st.design in BLD.HOMES:
        mv = move_toward(world, a, s, {c for c in st.cells() if world.passable(*c)} or set(st.cells()))
    else:
        mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach shelter"
    a.activity = "hurrying for shelter"
    return RUNNING


def _do_mark(world, a: Agent, step, s) -> str:
    """Leave a sign on this tile. It needs no words, so the silent world can use it too."""
    raw = str(step.get("what") or step.get("text") or "").strip().lower()
    sym = SIGN_ALIASES.get(raw, raw)
    if sym not in SIGN_SYMBOLS:
        return f"'{raw or '?'}' isn't a sign anyone would understand; signs can say: {', '.join(SIGN_SYMBOLS)}"
    if not a.has("wood"):
        return "a sign needs 1 wood for the post"
    a.activity = "putting up a sign"
    if s["ticks"] < 4:
        return RUNNING
    a.remove("wood", 1)
    for gid, g in list(world.signs.items()):
        if g["x"] == a.x and g["y"] == a.y:
            del world.signs[gid]
    gid = world._new_id("gsign")  # g1, g2... (structure ids already use "s")
    world.signs[gid] = {"id": gid, "x": a.x, "y": a.y, "symbol": sym, "author": a.id, "author_name": a.name,
                        "tick": world.tick}
    world.signs_dirty = True
    world.emit("sign", f"{a.name} put up a sign: {sym}", 2, a.id, a.x, a.y, sign=gid, symbol=sym)
    world.deliver("sign", a, a, None, sym)
    s["note"] = f"Put up a '{sym}' sign"
    return DONE


def sanitize_name(raw: Any) -> Optional[str]:
    """A chit-given name: letters, digits, spaces, ' and -; at most 24 characters; must contain a letter."""
    if raw is None:
        return None
    s = "".join(ch for ch in str(raw) if ch.isalnum() or ch in " '-")
    s = " ".join(s.split()).strip()[:24].strip()
    if not s or not any(ch.isalpha() for ch in s):
        return None
    return s


def _experiment_hint(bag: Dict[str, int], stations: Set[str], recipes: Optional[List[Any]] = None) -> str:
    """Physical feedback: the world 'feels' close without revealing recipes. `recipes`: this world's physics (the
    base recipes, then a content pack's)."""
    have = set(bag)
    recipes = list(RECIPES.values()) if recipes is None else recipes
    for r in recipes:
        need = dict(r.inputs)
        if need == bag and r.station and r.station not in stations:
            return {"fire": "It felt like it needed heat.", "kiln": "It needed far more heat than a campfire gives.",
                    "furnace": "Only a truly roaring fire could change this.",
                    "workshop": "Fiddly work — a proper workbench might help.",
                    "forge": "It needed a blast of heat beyond any furnace.",
                    "factory": "This needs machines, not hands.",
                    "mill": "It wanted grinding: a millstone might do it."}.get(r.station, "")
    for r in recipes:
        need = dict(r.inputs)
        if have < set(need) and all(bag[k] <= need[k] for k in bag):
            return "The pieces seemed to want something more."
        if set(need) == have and any(bag[k] != need[k] for k in bag):
            return "Right materials, wrong amounts perhaps."
    return ""


# a structure of the same kind this close is used instead of starting another: World A had 200 campfires (chits lit
# a new one beside every one that burned out), World B 153 farms beside empty ones, 30 shrines, 16 kilns
REUSE_WITHIN = {"campfire": 6, "farm": 8, "shrine": 12, "kiln": 12, "workshop": 12, "furnace": 12, "library": 15,
                "stockpile": 8}
REUSE_WITHIN.update(BLD.REUSE_WITHIN)  # wells, granaries, mills, smithies, towers, schools, bell towers


def _use_existing(world, a: Agent, key: str, s, x: Optional[int] = None, y: Optional[int] = None) -> Optional[str]:
    """One already stands where this would go up (x, y: by default where the chit is): use that instead."""
    x, y = (a.x, a.y) if x is None else (x, y)
    radius = REUSE_WITHIN.get(key)
    if not radius:
        return None
    if key == "stockpile" and sum(1 for x in world.structures.values() if x.design == "stockpile" and x.functional) \
            >= max(6, len(world.agents) // 6):
        # World A's model built 43 for 60 chits, most of them full of hoarded seeds
        s["note"] = "The village has plenty of stockpiles already: use what's stored in them, or take from a full one"
        return DONE
    near = [st for st in world.structures_near(x, y, radius, key) if st.complete and world.same_land(a, st)]
    if key == "shrine" and a.belief:
        # a believer's own shrine: only one of its own faith (or one not yet anyone's) stands in for it. With any
        # shrine counted, the second faith in a village could never raise its own (Codex #76)
        near = [st for st in near if st.belief in ("", a.belief)]
    if not near:
        return None
    if key == "campfire":
        st = near[0]
        if st.ruined:
            return None  # a ruin: build a new one
        s.clear()
        s["redirect"] = {"do": "refuel", "target": st.id}
        s["note"] = f"There was already a campfire close by ({st.id}); I fed it instead of building another"
        return _redirect(world, a, s)
    if key == "farm":
        empty = next((x for x in near if x.functional and not x.planted), None)
        if empty is not None:
            s.clear()
            s["redirect"] = {"do": "plant", "target": empty.id}
            s["note"] = f"There was an empty farm close by ({empty.id}); I sowed it instead of making another"
            return _redirect(world, a, s)
        return None  # every farm nearby is sown: a new one is fine
    if key == "stockpile" and any(stockpile_room(x, None, world.catalog) > 20 for x in near if x.functional):
        s["note"] = "There's a stockpile with room close by already"
        return DONE
    if key in ("shrine", "kiln", "workshop", "furnace", "library") or key in BLD.REUSE_WITHIN:
        st = next((x for x in near if x.functional), None)
        if st is not None:
            s["note"] = f"There's already a {DESIGNS[key].name} close by ({st.id} at {st.x},{st.y}): use that one"
            return DONE
    return None


def _redirect(world, a: Agent, s) -> str:
    """Run the step this build turned into (refuel a fire, sow a farm) to its end."""
    sub = s["redirect"]
    res = globals()[f"_do_{sub['do']}"](world, a, sub, s.setdefault("redirect_s", {}))
    if res == RUNNING:
        return RUNNING
    return DONE if res == DONE else res


def _do_build(world, a: Agent, step, s) -> str:
    if s.get("redirect"):
        return _redirect(world, a, s)
    if s.get("site"):
        return _do_help(world, a, step, s)
    key = normalize_design(step.get("what"))
    if not key:
        return f"'{step.get('what')}' is not a kind of structure anyone knows"
    if not a.knows_design(key):
        return f"I don't know how to build a {DESIGNS[key].name} yet"
    if key == "bridge":  # it goes over water, at the nearest narrow crossing
        return BLD.build_bridge(world, a, step, s)
    up = BLD.upgrade_instead(world, a, key, step)
    if up:  # a bigger home for a chit living in a smaller one close by: rebuild that one where it stands
        s["redirect"] = up
        return _redirect(world, a, s)
    ox, oy = a.x, a.y  # where it is to go up: here, or "near" a place (pioneers build at their new village's site)
    near = step.get("near") or step.get("at")
    if near:
        tgt = _resolve_place(world, a, near)
        if tgt:
            ox, oy = tgt
    elif key in BLD.TOWN_CENTRE:  # a town's public buildings go up around its hall, not wherever the builder stood
        hall = BLD.hall_near(world, a)
        if hall is not None:
            ox, oy = hall.x + hall.w // 2, hall.y + hall.h // 2
    # join an existing unfinished site of the same kind there rather than duplicating it
    for st in world.structures_near(ox, oy, 12, key):
        if not st.complete and a.reflex_rest.get("unreach:" + st.id, 0) <= world.tick and world.same_land(a, st):
            s["site"] = st.id
            s["joined"] = True
            return _do_help(world, a, step, s)
    reuse = _use_existing(world, a, key, s, ox, oy)
    if reuse is not None:
        return reuse
    cap = step.get("_cap")  # instinct decided "we need one" when planning; by now others may have started theirs
    if cap and sum(1 for x in world.structures.values() if x.design == key) >= cap:  # ruins count: they get restored
        s["note"] = f"There are enough {DESIGNS[key].name}s already"
        return DONE
    need_pop = DESIGNS[key].min_pop
    if need_pop and len(world.agents) < need_pop:
        return f"a {DESIGNS[key].name} is a great work: it needs at least {need_pop} people living here (there are {len(world.agents)})"
    if key in BLD.CITY_ONLY and BLD.city_of(world, ox, oy) is None:
        return (f"only a city can build a {DESIGNS[key].name}: a town of 40 or more with five kinds of public building "
                f"around its hall and paved streets")
    # models kept starting a second hut beside their own (53 huts for 26 chits); a pioneer's new home is the exception
    from . import pioneers as PI

    home = world.structures.get(a.home or "")
    crowded = home is not None and sum(o.home == home.id for o in world.agents.values()) > BLD.HOME_CAP.get(home.design, 3)
    if key == "hut" and home is not None and home.design in BLD.HOMES and home.functional \
            and not (crowded and home.founder != a.id) and not PI.builds_home_at(world, a, ox, oy):
        return (f"I already have a home ({DESIGNS[home.design].name} {home.id}): repair it if it's damaged, or help "
                f"build someone else's instead of a second one")
    pos = world.find_site(key, ox, oy, 8 if key != "road" else 3, reach=(a.x, a.y))
    # (a boat, lighthouse or mine is already sought far and wide: the wider tries would repeat the same search)
    for radius in ((16, 28) if key not in ("road", "boat", "lighthouse", "mine") else ()):
        pos = pos or world.find_site(key, ox, oy, radius, reach=(a.x, a.y))
    if not pos:
        a.reflex_rest["nobuild:" + key] = world.tick + TICKS_PER_DAY  # a crowded village: don't retry every plan
        return "there's no clear ground within 28 tiles: go somewhere open, or add \"near\":\"x,y\""

    st = world.place_site(key, pos[0], pos[1], a)
    st.builders[a.id] = 0.0
    s["site"] = st.id
    d = DESIGNS[key]
    need = ", ".join(f"{n} {world.item_name(k)}" for k, n in d.materials)
    if key != "road":
        world.emit("site", f"{a.name} started building a {d.name} (needs {need})", 2, a.id, *st.center(),
                   design=key, structure=st.id)
    a.remember(world.tick, f"I started a {d.name} at ({st.x},{st.y}); it needs {need}", 3, "build")
    return _do_help(world, a, step, s)


def _do_upgrade(world, a: Agent, step, s) -> str:
    """Rebuild your home bigger where it stands (hut -> longhouse or brick house, and on to a two-storey house)."""
    return BLD.do_upgrade(world, a, step, s)


def _resolve_place(world, a: Agent, ref: Any) -> Optional[Tuple[int, int]]:
    if isinstance(ref, (list, tuple)) and len(ref) == 2:
        try:
            return int(ref[0]), int(ref[1])
        except (TypeError, ValueError):
            return None
    if isinstance(ref, dict) and "x" in ref:
        try:
            return int(ref["x"]), int(ref["y"])
        except (TypeError, ValueError):
            return None
    r = str(ref).strip()
    if "," in r:
        try:
            x, y = r.strip("()[] ").split(",")[:2]
            return int(float(x)), int(float(y))
        except ValueError:
            pass
    if r.lower() in ("here", "me", "self"):
        return a.x, a.y
    o = world.agent_by_name(r, near=a)
    if o:
        return o.x, o.y
    st = _find_structure(world, a, r, 60)
    if st:
        return st.x, st.y
    return None


def _do_help(world, a: Agent, step, s) -> str:
    sid = s.get("site") or step.get("site") or step.get("target")
    st = world.structures.get(str(sid)) if sid else None
    if st is None and sid:
        dk = normalize_design(sid)
        cands = [x for x in world.structures_near(a.x, a.y, 30, dk) if not x.complete] if dk else []
        st = cands[0] if cands else None
    if st is None:
        cands = [x for x in world.structures_near(a.x, a.y, 25) if not x.complete and world.same_land(a, x)
                 and a.reflex_rest.get("unreach:" + x.id, 0) <= world.tick]
        st = cands[0] if cands else None
    if st is None:
        return "there's no construction site to help with"
    if st.complete and st.upgrade:  # a home being rebuilt bigger
        return BLD.do_upgrade(world, a, dict(step, target=st.id), s)
    if st.complete:
        s["note"] = f"The {DESIGNS[st.design].name} is already finished"
        return DONE
    s["site"] = st.id
    if s.get("fetch_from"):
        # the stockpile trip comes first: done after walking to the site, a pile more than ~3 tiles away had the chit
        # bouncing between the two until the step timed out, with the site still short of 2 wood
        pile = world.structures.get(s["fetch_from"])
        mv = _goto_structure(world, a, s, pile) if pile else "blocked"
        if mv not in ("arrived", "blocked"):
            return RUNNING
        if mv == "arrived":
            for k in list(st.needs):
                take = min(st.needs[k], pile.storage.get(k, 0))
                if take:
                    got = a.add(k, take)
                    pile.storage[k] -= got
                    if pile.storage[k] <= 0:
                        pile.storage.pop(k)
            world.dirty_struct.add(pile.id)
        s.pop("fetch_from", None)
        s.pop("goal_sig", None)
        s["repath"] = 0
        a.path = []
        return RUNNING
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        a.reflex_rest["unreach:" + st.id] = world.tick + TICKS_PER_DAY  # don't keep choosing it
        return "couldn't reach the construction site"
    if mv != "arrived":
        return RUNNING
    d = DESIGNS[st.design]
    # deliver whatever is needed
    delivered = []
    for k in list(st.needs):
        n = st.needs[k]
        give = min(n, a.inventory.get(k, 0))
        if give:
            a.remove(k, give)
            st.needs[k] -= give
            if st.needs[k] <= 0:
                st.needs.pop(k)
            st.builders[a.id] = st.builders.get(a.id, 0) + give
            st.last_work = world.tick
            delivered.append(f"{give} {world.item_name(k)}")
            world.dirty_struct.add(st.id)
    if delivered and st.founder != a.id:
        f = world.agents.get(st.founder)
        if f:
            f.like(a.id, 3)
            a.like(f.id, 2)
        if not s.get("announced"):
            s["announced"] = True
            fname = f.name if f else "someone"
            world.emit("helped", f"{a.name} brought {', '.join(delivered)} to {fname}'s {d.name}", 2, a.id,
                       *st.center(), structure=st.id)
    if st.needs:
        # try the stockpile before giving up
        pile = _stockpile_with(world, a, list(st.needs), 25)
        if pile and not s.get("fetched") and a.free_space() > 0:
            s["fetched"] = True
            s["fetch_from"] = pile.id
            s.pop("goal_sig", None)
            s["repath"] = 0
            a.path = []
            return RUNNING
        need = ", ".join(f"{n} {world.item_name(k)}" for k, n in st.needs.items())
        s["note"] = f"The {d.name} still needs {need}"
        return DONE
    a.activity = f"building {d.name}"
    a.emote = "🔨"
    a.emote_until = world.tick + 2
    st.work_done += a.skill_speed("building") * (1.1 if a.mood > 70 else 1.0)
    st.builders[a.id] = st.builders.get(a.id, 0) + 1
    st.last_work = world.tick
    a.practice("building", 0.3)
    if world.tick % 6 == 0:
        world.dirty_struct.add(st.id)
    if st.work_done >= st.work_total:
        world.complete_structure(st, a)
        s["note"] = f"Finished the {d.name}!"
        return DONE
    return RUNNING


def _do_store(world, a: Agent, step, s) -> str:
    st = None
    if not step.get("target") and not s.get("pile"):
        st = next((x for x in world.structures_near(a.x, a.y, 30, "stockpile") if x.functional and stockpile_room(x, None, world.catalog) > 0), None)
        if st:
            s["pile"] = st.id
    st = st or world.structures.get(s.get("pile") or "") or \
        _find_structure(world, a, step.get("target"), 30, lambda x: x.design in STORES and x.functional)
    if not st and not step.get("target"):
        # nothing to store in: keep the things and go on with the plan (as a failure it threw the rest of the
        # plan away, 73 times in a day in World B, where instinct stores its harvest before any stockpile exists)
        s["note"] = "There's no stockpile nearby yet, so I kept my things"
        return DONE
    if not st:
        return "there's no stockpile nearby"
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach the stockpile"
    if mv == "moving" and _long_way(a, s, st.x, st.y):
        a.reflex_rest["unreach:" + st.id] = world.tick + TICKS_PER_DAY
        s["note"] = "That stockpile is a long way round on foot, so I kept my things"
        return DONE
    if mv != "arrived":
        return RUNNING
    what = step.get("what") or "all"
    items: Dict[str, int] = {}
    if str(what).lower() in ("all", "everything", "extra", "surplus", "materials"):
        for k, n in a.inventory.items():
            if world.item(k).tool or world.item(k).carry_bonus:
                continue
            keep = kept_in_hand(world, k)  # (a bite stays in hand, and one of an invention that works while carried)
            if n > keep:
                items[k] = n - keep
    else:
        k = world.norm_item(what)
        if not k or not a.has(k):
            return f"I'm not carrying any {what}"
        items[k] = min(a.inventory[k], _qty(step, a.inventory[k], 1, 99))
    space = store_cap(st) - sum(st.storage.values())
    # a stockpile keeps room for food: materials may fill at most GOODS_SHARE of it
    goods_room = stockpile_room(st, None, world.catalog)
    stored = []
    food = {k: is_food(k, world.catalog) for k in items}
    for k, n in sorted(items.items(), key=lambda kv: not food[kv[0]]):  # food first
        n = min(n, space if food[k] else min(space, goods_room))
        if n <= 0:
            continue
        a.remove(k, n)
        st.storage[k] = st.storage.get(k, 0) + n
        space -= n
        if not food[k]:
            goods_room -= n
        stored.append(f"{n} {world.item_name(k)}")
    world.dirty_struct.add(st.id)
    if not stored:
        # full by the time it got there (76 failures a day in World B): try another pile, else keep the things and
        # go on with the plan instead of throwing it away
        tried = s.setdefault("tried", [])
        tried.append(st.id)
        other = next((x for x in world.structures_near(a.x, a.y, 30, "stockpile") if x.functional and x.id not in tried
                      and stockpile_room(x, None, world.catalog) > 0 and world.same_land(a, x)), None) if items else None
        if other is not None and len(tried) < 3:
            s["pile"] = other.id
            step.pop("target", None)
            s.pop("goal_sig", None)
            a.path = []
            return RUNNING
        s["note"] = "Every stockpile nearby is full, so I kept my things" if items else "I had nothing to store"
        return DONE
    a.bump("stored", sum(items.values()))
    s["note"] = f"Stored {', '.join(stored)} in the stockpile"
    return DONE


def _do_take(world, a: Agent, step, s) -> str:
    k = world.norm_item(step.get("what"))
    if not k:
        return f"'{step.get('what')}' isn't an item"
    want = s.setdefault("want", _qty(step, 3))
    taken = s.get("taken", 0)
    if taken >= want:
        return DONE
    st = _find_structure(world, a, step.get("target"), 30, lambda x: x.design in STORES + ("pen",) and x.functional
                         and x.storage.get(k, 0) > 0 and world.same_land(a, x)
                         and a.reflex_rest.get("unreach:" + x.id, 0) <= world.tick)
    if not st:
        return f"no stockpile nearby has {world.item_name(k)} (still need {want - taken})"
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach the stockpile"
    if mv != "arrived":
        return RUNNING
    n = min(st.storage.get(k, 0), want - taken)
    got = a.add(k, n)
    st.storage[k] = st.storage.get(k, 0) - got
    if st.storage[k] <= 0:
        st.storage.pop(k, None)
    world.dirty_struct.add(st.id)
    world.notice_items(a)
    s["taken"] = taken + got
    s["note"] = f"Took {s['taken']} of {want} {world.item_name(k)} from the stockpiles"
    if not got:
        return "my hands are full"
    return DONE if s["taken"] >= want else RUNNING


def _approach_agent(world, a: Agent, s, other: Agent, dist: int = 1) -> str:
    if max(abs(a.x - other.x), abs(a.y - other.y)) <= dist:
        return "arrived"
    if s.get("last_target") != (other.x, other.y) and s["ticks"] % 4 == 0:
        a.path = []
        s["last_target"] = (other.x, other.y)
        s.pop("goal_sig", None)
    goals = {(other.x + dx, other.y + dy) for dx in range(-dist, dist + 1) for dy in range(-dist, dist + 1)
             if world.passable(other.x + dx, other.y + dy)}
    return move_toward(world, a, s, goals)


def _do_give(world, a: Agent, step, s) -> str:
    other = _who(world, a, s, step.get("to") or step.get("target") or "")
    st = world.structures.get(str(step.get("to") or step.get("target") or "")) if not other else None
    if st is not None and st.design in STORES and st.complete:
        return _do_store(world, a, dict(step, do="store", target=st.id), s)
    if st is not None and not st.complete:
        return _do_help(world, a, dict(step, do="help", site=st.id), s)
    if not other:
        return f"there's no one called {step.get('to')} around"
    k = world.norm_item(step.get("what"))
    if not k or not a.has(k):
        return f"I don't have any {step.get('what')}"
    mv = _approach_agent(world, a, s, other)
    if mv == "blocked" or s["ticks"] > 250:
        return f"couldn't reach {other.name}"
    if mv != "arrived":
        return RUNNING
    n = min(a.inventory[k], _qty(step, 1, 1, 30))
    got = other.add(k, n)
    if not got:
        return f"{other.name}'s hands are full"
    a.remove(k, got)
    other.like(a.id, 3 + got)
    a.like(other.id, 2)
    other.remember(world.tick, f"{a.name} gave me {got} {world.item_name(k)}", 3, "social")
    world.notice_items(other)
    world.emit("gift", f"{a.name} gave {other.name} {got} {world.item_name(k)}", 2, a.id, a.x, a.y, to=other.id, item=k)
    world.incident(a, other, "gift")
    a.set_emote("🎁", world.tick, 20)
    s["note"] = f"Gave {other.name} {got} {world.item_name(k)}"
    return DONE


def _do_say(world, a: Agent, step, s) -> str:
    if not world.flags.get("say"):
        return "in this world chits cannot talk to one another"
    text = str(step.get("text") or step.get("what") or step.get("message") or "").strip()
    if not text:
        return "had nothing to say"
    to = step.get("to")
    other = _who(world, a, s, to) if to and str(to).lower() not in ("all", "everyone", "anyone") else None
    if other and not s.get("close"):
        mv = _approach_agent(world, a, s, other, 4)
        if mv == "blocked" or s["ticks"] > 150:
            return f"couldn't find {other.name} to talk to"
        if mv != "arrived":
            return RUNNING
        s["close"] = True
    a.activity = "talking"
    if not s.get("spoke"):
        s["spoke"] = True
        a.speak(text, world.tick)
        if a.spoken_to and (other is None or other.id == a.spoken_to.get("id")):
            a.spoken_to = {}  # answered (to them, or to everyone around)
        heard = []
        for o in world.agents_near(a.x, a.y, 6, exclude=a.id):
            if o.activity == "sleeping":
                continue
            addressed = other is not None and o.id == other.id
            o.remember(world.tick, f'{a.name} said{" to me" if addressed else ""}: "{text[:120]}"', 3 if addressed else 2, "heard")
            o.like(a.id, 1.5 if addressed else 0.5)
            a.like(o.id, 0.5)
            heard.append(o.name)
            if addressed:
                # kept until answered: a step note used to overwrite "just said to you" before the next prompt
                o.spoken_to = {"id": a.id, "name": a.name, "text": text[:120], "tick": world.tick}
                if o.plan and not o.thinking:
                    o.last_result = f'{a.name} just said to you: "{text[:120]}"'
        a.bump("said")
        diag.spoke(world, a, other.id if other else None, len(heard))
        for o in world.agents_near(a.x, a.y, 6, exclude=a.id):
            if o.name in heard:
                world.deliver("say", a, o, None, text[:160])
        world.emit("speech", f'{a.name}{" to " + other.name if other else ""}: "{text[:140]}"', 1, a.id, a.x, a.y,
                   to=other.id if other else None, heard=heard)
    if s["ticks"] > 4:
        s["note"] = f'Said "{text[:60]}"'
        return DONE
    return RUNNING


def _knowledge_key(raw: Any, world=None) -> Optional[str]:
    if not raw:
        return None
    if world is not None:  # this world's own inventions and local names, by key or name (T20)
        inv = world.invention_by_name(raw) or world.invention_by_name(str(raw).split(":", 1)[-1])
        if not inv and not normalize_item(str(raw).split(":", 1)[-1]) and not normalize_design(str(raw).split(":", 1)[-1]):
            inv = world.culture_item(raw) or world.culture_item(str(raw).split(":", 1)[-1])
        if inv:
            return f"recipe:{inv}"
    r = str(raw).strip().lower()
    if r.startswith("recipe:") or r.startswith("design:"):
        kind, k = r.split(":", 1)
        k = k.strip().replace(" ", "_")
        if (kind == "recipe" and k in RECIPES) or (kind == "design" and k in DESIGNS):
            return f"{kind}:{k}"
        if kind == "recipe" and world is not None and k in world.catalog.pack_recipes:
            return f"recipe:{k}"
        r = k
    for p in ("how to make ", "how to build ", "making ", "building ", "a ", "the "):
        if r.startswith(p):
            r = r[len(p):]
    it = normalize_item(r)
    if it and it in RECIPES:
        return f"recipe:{it}"
    if it is None and world is not None and world.catalog.pack_key(r) in world.catalog.pack_recipes:
        return f"recipe:{world.catalog.pack_key(r)}"  # (a content pack's recipe, by key or name)
    d = normalize_design(r)
    if d:
        return f"design:{d}"
    return None


def _do_teach(world, a: Agent, step, s) -> str:
    if not world.flags.get("teach"):
        return "in this world chits cannot teach one another directly"
    kk = _knowledge_key(step.get("what"), world)
    if not kk:
        return f"'{step.get('what')}' isn't something that can be taught"
    who = str(step.get("to") or step.get("target") or "").strip()
    other = _who(world, a, s, who) if who.lower() not in ("", "all", "everyone", "anyone", "others") else None
    if other is None and who.lower() in ("", "all", "everyone", "anyone", "others"):
        near = [o for o in world.agents.values() if o is not a and kk not in o.knows and o.activity != "sleeping"
                and max(abs(o.x - a.x), abs(o.y - a.y)) <= 8]
        other = min(near, key=lambda o: max(abs(o.x - a.x), abs(o.y - a.y)), default=None)
        if other is None:
            return "there's no one nearby who doesn't already know that"
    if not other:
        return f"there's no one called {step.get('to')} around"
    if kk not in a.knows:
        return "I can't teach what I don't know"
    if kk in other.knows:
        s["note"] = f"{other.name} already knows that"
        return DONE
    mv = _approach_agent(world, a, s, other, 1)
    if mv == "blocked" or s["ticks"] > 250:
        return f"couldn't reach {other.name}"
    if mv != "arrived":
        return RUNNING
    a.activity = "teaching"
    a.emote = "📖"
    a.emote_until = world.tick + 2
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 10:
        return RUNNING
    world.learned(other, kk, "taught", a)
    a.like(other.id, 5)
    other.like(a.id, 6)
    a.bump("taught")
    s["note"] = f"Taught {other.name} {kk.split(':')[1].replace('_', ' ')}"
    return DONE


def _do_write(world, a: Agent, step, s) -> str:
    if not world.flags.get("write"):
        return "in this world chits cannot leave written messages"
    what_raw = str(step.get("what") or "").strip().lower()
    bel = world.beliefs.get(a.belief)
    if bel and (what_raw in ("belief", "my belief", "faith", "scripture", "teachings", "tenet") or what_raw == bel["name"].lower()
                or what_raw == f"belief:{a.belief}"):
        kk = f"belief:{a.belief}"
    else:
        kk = _knowledge_key(step.get("what"), world)
        if not kk or kk not in a.knows:
            return "I can only write down something I know"
    surface = "clay_tablet" if a.has("clay_tablet") else ("paper" if a.has("paper") else None)
    if not surface:
        return "I need a clay tablet (or paper) to write on"
    lib = next((x for x in world.structures_near(a.x, a.y, 25, "library") if x.functional), None)
    if lib:
        mv = _goto_structure(world, a, s, lib)
        if mv == "moving":
            return RUNNING
    a.activity = "writing"
    a.emote = "✍️"
    a.emote_until = world.tick + 2
    if not _work(a, 1.0, 8.0):
        return RUNNING
    a.remove(surface, 1)
    tid = world._new_id("tablet")
    from .world import Tablet

    kind, key = kk.split(":", 1)
    if kind == "belief":
        b = world.beliefs[key]
        tb = Tablet(tid, kk, a.id, a.name, world.tick, a.x, a.y, lib.id if lib and lib.dist(a.x, a.y) <= 2 else None,
                    f"{b['name']}: {b['tenet']}")
        world.tablets[tid] = tb
        if tb.in_structure:
            lib.shelf.append(tid)
            world.dirty_struct.add(lib.id)
        a.bump("wrote")
        world.emit("tablet", f"{a.name} inscribed the teachings of {b['name']}", 3, a.id, a.x, a.y, tablet=tid, knowledge=kk)
        n = sum(1 for t in world.tablets.values() if t.knowledge == kk)
        if n >= 3 and not b.get("scripture"):
            b["scripture"] = world.tick
            world.emit("scripture", f"The {b['name']} now has a scripture — 3 tablets of teachings", 5, a.id, a.x, a.y,
                       belief=key)
        s["note"] = f"Wrote down the teachings of {b['name']}"
        return DONE
    what = world.item_name(key) if kind == "recipe" else DESIGNS[key].name
    text = world.catalog.describe(world.recipe(key)) if kind == "recipe" else (
        f"a {DESIGNS[key].name} is built from " + ", ".join(f"{n} {world.item_name(m)}" for m, n in DESIGNS[key].materials))
    tb = Tablet(tid, kk, a.id, a.name, world.tick, a.x, a.y, lib.id if lib and lib.dist(a.x, a.y) <= 2 else None, text)
    world.tablets[tid] = tb
    if tb.in_structure:
        lib.shelf.append(tid)
        world.dirty_struct.add(lib.id)
    a.bump("wrote")
    world.emit("tablet", f"{a.name} inscribed a tablet: {text}", 3, a.id, a.x, a.y, tablet=tid, knowledge=kk)
    s["note"] = f"Wrote down how to make {what}"
    return DONE


def _tablet_new(a: Agent, tb) -> bool:
    if tb.knowledge.startswith("belief:"):
        return not a.belief  # teachings only change a chit who believes nothing yet
    return tb.knowledge not in a.knows


def _do_read(world, a: Agent, step, s) -> str:
    src = s.get("src")
    if src is None and step.get("tablet") in world.tablets:  # a particular tablet, wherever it lies
        tb = world.tablets[step["tablet"]]
        if tb.in_structure is None:
            s["src"] = src = ("tab", tb.id)
        elif tb.in_structure in world.structures:
            s["src"] = src = ("lib", tb.in_structure)
            s["want"] = tb.id  # (that tablet, not the first unread one on its shelf, Codex #31)
    if src is None:
        best = None
        for lib in world.structures_near(a.x, a.y, 30, "library"):
            if lib.functional and any(_tablet_new(a, world.tablets[t]) for t in lib.shelf if t in world.tablets):
                best = ("lib", lib.id)
                break
        if not best:
            for tb in world.tablets.values():
                if tb.in_structure is None and max(abs(tb.x - a.x), abs(tb.y - a.y)) <= 25 and _tablet_new(a, tb):
                    best = ("tab", tb.id)
                    break
        if not best:
            return "there is nothing new to read nearby"
        s["src"] = src = best
    if src[0] == "lib":
        lib = world.structures.get(src[1])
        if not lib:
            return "the library is gone"
        mv = _goto_structure(world, a, s, lib)
        tabs = [world.tablets[t] for t in lib.shelf if t in world.tablets and (not s.get("want") or t == s["want"])]
    else:
        tb = world.tablets.get(src[1])
        if not tb:
            return "the tablet is gone"
        mv = move_toward(world, a, s, world.stand_tiles_for(tb.x, tb.y))
        tabs = [tb]
    if mv == "blocked":
        if src[0] == "tab":
            a.reflex_rest["unreach:" + src[1]] = world.tick + TICKS_PER_DAY
        return "couldn't get there"
    if mv != "arrived":
        return RUNNING
    a.activity = "reading"
    a.emote = "📜"
    a.emote_until = world.tick + 2
    if not _work(a, 1.0, 8.0):
        return RUNNING
    for tb in tabs:
        if tb.knowledge.startswith("belief:"):
            if not a.belief and world.convert(a, tb.knowledge.split(":", 1)[1], "read"):
                a.remember(world.tick, f"I read {tb.author_name}'s tablet: {tb.text}", 4, "belief")
                a.bump("read")
                s["note"] = f"Read a tablet of teachings: {tb.text}"
                return DONE
            continue
        if tb.knowledge not in a.knows:
            author = world.agents.get(tb.author) or world.dead.get(tb.author)
            world.learned(a, tb.knowledge, "read", None)
            a.remember(world.tick, f"I read {tb.author_name}'s tablet: {tb.text}", 4, "learn")
            if author and not author.alive:
                world.emit("legacy", f"{a.name} learned from a tablet left by the late {tb.author_name}", 4, a.id,
                           a.x, a.y, tablet=tb.id)
            a.bump("read")
            s["note"] = f"Read a tablet: {tb.text}"
            return DONE
    s["note"] = "Nothing new in these tablets"
    return DONE


def _do_study(world, a: Agent, step, s) -> str:
    from .research import do_study  # research at a library (sim/research.py); "study <a thing>" still inspects it

    return do_study(world, a, step, s)


def _do_inspect(world, a: Agent, step, s) -> str:
    ref = step.get("target") or step.get("what") or ""
    curious = a.traits.get("curiosity", 0.5)
    from . import artifacts as ART

    ak = world.norm_item(ref)
    if ART.is_artifact(ak) and (a.has(ak) or any(p.get(ak) for _, _, p in world.piles_near(a.x, a.y, 2))):
        a.activity = "studying"
        a.set_emote("🤔", world.tick, 4)
        if not _work(a, 1.0, 8.0):
            return RUNNING
        note = ART.on_inspect(world, a, ak, s)
        if note is None:
            s["note"] = f"Turned the {world.item_name(ak)} over and over. What is it for?"
            a.remember(world.tick, f"I studied a strange {world.item_name(ak)}: {', '.join(world.item(ak).props)}", 3, "wonder")
        else:
            s["note"] = note
            a.remember(world.tick, note, 4, "wonder")
        return DONE
    # own item?
    k = world.norm_item(ref)
    if k and a.has(k) and world.recipe(k) and not a.knows_recipe(k):
        a.activity = "studying"
        if not _work(a, 1.0, 8.0):
            return RUNNING
        if world.rng_for("agents").random() < 0.45 + 0.35 * curious:
            world.learned(a, f"recipe:{k}", "inspected")
            s["note"] = f"Studied my {world.item_name(k)} and worked out how it's made: {world.catalog.describe(world.recipe(k))}"
        else:
            s["note"] = f"Studied my {world.item_name(k)} but couldn't work out how it was made"
            a.remember(world.tick, s["note"], 2, "learn")
        return DONE
    other = _who(world, a, s, ref)
    if other and other.id != a.id:
        mv = _approach_agent(world, a, s, other, 2)
        if mv == "blocked" or s["ticks"] > 200:
            return f"couldn't get close to {other.name}"
        if mv != "arrived":
            return RUNNING
        a.activity = f"watching {other.name}"
        s["t"] = s.get("t", 0) + 1
        if s["t"] < 8:
            return RUNNING
        unknown = [x for x in other.inventory if world.recipe(x) and not a.knows_recipe(x)]
        if not unknown:
            s["note"] = f"Looked over {other.name}'s things; nothing I don't already understand"
            return DONE
        pick = world.rng_for("agents").choice(unknown)
        if world.rng_for("agents").random() < 0.35 + 0.35 * curious:
            world.learned(a, f"recipe:{pick}", "inspected", other)
            s["note"] = f"Studied {other.name}'s {world.item_name(pick)} and figured out how to make one"
        else:
            s["note"] = f"Studied {other.name}'s {world.item_name(pick)} but couldn't figure it out"
            a.remember(world.tick, s["note"], 2, "learn")
        return DONE
    st = _find_structure(world, a, ref or None, 30, lambda x: x.complete and not a.knows_design(x.design))
    if not st:
        return "found nothing new to study nearby"
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't get there"
    if mv != "arrived":
        return RUNNING
    a.activity = f"studying the {DESIGNS[st.design].name}"
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 10:
        return RUNNING
    d = DESIGNS[st.design]
    if a.knows_design(st.design):
        s["note"] = f"I already know how to build a {d.name}"
        return DONE
    if world.rng_for("agents").random() < 0.5 + 0.4 * curious:
        builder = world.agents.get(st.founder)
        world.learned(a, f"design:{st.design}", "inspected", builder)
        s["note"] = f"Studied the {d.name} and understood how to build one"
    else:
        s["note"] = f"Studied the {d.name} but couldn't work out its construction"
        a.remember(world.tick, s["note"], 2, "learn")
    return DONE


_DIRS = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0), "n": (0, -1), "s": (0, 1), "e": (1, 0),
    "w": (-1, 0), "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1),
    "ne": (1, -1), "nw": (-1, -1), "se": (1, 1), "sw": (-1, 1), "up": (0, -1), "down": (0, 1), "left": (-1, 0),
    "right": (1, 0),
}


_PLACE = re.compile(r"([a-z][a-z ]*?) at \((\d+),(\d+)\)")


def remembered_place(world, a: Agent, kind: str):
    """Where this chit remembers a resource, nearest first, or None: from its own exploring, or from what it heard
    someone say ("I found copper ore at (x,y)!"), which needs a world whose chits can talk."""
    name = world.item_name(kind)
    best = None
    for m in a.memories:
        if m.kind not in ("place", "heard"):
            continue
        for what, x, y in _PLACE.findall(m.text):
            what = what.strip()
            if what == name or what.endswith(" " + name):  # ("...I found copper ore at (x,y)")
                p = (int(x), int(y))
                if best is None or max(abs(p[0] - a.x), abs(p[1] - a.y)) < max(abs(best[0] - a.x), abs(best[1] - a.y)):
                    best = p
    return best


def _do_explore(world, a: Agent, step, s) -> str:
    if "goal" not in s:
        d = str(step.get("dir") or step.get("to") or step.get("what") or "").lower().replace(" ", "").replace("-", "")
        dx, dy = _DIRS.get(d, (0, 0))
        if (dx, dy) == (0, 0):
            ang = world.rng_for("agents").random() * 6.283
            dx, dy = math.cos(ang), math.sin(ang)
        dist = 16
        tx = int(max(1, min(world.w - 2, a.x + dx * dist)))
        ty = int(max(1, min(world.h - 2, a.y + dy * dist)))
        pos = world.ring_scan(tx, ty, 8, lambda x, y, i: world.passable(x, y))
        if not pos:
            return "that way is impassable"
        s["goal"] = pos
    mv = move_toward(world, a, s, {tuple(s["goal"])})
    if mv == "moving":
        a.activity = "exploring"
        return RUNNING
    # survey the surroundings and remember notable finds
    found = []
    for kind in ("clay", "ore", "iron_ore", "fish", "sand", "berries", "stone", "wood"):
        p = world.nearest_resource(a.x, a.y, kind, 8)
        if p:
            found.append(f"{world.item_name(kind)} at ({p[0]},{p[1]})")
    if found:
        a.remember(world.tick, "While exploring I found " + ", ".join(found[:5]), 3, "place")
    a.bump("explored")
    s["note"] = ("Explored and found " + ", ".join(found[:5])) if found else "Explored but found nothing notable"
    return DONE


PROSPECT_OUT = 40  # how far a prospector walks out
PROSPECT_LOOK = 12  # and how widely it looks about when it gets there (an explorer looks 8)
PROSPECT_KINDS = ("ore", "iron_ore", "sand", "clay")
PROSPECT_DAYS = 2  # one prospector out at a time in a village; the next may set out this long after


def _do_prospect(world, a: Agent, step, s) -> str:
    """{"do":"prospect","what":"ore|sand|clay","dir":"NE"} (or "to":"x,y"): walk far out to find what is scarce near
    home, look about widely, remember every find, and come home. Where chits can talk, it tells those around it."""
    if "phase" not in s:
        want = world.norm_item(step.get("what")) if step.get("what") else None
        if step.get("what") and want not in PROSPECT_KINDS:
            return "prospecting is for ore, sand or clay"
        to = _xy(step.get("to"))
        if to is not None:
            tx, ty = to
        else:
            d = str(step.get("dir") or "").lower().replace(" ", "").replace("-", "")
            dx, dy = _DIRS.get(d, (0, 0))
            if (dx, dy) == (0, 0):
                ang = world.rng_for("agents").random() * 6.283
                dx, dy = math.cos(ang), math.sin(ang)
            tx, ty = a.x + dx * PROSPECT_OUT, a.y + dy * PROSPECT_OUT
        tx, ty = int(max(1, min(world.w - 2, tx))), int(max(1, min(world.h - 2, ty)))
        pos = world.ring_scan(tx, ty, 10, lambda x, y, i: world.passable(x, y) and world.same_land_xy(a, x, y))
        if not pos:
            return "there's no way to walk out there"
        home = world.structures.get(a.home or "")
        hx, hy = (home.x, home.y) if home is not None else (a.x, a.y)
        back = world.ring_scan(hx, hy, 5, lambda x, y, i: world.passable(x, y) and world.same_land_xy(a, x, y)) or (a.x, a.y)
        s.update(phase="out", goal=list(pos), back=list(back), want=want, found=[])
        world.civic["prospector_until"] = world.tick + PROSPECT_DAYS * TICKS_PER_DAY
    if s["phase"] == "out":
        mv = move_toward(world, a, s, {tuple(s["goal"])})
        if mv == "moving":
            a.activity = "prospecting"
            return RUNNING
        found = []  # arrived, or as far as the way goes: look about
        for kind in sorted(PROSPECT_KINDS, key=lambda k: k != s["want"]):
            p = world.nearest_resource(a.x, a.y, kind, PROSPECT_LOOK)
            if p:
                found.append([kind, p[0], p[1]])
                a.remember(world.tick, f"While prospecting I found {world.item_name(kind)} at ({p[0]},{p[1]})", 4, "place")
        s["found"] = found
        a.bump("prospected")
        s["phase"] = "home"
        a.path = []
    if s["phase"] == "home":
        mv = move_toward(world, a, s, {tuple(s["back"])})
        if mv == "moving":
            a.activity = "coming home from prospecting"
            return RUNNING
        if not (s["found"] and world.flags.get("say")):
            s["note"] = ("Prospected and found " + ", ".join(world.item_name(k) for k, _, _ in s["found"])) if s["found"] \
                else "Prospected far and wide and found nothing"
            return DONE
        s["phase"] = "tell"
    text = "I found " + " and ".join(f"{world.item_name(k)} at ({x},{y})" for k, x, y in s["found"][:2]) + "!"
    ss = s.setdefault("say", {"ticks": 0})
    ss["ticks"] += 1
    if _do_say(world, a, {"do": "say", "to": "all", "text": text}, ss) == RUNNING:
        return RUNNING
    s["note"] = f"Came home from prospecting and told them: {text}"
    return DONE


def _xy(raw):
    m = re.match(r"\s*\(?\s*(\d+)\s*,\s*(\d+)\s*\)?\s*$", str(raw or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _do_go(world, a: Agent, step, s) -> str:
    if "goal" not in s:
        ref = step.get("to") or step.get("target") or step.get("what")
        pos = _resolve_place(world, a, ref)
        if pos is None:
            k = world.norm_item(ref)
            if k in GATHER_RULES:
                pos = world.nearest_resource(a.x, a.y, k, 30)
        if pos is None:
            d = str(ref or "").lower()
            if d in _DIRS:
                step["dir"] = d
                return _do_explore(world, a, step, s)
            return f"don't know where '{ref}' is"
        x, y = max(0, min(world.w - 1, pos[0])), max(0, min(world.h - 1, pos[1]))
        goals = world.stand_tiles_for(x, y) or {p for p in [world.ring_scan(x, y, 5, lambda xx, yy, i: world.passable(xx, yy))] if p}
        s["goal"] = list(goals)
    mv = move_toward(world, a, s, set(map(tuple, s["goal"])))
    if mv == "blocked":
        return "couldn't find a way there"
    if mv == "moving":
        return RUNNING
    s["note"] = f"Arrived at ({a.x},{a.y})"
    return DONE


def _do_refuel(world, a: Agent, step, s) -> str:
    st = _find_structure(world, a, step.get("target"), 30, lambda x: x.design == "campfire" and x.functional and x.fuel < 80)
    if not st:
        return "no campfire nearby needs fuel"
    if not a.has("wood"):
        return "I need wood to feed the fire"
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach the fire"
    if mv != "arrived":
        return RUNNING
    a.activity = "tending the fire"
    if not _work(a, 1.0, 3.0):
        return RUNNING
    n = min(a.inventory.get("wood", 0), max(1, int((100 - st.fuel) // 35) or 1), 3)
    a.remove("wood", n)
    was_out = st.fuel <= 0
    st.fuel = min(100.0, st.fuel + 35 * n)
    world.dirty_struct.add(st.id)
    a.bump("refueled")
    if was_out:
        world.emit("fire_lit", f"{a.name} rekindled a campfire", 1, a.id, *st.center(), structure=st.id)
    s["note"] = f"Fed {n} wood to the campfire (fuel {st.fuel:.0f}/100)"
    return DONE


def _do_plant(world, a: Agent, step, s) -> str:
    st = _find_structure(world, a, step.get("target"), 30, lambda x: x.design == "farm" and x.functional and not x.planted)
    if not st:
        return "no empty farm plot nearby"
    if not a.has("seeds", 2):
        pile = world.structures.get(s.get("seed_pile") or "") or _stockpile_with(world, a, ["seeds"], 30)
        if (not pile or s.get("seed_tries", 0) > 1) and world.nearest_resource(a.x, a.y, "seeds", 20):
            # no store of seeds: gather wild ones (models planted with empty hands 60 times a day)
            res = _do_gather(world, a, {"do": "gather", "what": "seeds", "qty": 2}, s.setdefault("seed_gather", {}))
            if res == RUNNING:
                return RUNNING
            s.pop("seed_gather", None)
            s.pop("goal_sig", None)
            a.path = []
            if res != DONE or not a.has("seeds", 2):
                return "I need 2 seeds to plant, and couldn't gather enough nearby"
            return RUNNING
        if not pile or s.get("seed_tries", 0) > 1:
            return "I need 2 seeds to plant (gather seeds, harvest a ripe farm, or take some from a stockpile)"
        s["seed_pile"] = pile.id
        mv = _goto_structure(world, a, s, pile)
        if mv == "blocked":
            return "couldn't reach the stockpile for seeds"
        if mv != "arrived":
            return RUNNING
        n = min(4, pile.storage.get("seeds", 0))
        got = a.add("seeds", n) if n else 0
        if got:
            pile.storage["seeds"] -= got
            if pile.storage["seeds"] <= 0:
                pile.storage.pop("seeds")
            world.dirty_struct.add(pile.id)
        s["seed_tries"] = s.get("seed_tries", 0) + 1
        s.pop("goal_sig", None)
        s.pop("seed_pile", None)
        a.path = []
        return RUNNING
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach the farm"
    if mv != "arrived":
        return RUNNING
    a.activity = "planting"
    if not _work(a, a.skill_speed("farming"), 6.0):
        return RUNNING
    a.remove("seeds", 2)
    st.planted, st.growth = True, 0.0
    kept_up(world, st, 20)
    world.dirty_struct.add(st.id)
    a.practice("farming", 1.0)
    a.bump("planted")
    s["note"] = "Planted the farm" + (" (but nothing grows in winter)" if world.season == "winter" else "")
    return DONE


def _do_harvest(world, a: Agent, step, s) -> str:
    if s.get("redirect"):
        return _redirect(world, a, s)
    st = _find_structure(world, a, step.get("target"), 35, lambda x: x.design == "farm" and x.functional and x.planted
                         and x.growth >= 1.0 and a.reflex_rest.get("unreach:" + x.id, 0) <= world.tick)
    if not st:
        # nothing ripe. World A's model harvested unripe or empty farms 483 times in 160 days, and each failure
        # threw the rest of its plan away while 32 farms lay empty: sow an empty one, or just say how it's growing
        farms = [x for x in world.structures_near(a.x, a.y, 35, "farm") if x.functional]
        if not farms:
            return "there's no farm nearby"
        empty = next((x for x in farms if not x.planted and world.same_land(a, x)), None)
        if empty is not None and (a.has("seeds", 2) or _stockpile_with(world, a, ["seeds"], 30)
                                  or world.nearest_resource(a.x, a.y, "seeds", 20)):
            s["redirect"] = {"do": "plant", "target": empty.id}
            s["note"] = f"Nothing was ripe, so I sowed the empty farm {empty.id}"
            return _redirect(world, a, s)
        best = max(farms, key=lambda x: x.growth if x.planted else -1)
        s["note"] = (f"Nothing is ripe yet: farm {best.id} is {int(best.growth * 100)}% grown" if best.planted
                     else f"Nothing to harvest: farm {best.id} is empty and I have no seeds to sow it")
        return DONE
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach the farm"
    if mv == "moving" and _long_way(a, s, st.x, st.y):
        a.reflex_rest["unreach:" + st.id] = world.tick + TICKS_PER_DAY
        return "that farm is a long way round on foot"
    if mv != "arrived":
        return RUNNING
    a.activity = "harvesting"
    if not _work(a, a.skill_speed("farming"), 8.0):
        return RUNNING
    # a world-specific farming invention: as much more grain as what it is made of gives (invent.FARMING_GRAIN)
    bonus = int(world.invention_effect(a, "farming")) if world.catalog.items else 0
    grain_yield = (12 if a.has("plough") else 6) + bonus
    g = a.add("grain", grain_yield)
    if a.has("plough"):
        _wear(world, a, "plough")
    sd = a.add("seeds", 2)
    left = {k: n for k, n in (("grain", grain_yield - g), ("seeds", 2 - sd)) if n > 0}
    for k, n in left.items():  # what doesn't fit in hand goes on the ground, not into thin air
        world.put_ground(a.x, a.y, k, n)
    st.planted, st.growth = False, 0.0
    kept_up(world, st, 20)
    # a harvester sows the plot again from the seeds it just gathered. Nobody chose to "plant": in both live
    # worlds farms went empty after one harvest (38 empty, 7 ripe) while 120-240 seeds sat in the stockpiles
    resown = a.has("seeds", 2)
    if resown:
        a.remove("seeds", 2)
        st.planted = True
    world.dirty_struct.add(st.id)
    a.practice("farming", 1.5)
    a.bump("harvested")
    world.notice_items(a)
    if a.stats.get("harvested") == 1:
        world.emit("harvest", f"{a.name} brought in a harvest of grain", 2, a.id, *st.center())
    s["note"] = f"Harvested {g} grain" + (" and sowed the plot again" if resown else
                                          f" and {sd} seeds (the plot needs replanting)") + (
        " and left " + ", ".join(f"{n} {world.item_name(k)}" for k, n in left.items()) + " on the ground" if left else "")
    return DONE


def _station_step(world, a: Agent, s, station: str) -> Optional[str]:
    """Walk to the nearest station of a kind: None on arrival, else RUNNING or why not."""
    mv = _gather_station(world, a, s, station)
    if mv == "none":
        return f"there's no {station} nearby"
    if mv == "blocked":
        return f"couldn't reach the {station}"
    return None if mv == "arrived" else RUNNING


def _mend_tool(world, a: Agent, step, s, tool: str) -> str:
    """A worn metal tool, re-hafted at a workshop with one piece of wood: as good as new, its metal kept."""
    name = world.item_name(tool)
    if not a.has(tool):
        return f"I have no {name} to mend"
    if a.tool_wear.get(tool, 0) <= 0:  # (an invented metal tool is mended the same way, F34)
        return f"my {name} doesn't need mending"
    if not a.has("wood"):
        return f"I need a piece of wood for a new haft for my {name}"
    why = _station_step(world, a, s, MEND_AT)
    if why is not None:
        return why
    a.activity = f"mending a {name}"
    a.emote = "🔧"
    a.emote_until = world.tick + 2
    if not _work(a, a.skill_speed("crafting"), 6.0):
        return RUNNING
    a.remove("wood", 1)
    a.tool_wear[tool] = 0
    a.practice("crafting", 0.5)
    a.bump("tools_mended")
    s["note"] = f"Mended my {name}: as good as new"
    return DONE


def _do_smelt(world, a: Agent, step, s) -> str:
    """Melt a metal tool back into its metal at a furnace (a copper pick nobody needs once there's an iron one)."""
    tool = world.norm_item(step.get("what"))
    metal = metal_of(world, tool)
    if metal is None:
        return f"only metal tools can be smelted down ({step.get('what')} isn't one)"
    name = world.item_name(tool)
    if not a.has(tool):
        return f"I have no {name} to smelt"
    why = _station_step(world, a, s, SMELT_AT)
    if why is not None:
        return why
    a.activity = f"smelting a {name}"
    a.emote = "🔥"
    a.emote_until = world.tick + 2
    if not _work(a, a.skill_speed("crafting"), 8.0):
        return RUNNING
    a.remove(tool, 1)
    if not a.has(tool):
        a.tool_wear.pop(tool, None)
    a.add(metal, 1)
    a.bump("tools_smelted")
    world.emit("smelted_down", f"{a.name} smelted a {name} back into {world.item_name(metal)}", 1, a.id, a.x, a.y,
               item=tool)
    s["note"] = f"Smelted my {name} back into {world.item_name(metal)}"
    return DONE


def _do_repair(world, a: Agent, step, s) -> str:
    tool = world.norm_item(step.get("what")) if step.get("what") else None
    if metal_of(world, tool):  # a tool, not a building
        return _mend_tool(world, a, step, s, tool)
    st = _find_structure(world, a, step.get("target"), 30, lambda x: x.complete and x.durability < 70)
    if not st:
        return "nothing nearby needs repair"
    d = DESIGNS[st.design]
    mat = d.materials[0][0]
    if not a.has(mat):
        return f"I need {world.item_name(mat)} to repair the {d.name}"
    mv = _goto_structure(world, a, s, st)
    if mv == "blocked":
        return "couldn't reach it"
    if mv != "arrived":
        return RUNNING
    a.activity = f"repairing the {d.name}"
    a.emote = "🔧"
    a.emote_until = world.tick + 2
    if not _work(a, a.skill_speed("building"), 6.0):
        return RUNNING
    a.remove(mat, 1)
    was_ruin = st.durability <= 0
    st.durability = min(100.0, st.durability + 45)
    st.ruined_at = -1
    world.dirty_struct.add(st.id)
    a.bump("repaired")
    a.practice("building", 0.8)
    if was_ruin:
        world.emit("restored", f"{a.name} restored a ruined {d.name}", 3, a.id, *st.center(), structure=st.id)
    s["note"] = f"Repaired the {d.name} (condition {st.durability:.0f}%)"
    return DONE


def _do_rest(world, a: Agent, step, s) -> str:
    a.activity = "resting"
    a.energy = min(100.0, a.energy + 0.25)
    if s["ticks"] >= _qty(step, 20, 5, 120):
        s["note"] = "Rested a while"
        return DONE
    return RUNNING


def _do_wander(world, a: Agent, step, s) -> str:
    if "goal" not in s:
        pos = world.ring_scan(a.x + world.rng_for("agents").randint(-6, 6), a.y + world.rng_for("agents").randint(-6, 6), 4,
                              lambda x, y, i: world.passable(x, y))
        if not pos:
            return DONE
        s["goal"] = pos
    mv = move_toward(world, a, s, {tuple(s["goal"])})
    if mv == "moving" and s["ticks"] < 60:
        a.activity = "wandering"
        return RUNNING
    return DONE


def _do_drop(world, a: Agent, step, s) -> str:
    k = world.norm_item(step.get("what"))
    if not k or not a.has(k):
        return f"I'm not carrying any {step.get('what')}"
    n = a.remove(k, _qty(step, a.inventory[k], 1, 99))
    if n:
        world.put_ground(a.x, a.y, k, n)  # it lies there for a while (T28)
    s["note"] = f"Dropped {n} {world.item_name(k)}"
    return DONE


def _chase(world, a: Agent, s, animal) -> str:
    """Walk up to an animal (it may move). Returns 'arrived', 'moving' or 'blocked'."""
    if max(abs(a.x - animal["x"]), abs(a.y - animal["y"])) <= 1:
        return "arrived"
    goal = (animal["x"], animal["y"])
    if s.get("chase_goal") != goal:
        s["chase_goal"] = goal
        s.pop("path", None)
        a.path = []
    goals = {goal} if world.passable(*goal) else set(world.stand_tiles_for(*goal))
    return move_toward(world, a, s, goals)


def _do_hunt(world, a: Agent, step, s) -> str:
    """Hunt a deer (or drive off a wolf) with a spear or a weapon (T31)."""
    from . import animals as AN

    kind = str(step.get("what") or "deer").strip().lower().rstrip("s") or "deer"
    kind = {"wolve": "wolf", "stag": "deer", "doe": "deer"}.get(kind, kind)
    if kind not in ("deer", "wolf"):
        return "you can hunt deer (or wolves)"
    tool = a.best_tool("weapon") or a.best_tool("spear")
    if not tool:
        return "hunting needs a spear (or a weapon)"
    prey = world.animals.get(s.get("prey", "")) or AN.nearest(world, a.x, a.y, kind, 20)
    if not prey:
        return f"there's no {kind} within reach"
    s["prey"] = prey["id"]
    mv = _chase(world, a, s, prey)
    if mv == "blocked" or s.get("ticks", 0) > 300:
        return f"the {kind} got away"
    if mv != "arrived":
        return RUNNING
    a.activity = "hunting"
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 6:
        return RUNNING
    s["t"] = 0
    s["tries"] = s.get("tries", 0) + 1
    power = world.item(tool).tool_power if world.item(tool) else 1.0
    if AN._rng(world).random() < 0.35 + 0.15 * power:
        world.animals.pop(prey["id"], None)
        if kind == "deer":
            got = a.add("meat", 3)
            if got < 3:
                world.put_ground(a.x, a.y, "meat", 3 - got)
            world.notice_items(a)
        a.bump(f"hunted_{kind}")
        a.practice("gathering", 0.5)
        what = "a deer" if kind == "deer" else "a wolf"
        world.emit("hunt", f"{a.name} hunted {what}" + (" and brought home meat" if kind == "deer" else " and drove the danger away"),
                   3 if kind == "wolf" else 2, a.id, a.x, a.y, prey=kind)
        s["note"] = f"Hunted {what}" + (": 3 meat" if kind == "deer" else "")
        return DONE
    if s["tries"] >= 8:
        return f"the {kind} kept getting away"
    return RUNNING


def _do_tame(world, a: Agent, step, s) -> str:
    """Coax a wild sheep into a pen with grain or berries (T31)."""
    from . import animals as AN

    pen = _find_structure(world, a, step.get("target"), 12, lambda x: x.design == "pen" and x.functional)
    if not pen:
        return "taming needs a pen nearby to keep the animal in"
    bait = "grain" if a.has("grain") else "berries" if a.has("berries") else None
    if not bait:
        return "I need grain or berries to tempt an animal"
    sheep = world.animals.get(s.get("sheep", "")) or AN.nearest(world, a.x, a.y, "sheep", 15)
    if not sheep or sheep["tame"]:
        return "there's no wild sheep nearby"
    s["sheep"] = sheep["id"]
    mv = _chase(world, a, s, sheep)
    if mv == "blocked" or s.get("ticks", 0) > 300:
        return "the sheep wandered off"
    if mv != "arrived":
        return RUNNING
    a.activity = "taming"
    s["t"] = s.get("t", 0) + 1
    if s["t"] < 4:
        return RUNNING
    s["t"] = 0
    s["tries"] = s.get("tries", 0) + 1
    a.remove(bait, 1)
    if AN._rng(world).random() < 0.5:
        first = not any(x["tame"] for x in world.animals.values())
        sheep["tame"], sheep["pen"] = True, pen.id
        sheep["x"], sheep["y"] = pen.x, pen.y
        a.bump("tamed")
        if first:
            world.emit("tamed", f"{a.name} tamed the first sheep", 4, a.id, a.x, a.y)
        else:
            world.emit("tamed", f"{a.name} tamed a sheep", 3, a.id, a.x, a.y)
        s["note"] = f"Tamed a sheep and led it into pen {pen.id}"
        return DONE
    if s["tries"] >= 4:
        return "the sheep wouldn't come"
    return RUNNING


def _do_sail(world, a: Agent, step, s) -> str:
    """Take a boat out to sea (T30). With contact off there is nothing out there. A trader from over the sea sails
    home in the boat it came in (it is drawn up on the shore: nobody else can take it)."""
    if getattr(world, "is_fork", False):
        return "the sea is closed: this is a what-if"
    if a.origin and a.voyage_intent == "trade" and a.stats.get("boat_abroad"):  # (home, even after a fair has ended)
        a.stats["boat_abroad"] = a.stats["traded_trip"] = 0
        a.voyage_intent = "home"
        a.activity = "sailing home"
        world.depart(a)
        return DONE
    boat = _find_structure(world, a, step.get("target"), 20, lambda x: x.design == "boat" and x.functional)
    if not boat:
        return "there's no boat nearby (build one on the shore first)"
    mv = _goto_structure(world, a, s, boat)
    if mv == "blocked":
        return "couldn't reach the boat"
    if mv != "arrived":
        return RUNNING
    if not getattr(world, "contact", False):
        a.remember(world.tick, "I rowed out, but beyond the horizon there was only more sea", 3, "voyage")
        return "Beyond the horizon there is only more sea"
    a.activity = "sailing"
    intent = str(step.get("intent") or "explore").strip().lower()
    a.voyage_intent = intent if intent in ("raid", "trade", "explore", "settle") else "explore"
    if a.voyage_intent == "trade":
        a.stats["boat_abroad"] = 1  # the boat waits on the far shore to bring the trader home
        from ..brain import voyages

        voyages.sent(world)
    world.structures.pop(boat.id, None)
    world.removed_struct.add(boat.id)
    for cx, cy in boat.cells():
        world.occupied.pop(cy * world.w + cx, None)
    world.depart(a)
    return DONE


def _do_pickup(world, a: Agent, step, s) -> str:
    """Pick things up from the ground here, or from the nearest pile within 20 tiles that has them (T28)."""
    from . import artifacts as ART

    want = world.norm_item(step.get("what")) if step.get("what") else None
    if step.get("what") and not want:
        return f"'{step.get('what')}' isn't an item"
    tgt = s.get("pile")
    if tgt is None:
        for px, py, pile in world.piles_near(a.x, a.y, 20):
            if want is None or pile.get(want, 0) > 0:
                tgt = s["pile"] = (px, py)
                break
        if tgt is None:
            return f"there's no {world.item_name(want) if want else 'thing'} lying around nearby"
    tile = f"{tgt[0]},{tgt[1]}"
    goals = {tuple(tgt)} if world.passable(*tgt) else set(world.stand_tiles_for(*tgt))
    if max(abs(a.x - tgt[0]), abs(a.y - tgt[1])) > (0 if world.passable(*tgt) else 1):
        mv = move_toward(world, a, s, goals)
        if mv == "blocked":
            return "couldn't get there"
        if mv == "moving" and _long_way(a, s, *tgt):
            a.reflex_rest[f"unreach:{tgt[0]},{tgt[1]}"] = world.tick + TICKS_PER_DAY
            return "that's a long way round on foot"
        if mv != "arrived":
            return RUNNING
    pile = world.ground.get(tile, {})
    keys = [want] if want else [k for k in pile if k != "_t" and pile[k] > 0]
    notes = []
    for k in keys:
        n = pile.get(k, 0)
        if n <= 0:
            continue
        if ART.is_artifact(k):
            res = ART.on_pickup(world, a, k, tile)
            if res and res.startswith("!"):
                if want:
                    return res[1:]
                continue
            if res:
                pile[k] -= 1
                notes.append(res)
                world.emit("artifact", f"{a.name} picked up the {world.item_name(k)}. {res}", 4, a.id, a.x, a.y, item=k)
                continue
        if want == k and k in FOODS and a.free_space() < world.item(k).weight:
            # picking up food it came for with full hands failed 384 times in a row for one chit: make room
            _drop_for_room(world, a, world.item(k).weight)
        got = a.add(k, n)
        pile[k] = n - got
        if got:
            notes.append(f"{got} {world.item_name(k)}")
    for k in [k for k in pile if k != "_t" and pile[k] <= 0]:
        pile.pop(k)
    if not any(k != "_t" for k in pile):
        world.ground.pop(tile, None)
    world.notice_items(a)
    if not notes:
        return "my hands are full" if keys else "there's nothing here"
    s["note"] = "Picked up " + "; ".join(notes)
    return DONE
