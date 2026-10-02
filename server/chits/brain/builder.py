"""Instinct for the bigger homes, the bridge and the useful buildings (sim/buildings.py).

When a family has outgrown its home and the materials are to hand, rebuild it bigger. When sand, clay or ore lies on
other land just across the water, bridge it. When a well, granary, mill, smithy, watchtower, school or bell tower would
earn its keep here, build one; and once there is a mill, grind and bake. Instinct.plan calls in here. Like the rest of
instinct it knows only what the chit knows: designs it has had the idea for, recipes it has learned.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..sim import buildings as BLD
from ..sim.actions import GATHER_RULES, FOODS, STATION_NEAR, village_stores
from ..sim.agent import Agent, TICKS_PER_DAY
from ..sim.items import DESIGNS, RECIPES, item_name

Plan = Dict[str, Any]
METAL_TOOLS = (("iron_axe", "axe"), ("iron_pick", "pick"), ("copper_axe", "axe"), ("copper_pick", "pick"))


def _stock(world, a: Agent, radius: int = 25) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in village_stores(world, a.x, a.y, radius):
        for k, n in p.storage.items():
            out[k] = out.get(k, 0) + n
    return out


def _supply_steps(world, a: Agent, need: Dict[str, int]) -> Optional[List[Dict[str, Any]]]:
    """Steps that bring what `need` lacks beyond what is carried and stored nearby (the upgrade fetches from the
    stores itself). Raw things may be gathered and cord made; anything else must already be stored ("materials are
    stored"), or this returns None."""
    from .instinct import _craft_steps

    stock = _stock(world, a)
    steps: List[Dict[str, Any]] = []
    for k, n in need.items():
        short = n - a.inventory.get(k, 0) - stock.get(k, 0)
        if short <= 0:
            continue
        if k in GATHER_RULES and GATHER_RULES[k]["requires"] is False and world.nearest_resource(a.x, a.y, k, 26):
            steps.append({"do": "gather", "what": k, "qty": min(short, 8)})
        elif k in RECIPES and RECIPES[k].station is None and a.knows_recipe(k):
            sub = _craft_steps(a, k, min(short, 4), world=world)
            if not sub:
                return None
            steps += sub
        else:
            return None
    return steps


# ---------------------------------------------------------------------------- a bigger home
def upgrade_plan(world, a: Agent, rng) -> Optional[Plan]:
    """A crowded family home, a bigger design known and the materials to hand: rebuild it bigger where it stands.
    A home already being rebuilt: bring what it still needs and lend a hand."""
    if a.is_child(world.tick):
        return None
    home = world.structures.get(a.home or "")
    if home is None or not home.functional or home.design not in BLD.UPGRADES:
        return None
    old = DESIGNS[home.design].name
    if home.upgrade:
        if rng.random() > 0.6:
            return None
        steps = _supply_steps(world, a, home.upgrade.get("needs", {}))
        if steps is None:
            return None
        new = DESIGNS[home.upgrade["to"]].name
        return {"goal": f"rebuild our {old} as a {new}", "thought": f"Our new {new} is going up. I'll lend a hand.",
                "steps": steps[:4] + [{"do": "upgrade", "target": home.id}]}
    n, cap = BLD.residents(world, home), BLD.HOME_CAP[home.design]
    if n <= cap or rng.random() > 0.5:  # (full is fine; more living there than it was built for is crowded)
        return None
    for to in sorted((k for k in BLD.UPGRADES[home.design] if a.knows_design(k)), key=lambda k: -BLD.HOME_CAP[k]):
        steps = _supply_steps(world, a, BLD.salvage_needs(home.design, to))
        if steps is None or BLD.upgrade_spot(world, home, to) is None:
            continue
        new = DESIGNS[to].name
        return {"goal": f"make our {old} a {new}", "thought": f"{n} of us in a {old} built for {cap}. A {new} would "
                                                              f"give the family room to grow.",
                "steps": steps[:4] + [{"do": "upgrade", "to": to, "target": home.id}]}
    return None


def store_upgrade_plan(world, a: Agent) -> Optional[Plan]:
    """A stockpile being rebuilt bigger (as a warehouse) waits for materials: bring them and lend a hand. Only a chit's
    own home was ever carried on, so a store upgrade stood half done once its first builder moved on; live, six
    stockpiles in each world waited for stone and cord that full stores never took in, and while one waited no more
    storage was begun (audit F10). The stone is gathered and the cord made by hand: no room in the stores needed."""
    if a.is_child(world.tick) or a.free_space() < 6:
        return None
    for st in village_stores(world, a.x, a.y, 25, a):
        if not st.upgrade or st.design not in BLD.UPGRADES:
            continue
        steps = _supply_steps(world, a, st.upgrade.get("needs", {}))
        if steps is None:
            continue
        new = DESIGNS[st.upgrade["to"]].name
        return {"goal": f"help rebuild the {DESIGNS[st.design].name} as a {new}",
                "thought": f"The new {new} is half built. It still needs things; I'll bring them.",
                "steps": steps[:4] + [{"do": "upgrade", "target": st.id}]}
    return None


# ---------------------------------------------------------------------------- a bridge
def _wanted_across(a: Agent) -> List[str]:
    """The scarce things this chit has a use for."""
    out = []
    if a.knows_recipe("brick") or a.knows_recipe("glass"):
        out.append("sand")
    out.append("clay")
    if a.best_tool("pick") or a.knows_recipe("copper"):
        out.append("ore")
    return out


def bridge_plan(world, a: Agent, rng) -> Optional[Plan]:
    """Sand, clay or ore lies on other land just across the water, and nothing as close on this side: bridge it."""
    from .instinct import _need_steps

    t = world.tick
    if not a.knows_design("bridge") or a.is_child(t) or rng.random() > 0.3:
        return None
    memo = world.__dict__.setdefault("_nobridge", {})  # a planner's cache: not saved, not the chit's state
    if memo.get(a.id, 0) > t or a.reflex_rest.get("nobuild:bridge", 0) > t:
        return None
    bridges = [s for s in world.structures.values() if s.design == "bridge"]
    cap = max(2, len(world.agents) // 8)
    if len(bridges) >= cap or any(not s.complete for s in bridges):
        return None
    for kind in _wanted_across(a):
        own, other = BLD.resource_sides(world, a, kind)
        if other is None or (own is not None and own[0] <= other[0] + 6):
            continue
        c = BLD.best_crossing(world, a, a.x, a.y, 14, other[3])
        if c is None:
            continue
        mats = DESIGNS["bridge"].material_map
        steps = _need_steps(a, mats, world)
        if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
            continue
        (nx, ny), (fx, fy) = c[6], c[7]
        return {"goal": "bridge the water", "thought": f"There's {item_name(kind)} just across the water. A bridge "
                                                       f"would bring it within reach.",
                "steps": steps[:4] + [{"do": "build", "what": "bridge", "near": f"{nx},{ny}", "toward": f"{fx},{fy}",
                                       "_cap": cap}]}
    memo[a.id] = t + TICKS_PER_DAY  # nothing to bridge to: look again tomorrow
    return None


# ---------------------------------------------------------------------------- the useful buildings
def _count(world, design: str) -> int:
    return sum(1 for s in world.structures.values() if s.design == design and not s.ruined)


def _none_near(world, x: int, y: int, design: str, radius: int) -> bool:
    return not world.structures_near(x, y, radius, design)


def _farms(world, a: Agent, radius: int) -> List:
    return [f for f in world.structures_near(a.x, a.y, radius, "farm") if f.functional]


def _food_pile(world, a: Agent):
    """A stockpile near here with plenty of food in it and no granary looking after it."""
    for p in world.structures_near(a.x, a.y, 14, "stockpile"):
        if p.functional and not BLD.keeps_fresh(world, p) and \
                sum(n for k, n in p.storage.items() if k in FOODS) >= 20:
            return p
    return None


def _wolves_about(world, a: Agent) -> bool:
    if any(m.kind == "danger" and "wolf" in m.text and world.tick - m.tick < 2 * TICKS_PER_DAY for m in a.memories[-20:]):
        return True
    return any(w["kind"] == "wolf" and max(abs(w["x"] - a.x), abs(w["y"] - a.y)) <= 25
               for w in getattr(world, "animals", {}).values())


def _build(world, a: Agent, design: str, cap: int, thought: str, near=None) -> Optional[Plan]:
    from .instinct import _need_steps

    if a.reflex_rest.get("nobuild:" + design, 0) > world.tick or _count(world, design) >= cap:
        return None
    mats = DESIGNS[design].material_map
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        return None  # something it needs can't be had
    step = {"do": "build", "what": design, "_cap": cap}
    if near is not None:
        step["near"] = f"{near[0]},{near[1]}"
    return {"goal": f"build a {DESIGNS[design].name}", "thought": thought, "steps": steps[:4] + [step]}


def building_options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    """Weighted plans for the useful buildings this chit knows and its village lacks. None are started in the dark:
    trips for stone and wood at night had wolves biting chits 57 times in six 30-day runs instead of 16."""
    if world.is_night:
        return []
    pop = len(world.agents)
    opts: List[Tuple[float, Plan]] = []

    def add(w: float, plan: Optional[Plan]) -> None:
        if plan:
            opts.append((w, plan))

    if a.knows_design("mine") and (a.knows_recipe("copper") or a.knows_recipe("iron")) \
            and _none_near(world, a.x, a.y, "mine", 30) and world.nearest_resource(a.x, a.y, "ore", 26) is None:
        add(2.0, _build(world, a, "mine", max(1, pop // 15), "The ore near home is dug out. A mine in the rocks would give more."))
    if a.knows_design("well") and len(_farms(world, a, 12)) >= 2 and _none_near(world, a.x, a.y, "well", 10):
        add(2.0, _build(world, a, "well", max(1, pop // 10), "Our fields are thirsty. A well would water them."))
    if a.knows_design("granary"):
        pile = _food_pile(world, a)
        if pile is not None:
            add(2.5 if world.season in ("summer", "autumn") else 1.5,
                _build(world, a, "granary", max(1, pop // 12), "The stored food is going bad. A granary would keep it.",
                       near=(pile.x, pile.y)))
    if a.knows_design("mill") and len(_farms(world, a, 20)) >= 2 and _none_near(world, a.x, a.y, "mill", 20):
        add(1.5, _build(world, a, "mill", max(1, pop // 15), "All this grain... a millstone could grind it finer."))
    if a.knows_design("smithy") and any(a.knows_recipe(t) for t, _ in METAL_TOOLS) \
            and _none_near(world, a.x, a.y, "smithy", 25):
        add(1.2, _build(world, a, "smithy", max(1, pop // 15), "Metal wants an anvil and bellows of its own."))
    if a.knows_design("watchtower") and _wolves_about(world, a) and _none_near(world, a.x, a.y, "watchtower", 15):
        add(2.5, _build(world, a, "watchtower", max(1, pop // 10), "Wolves prowl at night. A lookout would keep them off."))
    if a.knows_design("school") and _none_near(world, a.x, a.y, "school", 20) \
            and sum(1 for o in world.agents_near(a.x, a.y, 12) if o.is_child(world.tick)) >= 2:
        add(1.5, _build(world, a, "school", max(1, pop // 15), "The little ones should learn what we know."))
    if a.knows_design("bell_tower") and pop >= DESIGNS["bell_tower"].min_pop:
        add(1.0, _build(world, a, "bell_tower", max(1, pop // 30), "A bell to call everyone together each morning."))
    # the Machine and Electric Ages
    if a.knows_design("steam_pump") and len(_farms(world, a, 12)) >= 2 and _none_near(world, a.x, a.y, "steam_pump", 12):
        add(2.0, _build(world, a, "steam_pump", max(1, pop // 15), "An engine could lift water to every field at once."))
    if a.knows_design("sawmill") and _none_near(world, a.x, a.y, "sawmill", 20) \
            and world.nearest_resource(a.x, a.y, "wood", 12) is not None:
        add(1.5, _build(world, a, "sawmill", max(1, pop // 25), "An engine could drive a saw. Every log would go twice as far."))
    if a.knows_design("printing_press") and _none_near(world, a.x, a.y, "printing_press", 30) \
            and any(x.functional for x in world.structures_near(a.x, a.y, 30, "library")):
        add(1.5, _build(world, a, "printing_press", max(1, pop // 40),
                        "What only a few of us know should be printed before it is lost."))
    if a.knows_design("power_station") and _none_near(world, a.x, a.y, "power_station", 25) \
            and any(s.functional and s.stations() & POWERED for s in world.structures_near(a.x, a.y, 20)):
        add(2.0, _build(world, a, "power_station", max(1, pop // 25), "Dynamos could drive every bench and furnace in town."))
    if a.knows_design("street_lamp") and _wolves_about(world, a) and _none_near(world, a.x, a.y, "street_lamp", 6):
        add(1.5, _build(world, a, "street_lamp", max(2, pop // 6), "A light here would keep the wolves off."))
    add(2.5, bridge_plan(world, a, rng))
    opts += _paper_for_the_press(world, a)
    opts += _mill_and_bake(world, a)
    opts += _at_the_smithy(world, a)
    return opts


POWERED = {"workshop", "kiln", "furnace", "forge", "mill", "factory"}


def _paper_for_the_press(world, a: Agent) -> List[Tuple[float, Plan]]:
    """A printing press nearby with no paper in the stores beside it: make some at a workshop and store it there."""
    from .instinct import _craft_steps

    pr = next((x for x in world.structures_near(a.x, a.y, 25, "printing_press") if x.functional), None)
    if pr is None or not a.knows_recipe("paper"):
        return []
    near = village_stores(world, pr.x, pr.y, BLD.PRESS_REACH)
    if not near or sum(p.storage.get("paper", 0) for p in near) >= 3:
        return []
    steps = _craft_steps(a, "paper", 2, world=world)
    if not steps:
        return []
    return [(1.5, {"goal": "make paper for the press", "thought": "The press has no paper left to print on.",
                   "steps": steps + [{"do": "store", "what": "paper", "target": near[0].id}]})]


def _mill_and_bake(world, a: Agent) -> List[Tuple[float, Plan]]:
    """A mill nearby: try grinding grain at it, bake what it grinds, and once both are known, make loaves."""
    mill = next((m for m in world.structures_near(a.x, a.y, 20, "mill") if m.functional), None)
    if mill is None:
        return []
    stock = _stock(world, a)
    grain = a.inventory.get("grain", 0) + stock.get("grain", 0)
    flour = a.inventory.get("flour", 0) + stock.get("flour", 0)
    fire = world.nearest_station(a.x, a.y, "fire", STATION_NEAR)

    def fetch(k: str, n: int) -> List[Dict[str, Any]]:
        short = n - a.inventory.get(k, 0)
        return [{"do": "take", "what": k, "qty": short}] if short > 0 else []

    if not a.knows_recipe("flour"):
        if grain >= 1:
            return [(2.0, {"goal": "try the millstone", "thought": "That millstone could grind this grain...",
                           "steps": fetch("grain", 1) + [{"do": "experiment", "with": ["grain"], "at": "mill"}]})]
        return []
    if not a.knows_recipe("loaf"):
        if fire is not None and (flour >= 2 or grain >= 2):
            pre = fetch("flour", 2) if flour >= 2 else fetch("grain", 2) + [{"do": "craft", "what": "flour", "qty": 2}]
            return [(1.5, {"goal": "bake the flour", "thought": "Flour this fine... what would heat make of it?",
                           "steps": pre + [{"do": "experiment", "with": ["flour", "flour"], "at": "fire"}]})]
        return []
    if fire is not None and grain >= 4 and a.free_space() > 4:
        steps = fetch("grain", 4) + [{"do": "craft", "what": "flour", "qty": 4}, {"do": "craft", "what": "loaf", "qty": 2}]
        if world.structures_near(a.x, a.y, 20, "stockpile"):
            steps.append({"do": "store", "what": "loaf"})
        return [(2.0, {"goal": "bake loaves", "thought": "Ground grain bakes into loaves that fill you for a day.",
                       "steps": steps})]
    return []


def _at_the_smithy(world, a: Agent) -> List[Tuple[float, Plan]]:
    """A smithy nearby: make the metal tool this chit lacks there, where it goes twice as fast."""
    from .instinct import _craft_steps

    sm = next((x for x in world.structures_near(a.x, a.y, 25, "smithy") if x.functional), None)
    if sm is None:
        return []
    for tool, cls in METAL_TOOLS:
        if not a.knows_recipe(tool) or a.has(tool):
            continue
        best = a.best_tool(cls)
        if best and a._item(best).tool_power >= a._item(tool).tool_power:
            continue
        steps = _craft_steps(a, tool, world=world)
        if steps:
            steps.insert(len(steps) - 1, {"do": "go", "to": sm.id})
            return [(3.5, {"goal": f"make a {item_name(tool)} at the smithy", "thought": "The anvil makes quick work "
                                                                                         "of metal.", "steps": steps})]
    return []
