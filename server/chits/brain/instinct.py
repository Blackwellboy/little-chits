"""Instinct: a hand-written utility planner.

It keeps chits alive when no model is attached (or while a model is thinking or
down) and gives a baseline to compare models against. It knows nothing the chit
doesn't know. It uses the same verbs and the same world laws as a model brain,
and it discovers by blind experimentation guided only by the world's feedback.
"""

from __future__ import annotations

import itertools
import zlib
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from ..sim.actions import _farm_ready, _stockpile_with  # (what the eat and harvest steps use)
from ..sim.actions import (FOODS, era_path, KEEP_STOCK, STATION_NEAR, STATION_REACH, STOCKPILE_CAP, WORK_RADIUS, _tablet_new,
                           food_items, mend_material, plan_bill, remembered_place, stockpile_room, village_stores)
from ..sim.agent import Agent
from ..sim import items as IT
from ..sim.items import BASE, DESIGNS, HOME_STORES, ITEMS, RECIPES, STATIONS, item_name
from ..sim.buildings import HOME_CAP, HOMES, upgrade_spot  # beyond its cap a family home is crowded
from . import builder as BI  # bigger homes, bridges and the useful buildings
from . import outposts as OP
from . import voyages as VOY
from . import prospect as PR
from . import pioneers as PIO
from . import ground as GR
from . import surplus as SUR  # how much of a good is enough, and what to do with more (issue #7)
from . import civic
from . import inventor as INVENTOR  # the one "invent" option of a chit that chooses (never for an instinct-only chit)

RAW = ("wood", "stone", "fiber", "berries", "clay", "sand")
# the most items any recipe takes: the steam engine's 2 steel + 2 gears + a pot is 5, and a bag that stopped growing at 4
# could never become it (issue #2)
MAX_BAG = max(sum(q for _, q in r.inputs) for r in RECIPES.values())
# the world's feedback on a failed experiment, and the station it points to (sim.actions._experiment_hint)
STATION_CUES = (("It needed far more heat than a campfire gives", "kiln"), ("Only a truly roaring fire", "furnace"),
                ("a proper workbench might help", "workshop"), ("a blast of heat beyond any furnace", "forge"),
                ("This needs machines", "factory"), ("It felt like it needed heat", "fire"))


# a hungry chit plans only for the stores and farms its eat and harvest steps can reach (False: the old lookups, which
# chose a store the step had found a long way round, every tick; tests/identity_runner.py turns it off)
HUNGER_REACH = True

def _stock_near(world, a: Agent, item: str, radius: int = 25) -> int:
    """How much of an item the stockpiles around this chit hold."""
    return sum(p.storage.get(item, 0) for p in world.structures_near(a.x, a.y, radius, "stockpile") if p.functional and _reachable(world, a, p))


CARRIERS = ("wagon", "cart", "sled")  # best first; the basket is made with the first tools


def _better_carrier(world, a: Agent) -> Optional[tuple]:
    """Make (or fetch from the stores) the best carrier this chit knows, if it beats the best it holds."""
    held = max((a._item(k).carry_bonus - a._item(k).weight for k, n in a.inventory.items()
                if n > 0 and a._item(k) and a._item(k).carry_bonus), default=0)
    for k in CARRIERS:
        it = world.item(k)
        if not a.knows_recipe(k) or a.has(k) or it.carry_bonus - it.weight <= held:
            continue
        if _stock_near(world, a, k) > 0:
            return (2.5, {"goal": f"fetch a {item_name(k)}", "thought": f"There's a {item_name(k)} in the stores. I could carry more.",
                          "steps": [{"do": "take", "what": k, "qty": 1}]})
        steps = _craft_steps(a, k, world=world)
        if steps and len(steps) <= 5:
            return (2.0, {"goal": f"make a {item_name(k)}", "thought": f"With a {item_name(k)} I could carry far more.",
                          "steps": steps})
    return None


HAUL_TRY = 0.3  # how often a chit who could try for the wagon does, when it experiments
LOST_TABLET_TRIP = 80  # how far a chit will walk to read a loose tablet of what nobody alive still knows


def _fuel_steps(world, a: Agent) -> List[Dict[str, Any]]:
    """Two wood for a fire: in hand, from the stores, or (only with none stored nearby) chopped. Fires were fed with
    freshly chopped wood while 7,600 lay in World A's stores: 88 trips in two days."""
    if a.has("wood", 2) or (IT.ITEM_USES and a.has("charcoal")):  # (charcoal in hand feeds a fire too, and for longer: no trip for wood)
        return []
    if _stock_near(world, a, "wood") >= 2:
        return [{"do": "take", "what": "wood", "qty": 2 - a.inventory.get("wood", 0)}]
    return [{"do": "gather", "what": "wood", "qty": 2}]


def _keeper_counts(world) -> Dict[str, int]:
    """How many living chits know each thing, counted again whenever anyone learns, forgets or dies (a count kept
    for the whole tick ranked a recipe taught to five watchers mid-tick as still rare, Codex #26)."""
    stamp = (world.tick, len(world.agents), sum(len(o.knows) for o in world.agents.values()))
    c = getattr(world, "_keepers_n", None)
    if c is None or c[0] != stamp:
        n: Dict[str, int] = {}
        for o in world.agents.values():
            for k in o.knows:
                n[k] = n.get(k, 0) + 1
        c = (stamp, n)
        world._keepers_n = c
    return c[1]


def _reachable(world, a: Agent, s) -> bool:
    """False for a site this chit recently failed to reach (it may be across water)."""
    return a.reflex_rest.get("unreach:" + s.id, 0) <= world.tick and world.same_land(a, s)


FURNACE_ORE_TARGET = KEEP_STOCK["ore"] + 4  # reserve + two iron batches: 0-5 ore made the live furnaces choose charcoal


def tool_care_plan(world, a: Agent) -> Optional[Dict[str, Any]]:
    """Look after metal tools (issue #5): mend one half worn at a workshop with a piece of wood, or smelt one that a
    better tool of the same kind has replaced back into its metal at a furnace. Worn tools only ever vanished, and in
    long runs the iron went into replacement picks instead of steel."""
    from ..sim.actions import METAL_OF, tool_wear_limit

    if a.is_child(world.tick):
        return None
    mine = sorted(t for t in a.inventory if t in METAL_OF and a.inventory[t] > 0)

    def better(tool):
        it = a._item(tool)
        return [t for t in a.inventory if t != tool and a.inventory[t] > 0 and it.tool and a._item(t)
                and a._item(t).tool == it.tool and a._item(t).tool_power > it.tool_power]

    for tool in mine:
        if better(tool):
            continue  # (smelted below, not mended first: a wood and a workshop visit spent on a pick about to melt)
        worn = a.tool_wear.get(tool, 0) >= tool_wear_limit(tool) // 2
        wood = a.has("wood") or any(p.storage.get("wood", 0) > 0 for p in village_stores(world, a.x, a.y, 25, a))
        if worn and wood and world.nearest_station(a.x, a.y, "workshop", STATION_NEAR):
            steps = [] if a.has("wood") else [{"do": "take", "what": "wood", "qty": 1}]
            return {"goal": f"mend my {item_name(tool)}", "thought": f"My {item_name(tool)} is getting worn. A new haft will save the metal.",
                    "steps": steps + [{"do": "repair", "what": tool}]}
    for tool in mine:
        best = better(tool)
        if best and world.nearest_station(a.x, a.y, "furnace", STATION_NEAR):
            metal = METAL_OF[tool]
            return {"goal": f"smelt down my old {item_name(tool)}",
                    "thought": f"I don't need the {item_name(tool)} now I have a {item_name(best[0])}. The {item_name(metal)} is worth more.",
                    "steps": [{"do": "smelt", "what": tool}]}
    return None


def feed_furnace_plan(world, a: Agent) -> Optional[Dict[str, Any]]:
    """Carry ore from a full mine to a store that a furnace can actually draw from.

    The long live Iron-Age world had six mines holding 80-90 ore while furnace-local stores held 0-5. Production
    therefore offered charcoal ~30x more often than iron. This is a directed supply trip, not magic transfer: the
    chit must know iron/copper, carry a pick, walk to the mine, dig the ore, then walk it to a real village store.
    """
    if not a.best_tool("pick") or not (a.knows_recipe("iron") or a.knows_recipe("copper")):
        return None
    # the ore the furnace needs next (issue #4): iron ore while iron is the way forward, else copper ore. When the
    # stores by the furnace already hold enough of that one, the other: once iron was on the path, copper ore was
    # never carried again, though wire and lanterns need copper (Codex, #46)
    iron_first = a.knows_recipe("iron") and "iron" in era_path(world)
    for kind in (("iron_ore", "ore") if iron_first else ("ore", "iron_ore")):
        plan = _feed_furnace(world, a, kind)
        if plan is not None:
            return plan
    return None


def _feed_furnace(world, a: Agent, kind: str) -> Optional[Dict[str, Any]]:
    # A supply plan may use only infrastructure this chit can plausibly know. A nearby furnace is visible in the
    # same local scene a model would receive; a farther mine is eligible only when the chit remembers/heard its ore
    # location. Never scan the whole landmass for private infrastructure.
    local_sight = 14  # prompt.SIGHT (10) + the four-tile structure margin
    furnaces = [st for st in world.structures_near(a.x, a.y, local_sight, "furnace")
                if st.functional and _reachable(world, a, st)]
    if not furnaces:
        return None
    mines = [st for st in world.structures_near(a.x, a.y, local_sight, "mine")
             if st.functional and st.storage.get(kind, 0) > 0 and _reachable(world, a, st)]
    if not mines:
        seen = remembered_place(world, a, kind)
        if seen is not None:
            mines = [st for st in world.structures_near(seen[0], seen[1], 6, "mine")
                     if st.functional and st.storage.get(kind, 0) > 0 and _reachable(world, a, st)]
    if not mines:
        return None
    for furnace in sorted(furnaces, key=lambda st: st.dist(a.x, a.y)):
        piles = village_stores(world, furnace.x, furnace.y, WORK_RADIUS, a)
        ore_here = sum(p.storage.get(kind, 0) for p in piles)
        if ore_here >= FURNACE_ORE_TARGET:
            continue
        need = FURNACE_ORE_TARGET - ore_here
        destinations = [p for p in piles if stockpile_room(p, kind) > 0]
        if not destinations:
            continue
        mine = min(mines, key=lambda st: st.dist(a.x, a.y))
        dest = max(destinations, key=lambda p: (stockpile_room(p, kind), -p.dist(furnace.x, furnace.y)))
        ore = world.item(kind)
        weight = max(1, int(getattr(ore, "weight", 1)))
        carry_units = max(0, int(a.free_space()) // weight)
        qty = min(8, need, mine.storage.get(kind, 0), stockpile_room(dest, kind), carry_units)
        if qty < 1:
            continue
        return {"goal": "feed the furnace with ore",
                "thought": "The mine has ore, but the furnace stores are running short. I'll carry a load there.",
                "steps": [{"do": "go", "to": mine.id},
                          {"do": "gather", "what": kind, "qty": qty},
                          {"do": "store", "what": kind, "qty": qty, "target": dest.id}]}
    return None

LINES_FOUND = [
    "I found {what} over at ({x},{y})!",
    "There's {what} near ({x},{y}) if anyone needs it.",
]
LINES_BUILD = [
    "I'm building a {d} — could use {need}.",
    "Help me with the {d}? It needs {need}.",
]


TOOL_FOR = {"pick": "stone_pick", "spear": "spear"}  # the simplest tool of each kind a gather rule requires


def tools_first(world, a: Agent, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A model's plan that gathers ore (or fish) with no pick (or spear) in hand: get or make one first, if the chit can."""
    from ..sim.items import GATHER_RULES

    for i, s in enumerate(steps):
        if not isinstance(s, dict) or s.get("do") != "gather":
            continue
        rule = GATHER_RULES.get(world.norm_item(s.get("what"))) or {}
        if rule.get("requires") and not a.best_tool(rule["tool"]) and not any(
                isinstance(p, dict) and world.norm_item(p.get("what")) == TOOL_FOR[rule["tool"]] for p in steps[:i]):
            pre = _supply_steps(a, {TOOL_FOR[rule["tool"]]: 1}, world) or []
            return steps[:i] + pre + steps[i:]
    return steps


def _supply_steps(a: Agent, need: Dict[str, int], world=None, depth: int = 0, reach=None) -> Optional[List[Dict[str, Any]]]:
    """Plan only known recipes, accounting for shared inputs and recipe output yields. `world` also draws on the
    stores and the ground; `reach` (a world) only checks that each recipe's station is in reach."""
    near = world if world is not None else reach
    from ..sim.items import GATHER_RULES, GATHERABLE

    held = dict(a.inventory)
    stock: Dict[str, int] = {}
    if world is not None:
        for p in world.structures_near(a.x, a.y, 25, "stockpile"):
            if p.functional and _reachable(world, a, p):
                for k, n in p.storage.items():
                    stock[k] = stock.get(k, 0) + n
    elif reach is not None:
        # a thing made by hand draws nothing from the stores, except what they hold at its ceiling (issue #7): iron
        # for a site was made with freshly burned charcoal, two for each wood, and one village stored 1,490 of it
        stock = SUR.plenty(reach, a)
    loose: Dict[str, int] = {}
    if world is not None:
        from .ground import ground_stock

        loose = ground_stock(world, a)  # dropped loads lying about (570 charcoal in one pile, unused)
    steps: List[Dict[str, Any]] = []

    def ensure(k, n, chain):
        missing = n - held.get(k, 0)
        if missing <= 0:
            return True
        take = min(missing, stock.get(k, 0))
        if take:
            steps.append({"do": "take", "what": k, "qty": take})
            stock[k] -= take
            held[k] = held.get(k, 0) + take
            missing -= take
        if missing <= 0:
            return True
        take = min(missing, loose.get(k, 0))
        if take:
            steps.append({"do": "pickup", "what": k})
            loose[k] -= take
            held[k] = held.get(k, 0) + take
            missing -= take
        if missing <= 0:
            return True
        recipe = _rec(a, k)
        if recipe and a.knows_recipe(k):
            if k in chain or len(chain) + depth > 12:
                return False
            if recipe.station and near is not None and not near.nearest_station(a.x, a.y, recipe.station, STATION_REACH):
                # an input made at a station out of reach can't be made: the live World B crafted charcoal for its
                # copper with no kiln nearby 590 times in 8 minutes (the loop detector's first live catch)
                return False
            batches = (missing + recipe.qty - 1) // recipe.qty
            for item, count in recipe.inputs:
                if not ensure(item, count * batches, chain + (k,)):
                    return False
                # Reserve each input before preparing the next one.
                held[item] -= count * batches
            left = batches
            while left:
                count = min(left, 10)
                steps.append({"do": "craft", "what": k, "qty": count})
                left -= count
            held[k] = held.get(k, 0) + batches * recipe.qty
        elif k in GATHERABLE:
            rule = GATHER_RULES[k]
            if rule["requires"] and not a.best_tool(rule["tool"]):
                # a pick before the ore (the live worlds failed "I need a pick to get copper ore" 54 times in a week,
                # 43 of them by chits that knew how to make one); a chit that can't get one plans as before
                mark = (len(steps), dict(held), dict(stock), dict(loose))
                if not ensure(TOOL_FOR[rule["tool"]], 1, chain + (k,)):
                    del steps[mark[0]:]
                    held.clear(), held.update(mark[1]), stock.clear(), stock.update(mark[2])
                    loose.clear(), loose.update(mark[3])
            steps.append({"do": "gather", "what": k, "qty": missing})
            held[k] = held.get(k, 0) + missing
        else:
            return False
        return True

    # Reserve requested final inputs so another ingredient cannot consume them.
    for k, n in need.items():
        if not ensure(k, n, ()):
            return None
        held[k] -= n
    return steps


def _need_steps(a: Agent, need: Dict[str, int], world=None) -> List[Dict[str, Any]]:
    return _supply_steps(a, need, world) or []


JOB_WORDS = {
    "farmer": ("farm", "harvest", "plant", "bread"),
    "builder": ("build", "help with", "mend", "restore", "road"),
    "crafter": ("make", "craft", "bake", "work at"),
    "gatherer": ("collect", "store food"),
    "fisher": ("fish",),
    "scholar": ("experiment", "read", "record", "study", "figure out"),
    "explorer": ("explore",),
}


def _rec(a: Agent, key: str):
    return (a.catalog or BASE).recipe(key)


def _craft_steps(a: Agent, key: str, qty: int = 1, depth: int = 0, world=None) -> List[Dict[str, Any]]:
    if not _rec(a, key) or not a.knows_recipe(key):
        return []
    return _supply_steps(a, {key: a.inventory.get(key, 0) + qty}, depth=depth, reach=world) or []


def _fetch_steps(world, a: Agent, key: str, n: int, room: Optional[float] = None) -> List[Dict[str, Any]]:
    """n of a good for a job, with a reading of what the village holds (issue #7): from the stores in the measure
    they are full of it, the rest gathered (or made by hand, for a thing this chit knows how to make). Sites were
    supplied with freshly cut wood and freshly burned charcoal while hundreds of each lay in the stores, and what the
    site didn't take was stored too. `room`: the weight its hands will still hold when it gets to the stores (a take
    of more than they hold fails, and the rest of the plan with it; gathering just stops at full hands)."""
    fresh, stored = SUR.split(world, a, key, n) if world is not None else (n, 0)
    if room is not None and stored:
        stored = min(stored, int(max(0.0, room) // max(1, world.item(key).weight)))
    steps: List[Dict[str, Any]] = [{"do": "take", "what": key, "qty": stored}] if stored else []
    if fresh and key in RECIPES:
        steps += _craft_steps(a, key, fresh, world=world)
    elif fresh:
        steps.append({"do": "gather", "what": key, "qty": fresh})
    return steps


WORK_NEAR = STATION_NEAR  # instinct offers a spare shift at a station this close, by choice


class Instinct:
    id = "instinct"
    label = "Instinct (no model)"

    def plan(self, world, a: Agent) -> Dict[str, Any]:
        self._world = world  # for _exp_plan's stockpile lookups
        rng = random.Random(world.tick * 7919 + zlib.crc32(a.id.encode()))
        for fn in (self._survive, self._declutter, self._shelter, self._maintain, self._communal, self._progress):
            for _ in range(3):  # a plan that needs something there's none of nearby is drawn again (World B tried
                out = fn(world, a, rng)  # "gather clay" 51 times a day with no clay in reach)
                if not (out and any(s and s.get("do") == "gather" and not s.get("_far") and a.reflex_rest.get(
                        f"scarce:{world.norm_item(s.get('what'))}", 0) > world.tick for s in out.get("steps", []))):
                    break
                out = None
            if out:
                out.setdefault("steps", [])
                out["steps"] = self._make_room(world, a, [s for s in out["steps"] if s])[:6]
                if out["steps"]:
                    if fn is not self._survive:
                        out["steps"] = (self._answer(world, a, out.get("goal", "")) + out["steps"])[:6]
                    return out
        return {"goal": "look around", "thought": "Nothing pressing. I'll wander.", "steps": [{"do": "wander"}]}

    @staticmethod
    def _answer(world, a: Agent, goal: str) -> List[Dict[str, Any]]:
        """Someone spoke to this chit: answer them, and hand over what they asked for if it has plenty. Instinct
        never answered, and it makes most of a slow model's moves (World B: addressed 3, answered 0)."""
        heard = a.spoken_to or {}
        other = world.agents.get(heard.get("id", ""))
        if not other or not world.flags.get("say") or world.tick - heard.get("tick", 0) > 120:
            return []
        text = str(heard.get("text", "")).lower()
        steps: List[Dict[str, Any]] = []
        for k, n in sorted(a.inventory.items()):
            it = world.item(k)
            words = {k.replace("_", " "), it.name.lower()} if it else set()
            if n >= 3 and it and not it.tool and any(re.search(rf"\b{re.escape(w)}s?\b", text) for w in words):
                steps.append({"do": "give", "to": other.name, "what": k, "qty": min(2, n - 1)})
                break
        # every answer was "I hear you, X. I'm off to sleep." (hundreds of times): vary it, with a little character
        g = goal or "work"
        n = other.name
        lines = (
            (f"Here, {n}, take some.", f"Catch, {n}! Don't say I never gave you anything.", f"Take these, {n}. We're even now. Mostly.")
            if steps else
            (f"I hear you, {n}. I'm off to {g}.", f"Can't stop, {n}! Got to {g}.", f"Later, {n}. First I {g}.",
             f"Sure, {n}. After I {g}.", f"Mm-hm. Busy, {n}. Must {g}.", f"Tell me again after I {g}, {n}.")
            if "sleep" not in g else
            (f"Night, {n}.", f"Too tired to argue, {n}. Sleeping.", f"Tomorrow, {n}. Eyes closing.", f"Zzz... what? Oh. Night, {n}."))
        reply = lines[zlib.crc32(f"{a.id}:{world.tick}".encode()) % len(lines)]
        return [{"do": "say", "to": other.name, "text": reply}] + steps

    # what a plan is for, from its goal: the choice menu gets one of each kind instead of five chores
    KINDS = (("experiment", ("experiment", "invent", "try")), ("build", ("build", "restore a", "brick house")),
             ("make", ("make ", "work ", "bake", "fire ", "smelt", "craft")), ("social", ("teach", "tell", "trade", "help", "gift", "preach")),
             ("explore", ("explore", "hunt", "fish", "read", "study")))
    CHORES = ("collect", "store", "mend", "repair", "gather", "rest", "declutter", "put down", "lighten", "refuel", "restore the")

    def _kind(self, goal: str) -> str:
        g = (goal or "").lower()
        for kind, words in self.KINDS:
            if any(w in g for w in words):
                return kind
        return "chore" if any(w in g for w in self.CHORES) else "other"

    def options(self, world, a: Agent, k: int = 6) -> List[Dict[str, Any]]:
        """A few distinct plans a chit could follow now, for a model to choose between (choose/cascade). One of each
        kind (experiment, build, make, social, explore) and at most one chore; survival only when it's needed.
        Drafted by instinct alone, the menus were mostly chores and the 5090's model spent 99% of its steps on them."""
        self._world = world
        seen: set = set()
        out: List[Dict[str, Any]] = []

        def add(p):
            if p and p.get("steps") and p["goal"] not in seen and len(out) < k:
                seen.add(p["goal"])
                p["steps"] = [dict(s) for s in p["steps"] if s][:6]
                out.append(p)

        needy = a.hunger < 40 or a.energy < 25 or a.warmth < 40
        best = self.plan(world, a)
        if needy or self._kind(best.get("goal", "")) != "chore":
            add(best)  # instinct's own pick, unless it's just a chore on a good day
        # one invention it could make now from what it carries (F34): instinct never invents, so without this a chit
        # that only chooses could never invent. Only for a chit whose mind is a model, and it draws nothing random.
        add(INVENTOR.option(world, a))
        seed = world.tick * 31 + zlib.crc32(a.id.encode())
        pool: Dict[str, List[Dict[str, Any]]] = {}
        for i in range(30):
            fn = (self._progress, self._progress, self._progress, self._communal, self._maintain)[i % 5]
            try:
                p = fn(world, a, random.Random(seed + i * 7919))
            except Exception:
                continue
            if p and p.get("steps"):
                pool.setdefault(self._kind(p.get("goal", "")), []).append(p)
        exp = self._experiment(world, a, random.Random(seed + 17))
        if exp:
            pool.setdefault("experiment", []).insert(0, exp)
        for kind in ("experiment", "build", "make", "social", "explore", "other"):
            for p in pool.get(kind, [])[:1]:
                add(p)
        if needy:
            add(self._survive(world, a, random.Random(seed + 3)))
        chores = pool.get("chore", [])
        if chores and not any(self._kind(o.get("goal", "")) == "chore" for o in out):
            add(chores[0])  # one chore, if nothing else is one
        return out

    @staticmethod
    def _make_room(world, a: Agent, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Gathering into full hands fails every time, and the same plan comes straight back. Once that has
        happened, make room first: eat what we carry if we can, otherwise put down something this plan doesn't
        use (never tools)."""
        if not a.last_result.endswith("my hands are full"):
            return steps
        for s in steps:
            if s.get("do") in ("drop", "store", "eat"):
                return steps
            if s.get("do") in ("gather", "take"):
                break
        else:
            return steps
        kind = world.norm_item(s.get("what"))
        it = world.item(kind) if kind else None
        if it is None or a.free_space() >= it.weight:
            return steps
        if any(world.item(f).food <= 100 - a.hunger + 10 for f in food_items(a)):
            return [{"do": "eat"}] + steps
        used = set()
        for st in steps:
            for v in (st.get("what"), *(st.get("with") or [])):
                if isinstance(v, str) and (k := world.norm_item(v)):
                    used.add(k)
        spare = [k for k, n in a.inventory.items()
                 if n > 0 and k not in used and not a._item(k).tool and not a._item(k).carry_bonus
                 and not (world.catalog.items and world.invention_carried(k))]
        if not spare:
            return steps
        junk = max(spare, key=lambda k: (k not in FOODS, a.inventory[k] * a._item(k).weight))
        need = it.weight * max(1, int(s.get("qty") or 1)) - a.free_space()
        qty = min(a.inventory[junk], max(1, -(-need // max(1, a._item(junk).weight))))
        return [{"do": "drop", "what": junk, "qty": qty}] + steps

    # ------------------------------------------------------------------
    def _hunt(self, world, a: Agent) -> Optional[Dict[str, Any]]:
        """Hungry, a spear in hand, a deer nearby and no berries around: go hunting (T31)."""
        from ..sim import animals as AN

        if not getattr(world, "animals", None) or not (a.best_tool("spear") or a.best_tool("weapon")):
            return None
        if world.nearest_resource(a.x, a.y, "berries", 12) is not None:
            return None
        if not AN.nearest(world, a.x, a.y, "deer", 12):
            return None
        return {"goal": "hunt a deer", "thought": "There's a deer close by, and I have a spear.",
                "steps": [{"do": "hunt", "what": "deer"}, {"do": "eat"}]}

    def _desperate_theft(self, world, a: Agent) -> Optional[Dict[str, Any]]:
        """Starving, and the only food around is in the stores of someone who doesn't care for me (T27)."""
        if world.nearest_resource(a.x, a.y, "berries", 20) is not None:
            return None
        piles = [st for st in world.structures_near(a.x, a.y, 30, "stockpile")
                 if st.functional and any(st.storage.get(f, 0) for f in FOODS)]
        if not piles:
            return None

        def friendly(st) -> bool:
            f = world.agents.get(st.founder)
            return st.founder == a.id or f is None or f.affinity.get(a.id, 0.0) >= 10

        if any(friendly(st) for st in piles):
            return None
        st = piles[0]
        food = next(f for f in FOODS if st.storage.get(f, 0))
        return {"goal": "steal food", "thought": "I'm starving, and nobody will share. I'll take some.",
                "steps": [{"do": "steal", "target": st.id, "what": food, "qty": 3}, {"do": "eat"}]}

    @staticmethod
    def _more_storage(world, a: Agent) -> Optional[Dict[str, Any]]:
        """Every stockpile nearby is full: build another rather than drop the load (a 30-day world dropped 384 loads
        with five full stockpiles, and 900 goods lay on the ground). One new stockpile at a time."""
        if a.is_child(world.tick):
            return None
        stores = world.structures_near(a.x, a.y, 25, "stockpile")
        if any(not s.complete or s.upgrade for s in stores):
            return None  # one is going up (or being rebuilt) already: its builder is on it
        if a.knows_design("warehouse"):  # rebuild the fullest stockpile as a warehouse, keeping all it holds
            # only one with clear ground beside it: a hemmed-in stockpile can't grow, and offering it anyway failed
            # 1.6 million times in one 2,600-day world while the stores stayed full
            full = [s for s in stores if s.design == "stockpile" and s.functional and world.same_land(a, s)
                    and upgrade_spot(world, s, "warehouse") is not None]
            if full:
                pile = min(full, key=lambda s: (stockpile_room(s), s.id))
                return {"goal": "make the stockpile a warehouse",
                        "thought": "Every stockpile is full. A warehouse would hold four times as much.",
                        "steps": [{"do": "upgrade", "to": "warehouse", "target": pile.id}]}
            # none can grow where it stands: a new warehouse beside them (its site is supplied from the stores, so
            # full hands don't matter), rather than the load dropped on the ground
            piles = [s for s in stores if s.functional and world.same_land(a, s)]
            cap = max(3, len(world.agents) // 6)
            if piles and len(world.agents) >= DESIGNS["warehouse"].min_pop \
                    and sum(1 for s in world.structures.values() if s.design == "warehouse") < cap:
                pile = min(piles, key=lambda s: (stockpile_room(s), s.id))
                return {"goal": "build a warehouse",
                        "thought": "Every store is full and there's no room to make one bigger. A new warehouse, then.",
                        "steps": [{"do": "build", "what": "warehouse", "near": f"{pile.x},{pile.y}", "_cap": cap}]}
        if not a.knows_design("stockpile"):
            return None
        if sum(1 for s in world.structures.values() if s.design == "stockpile") >= max(5, len(world.agents) // 12):
            return None  # enough (the plan's balance holds a small world to 6; the village builds its own too)
        mats = DESIGNS["stockpile"].material_map
        steps = _need_steps(a, mats, world)
        if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
            return None
        if any(s.get("do") == "gather" for s in steps):
            return None  # its hands are full: only with what it carries or what's in store
        if a.free_space() <= 0 and any(s.get("do") in ("pickup", "take") for s in steps):
            # no room at all: picking up or taking from a store fails at once and the plan comes back (a chit tried to
            # pick up wood for a stockpile 56 times in a row, tools/harness seed 7; a take does the same, Codex #91)
            return None
        h = world.structures.get(a.home or "")
        near = f"{h.x},{h.y}" if h is not None else f"{a.x},{a.y}"
        return {"goal": "build a stockpile", "thought": "Every stockpile is full. We need another.",
                "steps": steps[:4] + [{"do": "build", "what": "stockpile", "near": near}]}

    def _declutter(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        if a.free_space() > 3:
            return None
        piles = [p for p in world.structures_near(a.x, a.y, 25, "stockpile")
                 if p.functional and stockpile_room(p) > 10 and a.reflex_rest.get("unreach:" + p.id, 0) <= world.tick]
        if piles:
            return {"goal": "store my load", "thought": "My arms are full. I'll put things in the stockpile.",
                    "steps": [{"do": "store", "what": "all", "target": piles[0].id}]}
        more = self._more_storage(world, a)
        if more:
            return more
        # never throw away what we're carrying for our own home or our own building site
        keep = set()
        if not a.home and not a.is_child(world.tick):
            keep |= set(DESIGNS["hut"].material_map)
        for s in world.structures.values():
            if s.founder == a.id and not s.complete:
                keep |= set(s.needs)
        junk = max((k for k in a.inventory if not a._item(k).tool and not a._item(k).carry_bonus and k not in FOODS
                    and k not in keep and a.inventory[k] > 0
                    and not (world.catalog.items and (world.invention_carried(k) or a._item(k).food))),
                   key=lambda k: a.inventory[k], default=None)
        if junk:
            return {"goal": "lighten my load", "thought": f"I'm carrying too much {item_name(junk)}.",
                    "steps": [{"do": "drop", "what": junk, "qty": max(1, a.inventory[junk] // 2)}]}
        return None

    def _survive(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        if a.hunger < 20 and not food_items(a):
            theft = self._desperate_theft(world, a)
            if theft:
                return theft
        if a.hunger < 45:
            if food_items(a):
                return {"goal": "eat", "thought": "My stomach is rumbling.", "steps": [{"do": "eat"}]}
            hunt = self._hunt(world, a)
            if hunt:
                return hunt
            # the stores and farms the eat and harvest steps will use (the same two lookups): one the walk found to be
            # a long way round is marked unreachable for a day, and a plan for it again would fail again. Live in a
            # 60-day run, a chit planned "eat from the stores" every tick with food a few tiles off, and starved.
            if HUNGER_REACH:
                store, farm = _stockpile_with(world, a, FOODS, 30), _farm_ready(world, a)
            else:  # (the old lookups, for tests/identity_runner.py)
                store = next((st for st in world.structures_near(a.x, a.y, 30, "stockpile")
                              if any(st.storage.get(f, 0) for f in FOODS)), None)
                farm = next((st for st in world.structures_near(a.x, a.y, 30, "farm")
                             if st.functional and st.planted and st.growth >= 1), None)
            if store:
                return {"goal": "eat from the stores", "thought": "There's food in the stockpile.",
                        "steps": [{"do": "eat"}]}
            if farm:
                return {"goal": "harvest the farm", "thought": "The grain is ripe.",
                        "steps": [{"do": "harvest"}, {"do": "eat"}]}
            what = "fish" if a.best_tool("spear") and world.nearest_resource(a.x, a.y, "fish", 18) and rng.random() < 0.6 else "berries"
            if what == "berries" and world.nearest_resource(a.x, a.y, "berries", 26) is None:
                if a.best_tool("spear"):
                    what = "fish"
                else:
                    return {"goal": "find food", "thought": "The berry bushes are bare. I must search further.",
                            "steps": [{"do": "explore"}]}
            cook = what == "fish" and a.knows_recipe("cooked_fish")
            steps = [{"do": "gather", "what": what, "qty": 6}]
            if cook:
                steps.append({"do": "craft", "what": "cooked_fish", "qty": 2})
            steps.append({"do": "eat"})
            return {"goal": "find food", "thought": f"I'm hungry. Time to get some {item_name(what)}.", "steps": steps}
        if a.energy < 30 or (world.is_night and a.energy < 70):
            return {"goal": "sleep", "thought": "I can barely keep my eyes open.", "steps": [{"do": "sleep"}]}
        cold = world.season in ("autumn", "winter") or world.temperature() < 0.45
        if cold and a.knows_design("campfire"):
            fires = world.structures_near(a.x, a.y, 16, "campfire")
            lit = [f for f in fires if f.lit and f.dist(a.x, a.y) <= 10]
            if not lit:
                if fires and fires[0].complete:
                    st = _fuel_steps(world, a)
                    return {"goal": "keep the fire going", "thought": "The campfire's gone out and it's getting cold.",
                            "steps": st + [{"do": "refuel", "target": fires[0].id}]}
                # (under 9, not 10: chits deciding on the same tick can each start one)
                if not any(not f.complete for f in fires) and sum(1 for f in world.structures.values()
                                                                  if f.design == "campfire" and not f.ruined) < 9:
                    steps = _need_steps(a, DESIGNS["campfire"].material_map, world)
                    return {"goal": "build a campfire", "thought": "The nights are getting cold. We need a fire.",
                            "steps": steps + [{"do": "build", "what": "campfire", "_cap": 10}]}
            elif lit[0].fuel < 35 and rng.random() < 0.5 + a.traits["diligence"] * 0.5:
                st = _fuel_steps(world, a)
                return {"goal": "keep the fire going", "thought": "The fire is burning low.",
                        "steps": st + [{"do": "refuel", "target": lit[0].id}]}
        return None

    def _shelter(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        up = BI.upgrade_plan(world, a, rng)
        if up:  # a crowded family home: rebuild it bigger
            return up
        home = world.structures.get(a.home or "")
        if home and home.functional and not a.is_child(world.tick) and home.founder != a.id:
            cap = HOME_CAP.get(home.design, 2)
            living = [o for o in world.agents.values() if o.home == home.id]
            if len(living) > cap and rng.random() < 0.3:
                # a crowded family home: grown children move out and make their own
                home = None  # proposing a move must not change an unselected chit's home
        if home and home.functional:
            if home.durability < 40 and rng.random() < 0.6:
                mat = DESIGNS[home.design].materials[0][0]
                # (anything in hand that mends it will do: fiber for a hut's thatch, stone for a longhouse)
                pre = [{"do": "gather", "what": mat, "qty": 1}] if mend_material(a, home.design) is None else []
                return {"goal": "repair my home", "thought": "My home is falling apart.",
                        "steps": pre + [{"do": "repair", "target": home.id}]}
            return None
        for st in world.structures_near(a.x, a.y, 25):
            if st.functional and st.design in HOMES:
                cap = HOME_CAP.get(st.design, 2)
                if sum(1 for o in world.agents.values() if o.home == st.id) < cap:
                    return None  # sleep will claim it
        if a.is_child(world.tick):
            return None
        # an old home standing in ruins nearby is quicker to restore than a new one is to build
        ruins = [s for s in world.structures_near(a.x, a.y, 16) if s.complete and s.durability <= 0 and s.design in HOMES]
        if home and home.complete and home.durability <= 0:
            ruins.insert(0, home)
        if ruins:
            st = ruins[0]
            mat = DESIGNS[st.design].materials[0][0]
            pre = [] if a.has(mat, 2) else ([{"do": "gather", "what": mat, "qty": 2}] if mat not in RECIPES else _craft_steps(a, mat, 2, world=world))
            if mat not in RECIPES or pre or a.has(mat, 2):
                return {"goal": "restore a home", "thought": "That old house can be made to stand again.",
                        "steps": pre + [{"do": "repair", "target": st.id}, {"do": "repair", "target": st.id}]}
        # bricks go into the stockpile; nobody ever held 6 (World B: 105 stored, 0 held, 4 brick houses in 260 days)
        design = "brick_house" if a.knows_design("brick_house") and (
            a.has("brick", 6) or a.inventory.get("brick", 0) + _stock_near(world, a, "brick") >= 12) else "hut"
        sites = [s for s in world.structures_near(a.x, a.y, 14) if not s.complete and s.design in ("hut", "brick_house")
                 and _reachable(world, a, s)]
        if sites:
            return self._help_site(a, sites[0], "help build a home", "A home for us — I'll pitch in.")
        if a.reflex_rest.get("nobuild:" + design, 0) > world.tick:
            return None  # no room for one nearby: live without a home for now
        steps = _need_steps(a, DESIGNS[design].material_map, world)
        return {"goal": f"build a {DESIGNS[design].name}", "thought": "I need a place of my own to sleep.",
                "steps": steps[:4] + [{"do": "build", "what": design}]}

    def _maintain(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        """Look after what we have before building more: mend worn buildings, restore ruins."""
        if a.is_child(world.tick) or (a.job != "builder" and rng.random() > 0.3 + 0.5 * a.traits["diligence"]):
            return None
        worn = [s for s in world.structures_near(a.x, a.y, 18)
                if s.complete and DESIGNS[s.design].decay_per_day > 0 and s.durability < (55 if s.durability > 0 else 101)]
        if not worn:
            return None
        # ruins and the buildings everyone relies on come first
        rank = {"farm": 0, "stockpile": 0, "hut": 1, "brick_house": 1, "kiln": 2, "workshop": 2, "furnace": 2, "library": 2,
                "longhouse": 1, "two_storey_house": 1, "bridge": 1, "well": 1, "granary": 1}
        worn.sort(key=lambda s: (s.durability > 0, rank.get(s.design, 3), s.durability))
        st = worn[0]
        mat = DESIGNS[st.design].materials[0][0]
        pre = []
        if mend_material(a, st.design) is None:  # (cord, stone or brick in hand mends what is built with it)
            if mat in RECIPES:
                if not a.knows_recipe(mat):
                    return None
                pre = _fetch_steps(world, a, mat, 1)  # (from the stores once they hold plenty, issue #7)
                if not pre:
                    return None
            else:
                pre = _fetch_steps(world, a, mat, 2)
        name = DESIGNS[st.design].name
        ruined = st.durability <= 0
        return {"goal": f"{'restore the ruined' if ruined else 'mend the'} {name}",
                "thought": f"The {name} {'has fallen into ruin. We can bring it back' if ruined else 'is wearing out. A little work now saves a lot later'}.",
                "steps": pre + [{"do": "repair", "target": st.id}] * (2 if ruined else 1)}

    @staticmethod
    def _can_supply(world, a: Agent, site) -> bool:
        """Only pitch in where we can actually bring something (or the materials are all in and it needs labour)."""
        if not site.needs:
            return True
        for k, n in site.needs.items():
            if a.inventory.get(k, 0) > 0:
                return True
            if k in RECIPES and a.knows_recipe(k):
                return True
            if world.nearest_resource(a.x, a.y, k, 25) is not None:
                return True
        return False

    def _help_site(self, a: Agent, site, goal: str, thought: str) -> Dict[str, Any]:
        steps = []
        world, room = getattr(self, "_world", None), a.free_space()
        for k, n in list(site.needs.items())[:2]:
            have = a.inventory.get(k, 0)
            if have < n:
                # less of it fresh the fuller the stores are of it, and none at its ceiling (issue #7)
                made = k in RECIPES and a.knows_recipe(k)
                if made or k in ("wood", "stone", "fiber", "clay", "sand", "seeds", "ore", "iron_ore"):
                    want = min(n - have, 3 if made else 8)
                    steps += _fetch_steps(world, a, k, want, room)
                    room -= want * (max(1, world.item(k).weight) if world is not None else 1)
        steps.append({"do": "help", "site": site.id})
        return {"goal": goal, "thought": thought, "steps": steps}

    def _trade_offer(self, world, a: Agent) -> Optional[Dict[str, Any]]:
        """Barter a surplus for food (when hungry-ish) or a tool class I lack (T25)."""
        if not hasattr(world, "accepts_trade"):
            return None
        surplus = [k for k, n in sorted(a.inventory.items()) if n >= 8 and (it := a._item(k)) and not it.tool]
        if not surplus:
            return None
        for o in world.agents_near(a.x, a.y, 6, exclude=a.id):
            for k in surplus:
                if o.inventory.get(k, 0) > 0:
                    continue
                wants = []
                if a.hunger < 60:
                    wants += [f for f in FOODS if o.inventory.get(f, 0) > 0]
                wants += [t for t, n in sorted(o.inventory.items()) if n > 0 and (it := o._item(t)) and it.tool
                          and a.best_tool(it.tool) is None]
                for want in wants:
                    for q in (2, 4, 6, 8):
                        give, get = {k: q}, {want: 1}
                        if world.accepts_trade(o, a, give, get):
                            return {"goal": f"trade with {o.name}", "thought": f"{o.name} might swap for my spare {item_name(k)}.",
                                    "steps": [{"do": "trade", "to": o.name, "give": give, "get": get}]}
        return None

    def _communal(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        # contribute to someone's site
        sites = [s for s in world.structures_near(a.x, a.y, 16) if not s.complete and self._can_supply(world, a, s)
                 and _reachable(world, a, s)]
        if sites and rng.random() < 0.35 + 0.4 * a.traits["generosity"]:
            s = rng.choice(sites[:3])
            founder = world.agents.get(s.founder)
            fn = founder.name if founder and founder.id != a.id else "our"
            return self._help_site(a, s, f"help with the {DESIGNS[s.design].name}",
                                   f"{fn + chr(39) + 's' if fn != 'our' else 'Our'} {DESIGNS[s.design].name} needs hands.")
        # autumn stockpiling
        food_stored = sum(p.storage.get(f, 0) for p in world.structures_near(a.x, a.y, 25, "stockpile") for f in FOODS)
        if world.season in ("summer", "autumn") and food_stored < 12 * len(world.agents) and rng.random() < (0.25 if world.season == "summer" else 0.5) + 0.4 * a.traits["caution"]:
            piles = [s for s in world.structures_near(a.x, a.y, 25, "stockpile") if s.functional and stockpile_room(s, "berries") > 10]
            if piles:
                return {"goal": "store food for winter", "thought": "Winter is coming. We'll need stores.",
                        "steps": [{"do": "gather", "what": "berries", "qty": 8}, {"do": "store", "what": "berries"}]}
        # the stores near this chit hold under a few days of food: fill them before the project or odd jobs
        from ..sim import food

        if world.season != "winter" and food.short(world, a) and rng.random() < 0.6:
            piles = [s for s in world.structures_near(a.x, a.y, 25, "stockpile") if s.functional and s.design in HOME_STORES
                     and stockpile_room(s, "berries") > 10]
            if piles:
                ripe = [f for f in world.structures_near(a.x, a.y, 20, "farm") if f.functional and f.planted and f.growth >= 1.0
                        and _reachable(world, a, f)]
                steps = ([{"do": "harvest", "target": ripe[0].id}, {"do": "store", "what": "grain"}] if ripe else
                         [{"do": "gather", "what": "berries", "qty": 8}, {"do": "store", "what": "berries"}])
                steps[-1]["target"] = piles[0].id
                return {"goal": "fill the stores", "thought": "The stores are nearly empty. Food first.", "steps": steps}
        duty = civic.duty(self, world, a, rng)  # the village's project comes before talk and odd jobs
        if duty:
            return duty
        # culture: teach a friend (world A)
        if world.flags.get("teach") and rng.random() < 0.05 + 0.12 * a.traits["sociability"]:
            for o in world.agents_near(a.x, a.y, 8, exclude=a.id):
                gaps = [k for k in a.knows if k not in o.knows and a.knows[k]["how"] != "instinct"]
                if gaps:
                    # what fewest others know first: chosen at random, a chit who knew 80 things almost never taught
                    # the one only it and a friend knew, and live worlds forgot the engine, magnet and gear that way
                    n = _keeper_counts(world)
                    low = min(n.get(g, 0) for g in gaps)
                    k = rng.choice(sorted(g for g in gaps if n.get(g, 0) == low))
                    kind, key = k.split(":", 1)
                    # the world's own name ("Berry-Wick"), not the key: chits said "Now you know how to make a inv b 4!"
                    what = world.item_name(key) if kind == "recipe" else DESIGNS[key].name if key in DESIGNS else key.replace("_", " ")
                    art = "an" if what[:1].lower() in "aeiou" else "a"
                    line = rng.choice((f"Now you know how to make {art} {what}!", f"Watch closely: that's how {art} {what} is made.",
                                       f"There. Next time, you make the {what}.", f"Easy once you see it. Go make {art} {what}!"))
                    return {"goal": f"teach {o.name}", "thought": f"{o.name} doesn't know about the {what} yet.",
                            "steps": [{"do": "teach", "to": o.name, "what": k},
                                      {"do": "say", "to": o.name, "text": line}]}
        if world.flags.get("say") and rng.random() < 0.08 + 0.15 * a.traits["sociability"]:
            line = self._chatter(world, a, rng)
            if line:
                return {"goal": "share news", "thought": "Others should hear about this.",
                        "steps": [{"do": "say", "to": "all", "text": line}]}
        if world.flags.get("write") and a.has("clay_tablet") and rng.random() < 0.3:
            written = {t.knowledge for t in world.tablets.values()}
            best = [k for k, v in a.knows.items() if v["how"] in ("discovered", "insight", "inspected") and k not in written]
            if best:
                return {"goal": "record knowledge", "thought": "This should be written down so it isn't lost.",
                        "steps": [{"do": "write", "what": rng.choice(best)}]}
        deal = self._trade_offer(world, a)
        if deal and rng.random() < 0.1 + 0.2 * a.traits["sociability"]:
            return deal
        # read tablets / study structures
        if rng.random() < 0.25 + 0.4 * a.traits["curiosity"]:
            for lib in world.structures_near(a.x, a.y, 25, "library"):
                if lib.functional and any(_tablet_new(a, world.tablets[t]) for t in lib.shelf if t in world.tablets):
                    return {"goal": "read at the library", "thought": "The library holds things I don't know.",
                            "steps": [{"do": "read"}]}
            # a tablet lying loose that holds what nobody alive still knows (live World A had lost wire; its only
            # tablet lay loose). Only then: reading every loose tablet cost a 60-day A/B ~1 discovery in 12 seeds
            lost = sorted((max(abs(tb.x - a.x), abs(tb.y - a.y)), tb.id) for tb in world.tablets.values()
                          if tb.in_structure is None and tb.knowledge.startswith("recipe:") and _tablet_new(a, tb)
                          and max(abs(tb.x - a.x), abs(tb.y - a.y)) <= LOST_TABLET_TRIP
                          and world.same_land_xy(a, tb.x, tb.y)  # (one across the water was chosen again and again)
                          and a.reflex_rest.get("unreach:" + tb.id, 0) <= world.tick
                          and not any(tb.knowledge in o.knows for o in world.agents.values()))
            for d, tid in lost:
                if d <= 25:  # (this tablet: a bare read went to a library or an earlier tablet first, Codex #25)
                    return {"goal": "read an old tablet", "thought": "Someone wrote something on that tablet.",
                            "steps": [{"do": "read", "tablet": tid}]}
                if not a.is_child(world.tick):
                    # out of the read step's own 25 tiles: a deliberate trip to it (live World B's only tablet of
                    # steel lay 30+ tiles from where anyone went, and steel stayed lost)
                    return {"goal": "fetch lost knowledge",
                            "thought": "There's an old tablet out there with something on it nobody remembers any more.",
                            "steps": [{"do": "read", "tablet": tid}]}
            for st in world.structures_near(a.x, a.y, 20):
                if st.complete and not a.knows_design(st.design):
                    return {"goal": f"study the {DESIGNS[st.design].name}", "thought": "How did they build that?",
                            "steps": [{"do": "inspect", "target": st.id}]}
            for k in a.inventory:
                if k in RECIPES and not a.knows_recipe(k):
                    return {"goal": f"figure out the {item_name(k)}", "thought": f"How is a {item_name(k)} made?",
                            "steps": [{"do": "inspect", "what": k}]}
            for o in world.agents_near(a.x, a.y, 6, exclude=a.id):
                if any(k in RECIPES and not a.knows_recipe(k) for k in o.inventory):
                    return {"goal": f"watch {o.name}", "thought": f"{o.name} has something I've never made.",
                            "steps": [{"do": "inspect", "target": o.name}]}
        return None

    def _chatter(self, world, a: Agent, rng) -> Optional[str]:
        sites = [s for s in world.structures if world.structures[s].founder == a.id and not world.structures[s].complete]
        if sites:
            s = world.structures[sites[0]]
            need = ", ".join(f"{n} {item_name(k)}" for k, n in s.needs.items()) or "a few more hands"
            return rng.choice(LINES_BUILD).format(d=DESIGNS[s.design].name, need=need)
        places = [m for m in a.memories[-10:] if m.kind == "place"]
        if places:
            import re
            found = re.findall(r"([a-z ]+?) at \((\d+),(\d+)\)", places[-1].text.replace("While exploring I found", ""))
            rare = [(w.strip(), int(x), int(y)) for w, x, y in found if w.strip() in ("clay", "copper ore", "fish", "sand", "berries")]
            if rare:
                what, x, y = rare[0]
                dx, dy = x - a.x, y - a.y
                d = ("north" if dy < -3 else "south" if dy > 3 else "") + ("east" if dx > 3 else "west" if dx < -3 else "")
                return f"There's {what} {'to the ' + d if d else 'right around here'}!"
        fresh = [k for k, v in a.knows.items() if v["how"] == "discovered" and world.tick - v["tick"] < 400]
        if fresh:
            k = fresh[-1].split(":", 1)[1]
            return f"I worked out how to make {item_name(k)}: {world.catalog.describe(world.recipe(k))}!" if world.recipe(k) else None
        return None

    def _progress(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        if a.job == "guard" and rng.random() < 0.6:
            pile = next((p for p in world.structures_near(a.x, a.y, 25, "stockpile") if p.functional), None)
            if pile:
                return {"goal": "guard the stockpile", "thought": "Someone should keep watch over our stores.",
                        "steps": [{"do": "guard", "target": pile.id}]}
        opts: List[tuple] = []
        # tools that change what's possible
        for tool, cls in (("stone_axe", "axe"), ("stone_pick", "pick"), ("spear", "spear"), ("basket", None),
                          ("copper_axe", "axe"), ("copper_pick", "pick"), ("lantern", "light")):
            if a.knows_recipe(tool) and not a.has(tool):
                if cls and a.best_tool(cls) and a._item(a.best_tool(cls)).tool_power >= a._item(tool).tool_power:
                    continue
                if _stock_near(world, a, tool) > 0:  # one made at the workshop is in the stores: take that one
                    opts.append((3.0, {"goal": f"fetch a {item_name(tool)}", "thought": f"There's a {item_name(tool)} in the stores.",
                                       "steps": [{"do": "take", "what": tool, "qty": 1}]}))
                    continue
                steps = _craft_steps(a, tool, world=world)
                if steps:
                    opts.append((3.0, {"goal": f"make a {item_name(tool)}", "thought": f"A {item_name(tool)} would make life easier.", "steps": steps}))
        # something better to carry with (issue #9): basket 8, sled 10, cart 16, wagon 28 (less what it weighs); the
        # two best count. Carts were known by a dozen chits in each live world and none was ever made.
        carry = _better_carrier(world, a)
        if carry is not None:
            opts.append(carry)
        # a hunt: spears sat unused (World B: 12 spears, 1 hunt in 260 days) because instinct hunted only when starving
        if getattr(world, "animals", None) and (a.best_tool("spear") or a.best_tool("weapon")) and a.hunger < 85:
            from ..sim import animals as AN
            if AN.nearest(world, a.x, a.y, "deer", 20):
                opts.append((1.5, {"goal": "hunt a deer", "thought": "Fresh meat, and I have the spear for it.",
                                   "steps": [{"do": "hunt", "what": "deer"}, {"do": "eat"}]}))
        # a brick house when the village has stored the bricks for one (warmer than a hut, homes 5): the home
        # planner only ran for homeless chits, so bricks piled up in stockpiles and no one built with them
        if a.knows_design("brick_house") and _stock_near(world, a, "brick") + a.inventory.get("brick", 0) >= 12 \
                and sum(1 for s in world.structures.values() if s.design == "brick_house") < max(2, len(world.agents) // 5) \
                and not any(not s.complete for s in world.structures_near(a.x, a.y, 14, "brick_house")):
            opts.append((2.5, {"goal": "build a brick house", "thought": "We have the bricks. Time for a proper house.",
                               "steps": [{"do": "build", "what": "brick_house"}]}))
        # animals (T31): a pen once cord is known and wild sheep are about; tame one with spare grain
        if getattr(world, "animals", None):
            from ..sim import animals as AN

            pens = [p for p in world.structures_near(a.x, a.y, 12, "pen")]
            if a.knows_design("pen") and not pens and AN.nearest(world, a.x, a.y, "sheep", 15) \
                    and not any(s.design == "pen" for s in world.structures.values()):
                opts.append((1.2, {"goal": "build a pen", "thought": "Those sheep would be worth keeping.",
                                   "steps": [{"do": "build", "what": "pen"}]}))
            if a.has("grain") and any(p.functional for p in pens) and AN.nearest(world, a.x, a.y, "sheep", 15):
                opts.append((1.5, {"goal": "tame a sheep", "thought": "A sheep in the pen means wool.",
                                   "steps": [{"do": "tame"}]}))
        # useful structures not yet nearby
        wants = {"stockpile": 12, "farm": 10, "workshop": 14, "kiln": 14, "furnace": 16, "library": 18,
                 "monument": 20}
        pop = len(world.agents)
        for d, radius in wants.items():
            if not a.knows_design(d):
                continue
            near_all = world.structures_near(a.x, a.y, radius, d)
            if any(not x.complete or x.durability <= 0 for x in near_all):
                continue  # a site in progress or a ruin to restore: don't start another
            near = [x for x in near_all if x.functional]
            standing = [x for x in world.structures.values() if x.design == d and not x.ruined]
            total = sum(1 for x in standing if not (d == "stockpile" and stockpile_room(x) <= 20))
            # (5, not 6: chits deciding on the same tick can each start one, and the town shouldn't pass 6)
            if (d == "farm" and total * 3 >= max(6, pop)) or (d == "stockpile" and (total * 4 >= max(8, pop) or len(standing) >= 5)):
                continue  # the whole town already has plenty
            if d == "stockpile" and SUR.glut(world, a):
                continue  # full of what the village has plenty of: another would fill with the same (issue #7). (A
                # chit with full hands and nowhere to put them still builds one, _more_storage: that or drop the load)
            if d in ("kiln", "workshop", "furnace", "library") and len(standing) >= max(1, min(4, pop // 12)):
                continue
            # a monument is a great shared work, not one per corner of town: a sprawling town (70 tiles across) kept
            # finding none within 20 tiles and stood 39 of them for 89 people by day 2,600
            if d == "monument" and len(standing) >= max(1, pop // 30):
                continue
            # checked again when it builds: chits that planned at the same time each started one (7 stockpiles, 5 kilns)
            cap = 5 if d == "stockpile" else max(1, min(4, pop // 12)) if d in ("kiln", "workshop", "furnace", "library") \
                else max(1, pop // 30) if d == "monument" else 0
            if d == "farm":
                # enough fields to feed everyone nearby: about one per four chits (with more seed in the stores than
                # the village sows, one per three: a new field is where spare seed goes, issue #7)
                per = SUR.SURPLUS_FARM_PER if SUR.over(world, a, "seeds") else 4
                if len(near) * per >= max(4, len(world.agents_near(a.x, a.y, radius))):
                    continue
            elif d == "stockpile":
                if len(near) >= 3 or any(stockpile_room(p) > 20 for p in near):
                    continue
            elif near:
                continue
            if d == "monument" and pop < 12:
                continue
            mats = DESIGNS[d].material_map
            steps = _need_steps(a, mats, world)
            if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
                continue
            w = {"stockpile": 2.5, "farm": 2.5, "workshop": 3.0, "kiln": 3.0, "furnace": 3.0, "library": 2.0,
                 "monument": 1.5}[d]
            opts.append((w, {"goal": f"build a {DESIGNS[d].name}", "thought": f"We don't have a {DESIGNS[d].name} yet. {DESIGNS[d].blurb.capitalize()}.",
                             "steps": steps[:4] + [{"do": "build", "what": d, **({"_cap": cap} if cap else {})}]}))
        # farm upkeep
        for st in world.structures_near(a.x, a.y, 20, "farm"):
            if st.functional and st.planted and st.growth >= 1:
                opts.append((3.5, {"goal": "harvest", "thought": "The grain is ready.", "steps": [{"do": "harvest"}, {"do": "store", "what": "grain"}]}))
            elif st.functional and not st.planted and world.season != "winter":
                pre = _fetch_steps(world, a, "seeds", 2) if not a.has("seeds", 2) else []  # (stored seed first, issue #7)
                opts.append((2.5, {"goal": "plant the farm", "thought": "The plot lies empty.", "steps": pre + [{"do": "plant", "target": st.id}]}))
        # bake/cook when possible
        if a.knows_recipe("bread") and a.has("grain", 2) and world.nearest_station(a.x, a.y, "fire", STATION_NEAR):
            opts.append((1.5, {"goal": "bake bread", "thought": "Bread keeps better than berries.", "steps": [{"do": "craft", "what": "bread", "qty": min(3, a.inventory['grain'] // 2)}]}))
        # nothing new for days: curiosity grows (both live worlds sat on the same discoveries for 15+ days)
        last = max((v.get("tick", 0) for v in world.first.values()), default=0)
        wonder = 1 + min(1.5, max(0.0, (world.tick - last) / 240 - 2) / 4)
        # Iron-Age supply: mines are stores of ore, but station shifts only draw from village stores near the furnace.
        # Feed those stores before scoring another charcoal-heavy furnace shift (audit F11 gate 1).
        feed = feed_furnace_plan(world, a)
        if feed:
            opts.append((3.6 + a.traits["diligence"], feed))
        care = tool_care_plan(world, a)
        if care:
            opts.append((1.4 + a.traits["diligence"], care))
        # a shift at a station nearby, turning stored materials into what the stores lack (the emptier they are of
        # it, the more a shift is worth). Kilns and furnaces used to stand idle beside hundreds of stored clay. It
        # yields to curiosity (weighted 1.2-3.0, x2.5 for crafters, often the keenest experimenters, shifts halved
        # the experiments on one island in the first 30 days), except for what the next era needs: World B sat in
        # the Iron Age for want of iron, steel and gears, and there the next step is made, not found
        if not a.is_child(world.tick):
            bill, _ = plan_bill(world, a, None, radius=WORK_NEAR)
            if bill is not None:
                sname, what = DESIGNS[bill.st.design].name, world.item_name(bill.r.key)
                ins = " and ".join(world.item_name(k) for k, _ in bill.r.inputs)
                w = (0.6 + 1.0 * bill.lack) * (1.3 - 0.6 * a.traits["curiosity"])
                opts.append((w * 1.5 if bill.path else w / wonder, {
                    "goal": f"work at the {sname} ({what})",
                    "thought": (f"We'll need {what} to get further, and the stores have {ins}." if bill.path else
                                f"There's {ins} in the stores and not enough {what}. A shift at the {sname} will fix that."),
                    "steps": [{"do": "work", "at": bill.kind, "target": bill.st.id}]}))
        opts += SUR.sinks(world, a)  # a good over its ceiling: grain to flour at a mill, wood to charcoal at a kiln
        wanted = set()
        for d in DESIGNS.values():
            if a.knows_design(d.key) and not world.structures_near(a.x, a.y, 16, d.key):
                wanted |= {m for m, _ in d.materials}
        for r in RECIPES.values():
            if a.knows_recipe(r.key) and r.key in ("copper_axe", "copper_pick", "lantern", "copper", "glass") and not a.has(r.key):
                wanted |= {m for m, _ in r.inputs}
        if world.flags.get("write") and any(k not in {t.knowledge for t in world.tablets.values()} for k, v in a.knows.items() if v["how"] != "instinct"):
            wanted.add("clay_tablet")
        for mat in ("brick", "charcoal", "copper", "clay_tablet", "glass"):
            if mat in wanted and a.knows_recipe(mat) and a.inventory.get(mat, 0) < (1 if mat == "clay_tablet" else 4) and a.free_space() > 5:
                r = _rec(a, mat)
                if r.station and not world.nearest_station(a.x, a.y, r.station, STATION_REACH):
                    continue
                if SUR.over(world, a, mat):
                    continue  # the stores hold plenty: 1,490 charcoal lay in one village, made four at a time
                steps = _craft_steps(a, mat, 2 if mat != "clay_tablet" else 1, world=world)
                if steps:
                    opts.append((1.2, {"goal": f"make {item_name(mat)}", "thought": f"{item_name(mat).capitalize()} will be needed.", "steps": steps}))
        # roads between busy places
        if a.knows_design("road") and a.has("stone", 2) and len(world.structures) > 5 and rng.random() < 0.3:
            opts.append((0.7, {"goal": "pave a road", "thought": "The path through camp gets muddy.", "steps": [{"do": "build", "what": "road"}, {"do": "build", "what": "road"}]}))
        # store surplus
        roomy = [p for p in world.structures_near(a.x, a.y, 20, "stockpile") if p.functional and stockpile_room(p) > 10]
        if a.load() > a.capacity() * 0.7 and roomy:
            opts.append((2.5, {"goal": "store my load", "thought": "I'm carrying too much.",
                               "steps": [{"do": "store", "what": "all", "target": roomy[0].id}]}))
        # experimenting — the engine of discovery
        exp = self._experiment(world, a, rng)
        if exp:
            opts.append(((0.8 + 3.0 * a.traits["curiosity"]) * wonder, exp))
        # exploring
        opts.append((0.5 + 1.0 * a.traits["curiosity"] * (1 - a.traits["caution"]),
                     {"goal": "explore", "thought": "I wonder what's over there.", "steps": [{"do": "explore"}]}))
        # stockpile raw goods
        piles = world.structures_near(a.x, a.y, 20, "stockpile")
        stocked = {}
        for p in piles:
            for k, n in p.storage.items():
                stocked[k] = stocked.get(k, 0) + n
        # only collect what can actually be found nearby (an island may have no clay at all)
        # ...and only what the village isn't full of: the urge falls as its stores fill, to nothing at the good's
        # ceiling (issue #7: the stores right here could be short of what the village held hundreds of)
        held = SUR.stock(world, a)
        want = {m: SUR.urge(world, a, m, held=held) for m in ("wood", "stone", "fiber", "clay", "berries", "ore", "iron_ore", "sand")}
        lacking = [m for m in ("wood", "stone", "fiber", "clay", "berries") + (("ore", "iron_ore") if a.best_tool("pick") else ())
                   + (("sand",) if a.knows_recipe("brick") else ())
                   if stocked.get(m, 0) < 25 and want[m] > 0 and world.nearest_resource(a.x, a.y, m, 30) is not None]
        room = [p for p in piles if p.functional and stockpile_room(p) > 10]
        if lacking and (room or not piles) and a.free_space() > 6:
            mat = rng.choice(lacking)
            steps = [{"do": "gather", "what": mat, "qty": 6}]
            if room:
                steps.append({"do": "store", "what": mat, "target": room[0].id})
            opts.append(((1.0 + a.traits["diligence"]) * want[mat], {"goal": f"collect {item_name(mat)}", "thought": f"{item_name(mat).capitalize()} is always useful.", "steps": steps}))
        opts += BI.building_options(world, a, rng)  # wells, granaries, mills, smithies, towers, schools, bridges
        store_up = BI.store_upgrade_plan(world, a)
        if store_up:
            opts.append((1.5 + a.traits["diligence"], store_up))
        opts += OP.options(world, a, rng)  # outpost camps by far ore, sand or clay: found, work, haul home
        opts += VOY.options(world, a, rng)  # trade over the sea (contact games): send a load, barter it, sail home
        opts += PR.options(world, a, rng)  # prospecting for what is gone from around home
        opts += PIO.options(world, a, rng)  # pioneers founding a daughter village
        opts += GR.options(world, a, rng)  # strange objects to study, loose goods to carry in
        opts = civic.extend(self, world, a, rng, opts)  # the village's project, study, hints, wants, the famous
        words = JOB_WORDS.get(a.job)
        if words:  # a job (T24) biases what a chit chooses to do, it never forbids anything
            opts = [(w * 2.5 if any(k in o["goal"] for k in words) else w, o) for w, o in opts]
        tot = sum(w for w, _ in opts)
        r = rng.random() * tot
        for w, o in opts:
            r -= w
            if r <= 0:
                return o
        return opts[-1][1]

    @staticmethod
    def _bag_from(text: str) -> Tuple[List[str], str]:
        """'Tried 2 plant fiber + wood at the fire: ...' -> (["plant fiber", "plant fiber", "wood"], "fire")."""
        combo = text.split("Tried ", 1)[1].split(":", 1)[0]
        combo, _, station = combo.partition(" at the ")
        bag: List[str] = []
        for it in combo.split("+"):
            parts = it.strip().split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                bag += [parts[1]] * int(parts[0])
            elif it.strip():
                bag.append(it.strip())
        return bag, station

    def _near_miss(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        """Follow the world's other hints too: "wanted something more" -> add a third thing; "wrong amounts" -> double
        one. Only "needed heat" was followed, and stone axes (cord + sharp stone + wood) went undiscovered for weeks."""
        for m in reversed(a.memories[-12:]):
            if m.kind != "experiment" or "Tried " not in m.text:
                continue
            hinted = next((st for cue, st in STATION_CUES if cue in m.text), None)
            if hinted and hinted != "fire" and world.nearest_station(a.x, a.y, hinted, STATION_REACH):
                # "only a truly roaring fire could change this": the same things at a furnace (copper is
                # charcoal + ore at a furnace; only the campfire hint was followed)
                bag, station = self._bag_from(m.text)
                if bag and station != hinted:
                    return self._exp_plan(a, sorted(bag), hinted, "It needed something stronger. Let's try there.")
            if "want something more" in m.text or "wrong amounts" in m.text:
                bag, station = self._bag_from(m.text)
                if not bag or len(bag) >= MAX_BAG:
                    continue
                if "want something more" in m.text:
                    extra = [k for k in sorted(a.familiar) if k in ITEMS and not a._item(k).tool]
                    if not extra:
                        continue
                    bag = bag + [item_name(rng.choice(extra))]
                else:
                    bag = bag + [rng.choice(bag)]
                if station and not world.nearest_station(a.x, a.y, station, STATION_REACH):
                    station = ""
                return self._exp_plan(a, sorted(bag), station or None, "It felt close. Let me try a little differently.")
        return None

    @staticmethod
    def _heat_idea(world, a: Agent, rng) -> Optional[List[str]]:
        """At a furnace: something that burns very hot + something that melts in great heat. Reasoning from what
        things are like (the properties chits see), as with the toolmaking hunch; it never names a recipe."""
        if not world.nearest_station(a.x, a.y, "furnace", STATION_REACH):
            return None
        seen = set(a.familiar) | set(a.inventory) | {k for p in world.structures_near(a.x, a.y, 25, "stockpile")
                                                     if p.functional for k, n in p.storage.items() if n > 0}
        props = lambda k: set(ITEMS[k].props) if k in ITEMS else set()
        fuel = sorted(k for k in seen if "burns very hot" in props(k))
        melt = sorted(k for k in seen if "melts in great heat" in props(k))
        if not fuel or not melt:
            return None
        return [rng.choice(fuel), rng.choice(melt)] + ([rng.choice(melt)] if rng.random() < 0.3 else [])

    def _experiment(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        """Blind trial-and-error, nudged by the world's feedback in past attempts."""
        haul = self._haul_idea(world, a, rng)
        if haul:
            return haul
        if rng.random() < 0.35:
            bag = self._heat_idea(world, a, rng)
            if bag:
                combo = " + ".join(f"{bag.count(k)} {item_name(k)}" if bag.count(k) > 1 else item_name(k)
                                   for k in sorted(set(bag))) + " at the furnace"
                if combo not in a.failed_experiments:
                    plan = self._exp_plan(a, sorted(bag), "furnace", "Something that burns very hot, and something that melts...")
                    if plan:
                        return plan
        if rng.random() < 0.6:
            near = self._near_miss(world, a, rng)
            if near:
                return near
        # retry a near-miss with heat if the world hinted at it
        for m in reversed(a.memories[-12:]):
            if m.kind == "experiment" and "needed heat" in m.text and world.nearest_station(a.x, a.y, "fire", STATION_REACH):
                combo = m.text.split("Tried ", 1)[1].split(":", 1)[0]
                if " at the " not in combo:
                    items = [c.strip() for c in combo.split("+")]
                    bag = []
                    for it in items:
                        parts = it.split(" ", 1)
                        if parts[0].isdigit():
                            bag += [parts[1]] * int(parts[0])
                        else:
                            bag.append(it)
                    return self._exp_plan(a, bag, "fire", "It felt like it wanted heat. Let's try at the fire.")
        # toolmaking intuition: something long and sturdy + something hard or sharp (+ something binding) might
        # make a tool. That's reasoning from properties the chit has seen, not knowledge of a recipe.
        # (not once it has the tools: a combination that worked was repeated forever, one more tool each time)
        if rng.random() < 0.35 and not all(a.best_tool(c) for c in ("axe", "pick", "spear")):
            fam = [k for k in sorted(a.familiar) if k in ITEMS and not a._item(k).tool]
            handle = [k for k in fam if {"sturdy", "long"} & set(a._item(k).props)]
            head = [k for k in fam if {"hard", "sharp"} & set(a._item(k).props)]
            bind = [k for k in fam if {"binding", "strong"} & set(a._item(k).props)]
            if handle and head:
                bag = [rng.choice(handle), rng.choice(head)] + ([rng.choice(bind)] if bind and rng.random() < 0.6 else [])
                combo = " + ".join(f"{bag.count(k)} {item_name(k)}" if bag.count(k) > 1 else item_name(k)
                                   for k in sorted(set(bag)))
                if combo not in a.failed_experiments:
                    plan = self._exp_plan(a, sorted(bag), None, "A handle, a hard head, maybe something to bind them...")
                    if plan:
                        return plan
        pool = set(RAW) | ({"ore", "iron_ore"} if a.best_tool("pick") else set()) | {k for k in a.inventory if not a._item(k).tool}
        crafted = [k.split(":", 1)[1] for k in a.knows if k.startswith("recipe:")]
        crafted = [k for k in crafted if (k in ITEMS or k in world.catalog.pack_items)  # (a content pack's too)
                   and not a._item(k).tool and not a._item(k).food]
        pool |= set(crafted)
        if rng.random() > 0.3:
            pool.discard("berries")
        pool = sorted(pool)
        village = world.village_failed(a)  # what the neighbours already tried without luck
        stations = [None] + [s for s in STATIONS if world.nearest_station(a.x, a.y, s, STATION_NEAR)]  # (blind: by choice)
        for _ in range(12):
            size = rng.choice((1, 2, 2, 2, 3, 3, 4))  # (a 5 draw now and then cost the 60-day A/B 3.5 discoveries and 0.6 era: dropped)
            bag = [rng.choice(pool) for _ in range(size)]
            if size == 2 and rng.random() < 0.3:
                bag[1] = bag[0]  # two of the same (cord, sharp stone): drawn at random it was 3 bags in 299
            if crafted and rng.random() < 0.5:
                bag[0] = rng.choice(crafted)  # tinker with the newest things we know
            bag.sort()
            station = rng.choice(stations)
            if size == 1 and station is None:
                continue
            combo = " + ".join(f"{n} {item_name(k)}" if n > 1 else item_name(k) for k, n in sorted({k: bag.count(k) for k in bag}.items()))
            key = combo + (f" at the {station}" if station else "")
            if key in a.failed_experiments or key in village:
                continue
            return self._exp_plan(a, bag, station, "What happens if I put these together?")
        return None

    def _haul_idea(self, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
        """Something that hauls more than a cart (issue #9): a chit who has handled a cart, knows how wheels and iron
        are made and stands by a workshop may try for it with the hunch "a cart, more wheels, iron to hold them"
        (brain/civic.py). No age or building ever made the wagon a village project, so the hunch never ran (Codex,
        #41); as a village project it took the one project slot from work that counted for more (#58), so it's a
        curious chit's own try instead."""
        if a.knows_recipe("wagon") or "cart" not in a.familiar or not (a.knows_recipe("wheel") and a.knows_recipe("iron")) \
                or rng.random() >= HAUL_TRY:
            return None
        # a workshop it can walk to (the nearest may be across water: tried and failed, again and again, Codex #66)
        if not any(s.functional and "workshop" in s.stations() and _reachable(world, a, s)
                   for s in world.structures_near(a.x, a.y, STATION_REACH)):
            return None
        from . import civic

        bag = civic._hunch(world, rng, set(world.item("wagon").props), civic._handled(world, a))
        if not bag or civic._combo(bag, "workshop") in set(a.failed_experiments) | set(world.village_failed(a)):
            return None
        return self._exp_plan(a, sorted(bag), "workshop", "A cart with more wheels, and iron to hold them... it might haul more.")

    def _exp_plan(self, a: Agent, bag: List[str], station: Optional[str], thought: str) -> Optional[Dict[str, Any]]:
        from ..sim.items import normalize_item

        world = getattr(self, "_world", None)
        # through the world when there is one: a culture's own name for a thing, or an invention, in a hint memory
        keys = [(world.norm_item(b) if world is not None else normalize_item(b)) for b in bag]
        if any(k is None for k in keys):
            return None
        need: Dict[str, int] = {}
        for k in keys:
            need[k] = need.get(k, 0) + 1
        steps = _supply_steps(a, need, world)
        if steps is None or len(steps) > 5:
            return None
        step = {"do": "experiment", "with": keys}
        if station:
            step["at"] = station
        return {"goal": "experiment", "thought": thought, "steps": steps + [step]}
