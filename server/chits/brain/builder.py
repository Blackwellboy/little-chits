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
    if a.best_tool("pick") and a.knows_recipe("iron"):
        out.append("iron_ore")
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


def _count_all(world, design: str) -> int:
    """Every one of a design, ruins too: what the build itself counts against a step's cap (sim/actions.py)."""
    return sum(1 for s in world.structures.values() if s.design == design)


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
    step = {"do": "build", "what": design, "_cap": cap}
    if sum(mats.values()) > a.capacity():
        # more than anyone can carry (a town hall is 38 things, a chit carries 12): fetching it all first failed
        # before the site was ever started. Start the site; its builders bring the rest from the stores a load at a
        # time. Only when the stores hold every made material it needs (raw ones can be gathered for it).
        stock = _stock(world, a)
        if any(k not in GATHER_RULES and a.inventory.get(k, 0) + stock.get(k, 0) < n for k, n in mats.items()):
            return None
        if near is not None:
            step["near"] = f"{near[0]},{near[1]}"
        return {"goal": f"build a {DESIGNS[design].name}", "thought": thought, "steps": [step]}
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        return None  # something it needs can't be had
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

    # the ores it smelts: one dug out is reason enough (iron is the commoner, and copper ran out first while iron
    # deposits kept the mine from being built, Codex #46)
    smelts = [k for k, metal in (("ore", "copper"), ("iron_ore", "iron")) if a.knows_recipe(metal)]
    if a.knows_design("mine") and smelts and _none_near(world, a.x, a.y, "mine", 30) \
            and any(world.nearest_resource(a.x, a.y, k, 26) is None for k in smelts):
        add(2.0, _build(world, a, "mine", max(1, pop // 15), "The ore near home is dug out. A mine in the rocks would give more."))
    if a.knows_design("sand_pit") and a.reflex_rest.get("scarce:sand", 0) > world.tick \
            and _none_near(world, a.x, a.y, "sand_pit", BLD.PIT_REACH):
        # (it just found no sand within reach: dig a pit by the nearest water)
        add(2.0, _build(world, a, "sand_pit", max(1, pop // 20), "There's no sand left near home. A pit by the water would give some every day."))
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
    # towns: a hall for a big village, a square beside it, and streets along its worn trails
    opts += town_options(world, a)
    opts += town_life_options(world, a)
    opts += palisade_option(world, a)
    opts += city_options(world, a)
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
STREETS_MAX = 140  # paved tiles near a hall before the town stops paving


def _my_village(world, a: Agent):
    from ..sim import pioneers as PIs

    return next((v for v in PIs.villages(world) if a.home in v.structures), None)


def town_options(world, a: Agent) -> List[Tuple[float, Plan]]:
    """A village of 20 builds a town hall at its middle; a town lays a square beside its hall and paves the paths its
    people wear (the most walked first), so streets run where everyone goes."""
    from ..sim import settlements as SE

    out: List[Tuple[float, Plan]] = []
    if a.is_child(world.tick):
        return out
    # its own village's hall: a daughter village 35-70 tiles from its mother (sim/pioneers.py) never got one while
    # the mother's hall stood within 40 tiles of its middle, or within reach of the chit (Codex, #30)
    v = _my_village(world, a)
    hall = world.structures.get(v.hall) if v is not None and v.hall else None
    if hall is None and v is None:
        hall = BLD.hall_near(world, a, SE.HALL_REACH)  # (no home village: the town it stands in)
    if hall is None:
        if v is not None and a.knows_design("town_hall") and len(v.residents) >= SE.TOWN_POP \
                and _none_near(world, int(v.x), int(v.y), "town_hall", SE.HALL_REACH):
            # one hall per village (the reach check above); the cap only stops two of its chits starting two at once
            # (a share of the world's people counted the mother's hall against its daughter)
            plan = _build(world, a, "town_hall", _count_all(world, "town_hall") + 1,  # (a ruin counts at the build)
                          f"{v.name} has grown big enough for a town hall.", near=(int(v.x), int(v.y)))
            if plan:
                out.append((2.0, plan))
        return out
    if a.knows_design("plaza") and _none_near(world, hall.x, hall.y, "plaza", 15):
        plan = _build(world, a, "plaza", max(1, len(world.agents) // SE.TOWN_POP), "The town needs a square by its hall.",
                      near=(hall.x + hall.w // 2, hall.y + hall.h + 2))
        if plan:
            out.append((1.5, plan))
    street = _street_to_pave(world, hall) if a.knows_design("road") else None
    if street is not None:
        have = a.inventory.get("stone", 0) + _stock(world, a).get("stone", 0)
        if have >= 1:
            # (one stone paves a tile: asking for two where one was stored failed the take, Codex #30)
            steps = [] if a.has("stone") else [{"do": "take", "what": "stone", "qty": min(2, have)}]
            out.append((1.2, {"goal": "pave a street", "thought": "Everyone walks this way. It should be paved.",
                              "steps": steps + [{"do": "build", "what": "road", "at": f"{street[0]},{street[1]}"}]}))
    return out


def _fetch_then_craft(a: Agent, key: str, batches: int, stock: Dict[str, int]) -> Optional[List[Dict[str, Any]]]:
    """Take what this many batches need from the stores (what isn't already in hand), then make them; None when the
    stores and hands together fall short. (_craft_steps only gathers: grain in a stockpile never counted.)"""
    r = RECIPES.get(key)
    if r is None:
        return None
    steps: List[Dict[str, Any]] = []
    for k, n in r.inputs:
        short = n * batches - a.inventory.get(k, 0)
        if short > 0:
            if stock.get(k, 0) < short:
                return None
            steps.append({"do": "take", "what": k, "qty": short})
    return steps + [{"do": "craft", "what": key, "qty": batches}]


def palisade_option(world, a: Agent) -> List[Tuple[float, Plan]]:
    """A town with wolves about walls itself in (a palisade round its hall)."""
    from ..sim import settlements as SE

    hall = BLD.hall_near(world, a, SE.HALL_REACH)
    if hall is None or a.is_child(world.tick) or not a.knows_design("palisade") or not _wolves_about(world, a) \
            or not _none_near(world, hall.x, hall.y, "palisade", BLD.PALISADE_RADIUS):
        return []
    plan = _build(world, a, "palisade", _count_all(world, "palisade") + 1, "Wolves keep coming into the town. A wall would keep them out.",
                  near=(hall.x, hall.y))
    return [(2.0, plan)] if plan else []


def town_life_options(world, a: Agent) -> List[Tuple[float, Plan]]:
    """In a town: build what it lacks of tavern, bakery, healer, tailor and park (around the hall), and keep them in
    use: brew ale for the tavern, bake at the bakery, weave warm clothes before winter, and rest at the healer's."""
    from .instinct import _craft_steps
    from ..sim import settlements as SE

    out: List[Tuple[float, Plan]] = []
    if a.is_child(world.tick):
        return out
    hall = BLD.hall_near(world, a, SE.HALL_REACH)
    if hall is None:
        return out
    pop = len(world.agents)
    hurt = sum(1 for o in world.agents_near(hall.x, hall.y, 20) if o.health < 60)
    wants = (("tavern", 1.4, max(1, pop // 25), True, "A tavern would give everyone somewhere to go of an evening."),
             ("bakery", 1.4, max(1, pop // 30), True, "An oven of our own would make every sack of grain go twice as far."),
             ("healer", 2.0 if hurt else 1.0, max(1, pop // 30), True, "The hurt need somewhere to mend."),
             ("tailor", 1.6 if world.season in ("autumn", "winter") else 1.0, max(1, pop // 30), True,
              "Warm clothes would keep the cold off."),
             ("park", 1.0, max(1, pop // 15), True, "A green spot would lift everyone's spirits."))
    for d, w, cap, _, thought in wants:
        if a.knows_design(d) and _none_near(world, hall.x, hall.y, d, SE.HALL_REACH):
            plan = _build(world, a, d, cap, thought)
            if plan:
                out.append((w, plan))
    near = village_stores(world, hall.x, hall.y, 25)
    stock = {}
    for p in near:
        for k, n in p.storage.items():
            stock[k] = stock.get(k, 0) + n
    # brew for the tavern
    tv = next((x for x in world.structures_near(a.x, a.y, 25, "tavern") if x.functional), None)
    if tv is not None and a.knows_recipe("ale") and near and stock.get("ale", 0) < 6:
        steps = _fetch_then_craft(a, "ale", 2, stock)
        if steps:
            pile = min(near, key=lambda p: (p.dist(tv.x, tv.y), p.id))
            out.append((1.3, {"goal": "brew ale for the tavern", "thought": "The tavern's dry.",
                              "steps": steps + [{"do": "store", "what": "ale", "target": pile.id}]}))
    # bake at the bakery (two for one)
    bk = next((x for x in world.structures_near(a.x, a.y, 20, "bakery") if x.functional), None)
    if bk is not None:
        for key, need in (("loaf", {"flour": 2}), ("bread", {"grain": 2})):
            k, n = next(iter(need.items()))
            if a.knows_recipe(key) and a.inventory.get(k, 0) + stock.get(k, 0) >= n * 2:
                fetch = [{"do": "take", "what": k, "qty": n * 2 - a.inventory.get(k, 0)}] if a.inventory.get(k, 0) < n * 2 else []
                out.append((1.4, {"goal": f"bake at the bakery", "thought": "The oven makes two of everything.",
                                  "steps": fetch + [{"do": "go", "to": f"{bk.x},{bk.y}"},
                                                    {"do": "craft", "what": key, "qty": 2}]}))
                break
    # weave warm clothes before the cold
    tl = next((x for x in world.structures_near(a.x, a.y, 20, "tailor") if x.functional), None)
    warm = any(n > 0 and (it := world.item(k)) and "wearable" in it.props and "warm" in it.props
               for k, n in a.inventory.items())
    if tl is not None and not warm and world.season in ("autumn", "winter"):
        if a.knows_recipe("clothes"):
            steps = _craft_steps(a, "clothes", 1, world=world)
            if steps:
                out.append((1.5, {"goal": "make warm clothes", "thought": "Winter's coming and I've nothing warm to wear.",
                                  "steps": steps}))
        elif a.inventory.get("fiber", 0) >= 4 and a.inventory.get("cord", 0) >= 1:
            out.append((1.2, {"goal": "try the loom", "thought": "That loom could weave this fiber into something warm.",
                              "steps": [{"do": "go", "to": f"{tl.x},{tl.y}"},
                                        {"do": "experiment", "with": ["fiber", "fiber", "fiber", "fiber", "cord"], "at": "loom"}]}))
    # the badly hurt rest at the healer's
    hl = next((x for x in world.structures_near(a.x, a.y, 25, "healer") if x.functional), None)
    if hl is not None and a.health < 50 and hl.dist(a.x, a.y) > 3:
        out.append((3.0, {"goal": "rest at the healer's", "thought": "I'm badly hurt. The healer will see to me.",
                          "steps": [{"do": "go", "to": f"{hl.x},{hl.y}"}, {"do": "rest"}]}))
    # a town's first ale: try brewing grain and berries at a workshop
    # (from the stores too: only a chit that happened to carry both ever tried, and no tavern rose in 20-day runs)
    if not a.knows_recipe("ale") and a.knows_design("town_hall") \
            and world.nearest_station(a.x, a.y, "workshop", STATION_NEAR):
        fetch = []
        # (the stores this chit can walk to, around it, as its take looks: the town's, round the hall, offered a brew
        # its take then failed to fetch, Codex #40)
        mine: Dict[str, int] = {}
        for p in village_stores(world, a.x, a.y, 30, a):  # (the take's own reach)
            for k, n in p.storage.items():
                mine[k] = mine.get(k, 0) + n
        for k, n in (("grain", 2), ("berries", 1)):
            short = n - a.inventory.get(k, 0)
            if short > 0 and mine.get(k, 0) >= short:
                fetch.append({"do": "take", "what": k, "qty": short})
            elif short > 0:
                fetch = None
                break
        if fetch is not None:
            out.append((0.8, {"goal": "try brewing", "thought": "Grain and berries left to sit... might they make a drink?",
                              "steps": fetch + [{"do": "experiment", "with": ["grain", "grain", "berries"], "at": "workshop"}]}))
    return out


def city_options(world, a: Agent) -> List[Tuple[float, Plan]]:
    """A city raises a university and a theatre around its hall; a town by the water builds a harbour."""
    from ..sim import settlements as SE

    out: List[Tuple[float, Plan]] = []
    if a.is_child(world.tick):
        return out
    hall = BLD.hall_near(world, a, SE.HALL_REACH)
    if hall is None:
        return out
    pop = len(world.agents)
    if BLD.city_of(world, hall.x, hall.y) is not None:
        for d, w, thought in (("university", 1.8, "A city should have a university, so what we know is kept and shared."),
                              ("theatre", 1.2, "A city deserves a theatre.")):
            if a.knows_design(d) and _none_near(world, hall.x, hall.y, d, SE.HALL_REACH):
                plan = _build(world, a, d, _count_all(world, d) + 1, thought)  # (one per city: the check above)
                if plan:
                    out.append((w, plan))
    fish = world.nearest_resource(hall.x, hall.y, "fish", 20) if a.knows_design("harbour") else None
    if fish is not None and _none_near(world, hall.x, hall.y, "harbour", 40):
        # one per town (a share of the world's people kept a second town from its own), by the fish it's for
        plan = _build(world, a, "harbour", _count_all(world, "harbour") + 1, "Boats and a quay would bring in twice the fish.",
                      near=fish)
        if plan:
            out.append((1.3, plan))
    return out


def _street_to_pave(world, hall) -> Optional[Tuple[int, int]]:
    """The most-walked unpaved, open tile near a town hall (a worn trail: traffic over 30), if the town isn't fully
    paved yet."""
    from ..sim import settlements as SE

    r = SE.STREET_REACH
    if SE.streets_near(world, hall.x, hall.y, r) >= STREETS_MAX:
        return None
    best, best_t = None, 30.0
    w = world.w
    for y in range(max(0, hall.y - r), min(world.h, hall.y + r + 1)):
        for x in range(max(0, hall.x - r), min(w, hall.x + r + 1)):
            i = y * w + x
            t = world.traffic[i]
            if t > best_t and i not in world.roads and i not in world.occupied and world.passable(x, y):
                best, best_t = (x, y), t
    return best


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
