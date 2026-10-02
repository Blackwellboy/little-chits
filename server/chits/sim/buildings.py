"""What the bigger homes, the bridge and the useful buildings DO.

Their designs are in items.DESIGNS like every other structure (materials, the idea that unlocks them, a blurb). This
module is their effect on the world, reached through small hooks in the world, the actions and the animals:
- homes: how many each holds (HOME_CAP), which keep out any weather, and rebuilding a home bigger where it stands
  (the `upgrade` verb) with everyone still living in it; a crowded home has fewer children
- bridge: a deck over 1-3 water tiles that chits (and wolves) can walk; World.rebuild_block lays it into the grid
- well: chits sleeping near it recover faster, and farms within 6 tiles grow a third faster
- granary: food in stockpiles within 10 tiles doesn't rot (elsewhere ~2% of stored food spoils a day, less with pots)
- mill: the "mill" station, where grain is ground into flour (a loaf of it is more filling than bread)
- smithy: a workshop where metal tools are made twice as fast
- watchtower: wolves within 12 tiles are driven off and bite no one there
- school: children within 8 tiles learn recipes from the grown-ups around it
- bell tower: rings every morning; the chits within 20 tiles gather (mood, friendship, and the chief's objective)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import terrain as T
from .agent import TICKS_PER_DAY, Agent
from .items import DESIGNS, HOME_STORES, STORES, normalize_design

HOME_CAP: Dict[str, int] = {"hut": 3, "brick_house": 5, "longhouse": 6, "two_storey_house": 8, "apartment": 12}
HOMES: Tuple[str, ...] = tuple(HOME_CAP)
WARM_HOMES = ("brick_house", "two_storey_house", "apartment")  # warm inside in any weather; a hut or longhouse not in a winter storm
UPGRADES: Dict[str, Tuple[str, ...]] = {"hut": ("longhouse", "brick_house"), "brick_house": ("two_storey_house",),
                                        "longhouse": ("two_storey_house",), "two_storey_house": ("apartment",),
                                        "stockpile": ("warehouse",)}  # a full village's store, rebuilt bigger in place
UPGRADE_WORK = 0.6  # rebuilding over an old home takes this share of building the new one from scratch

BRIDGE_MAX = 3  # water tiles one bridge can span
WATER = (T.SHALLOW, T.DEEP)
WELL_RADIUS, WELL_REST, WELL_GROWTH = 6, 1.3, 1.3
GRANARY_RADIUS, SPOIL_PER_DAY, POT_KEEPS = 10, 0.02, 10  # a clay pot in a stockpile keeps 10 food fresh
# the most perishable food rots first; anything else (a world's own dishes) after these
PERISH = ("fish", "meat", "berries", "cooked_fish", "cooked_meat", "berry_tart", "loaf", "bread", "grain")
SMITHY_SPEED = 2.0
TOWER_RADIUS = 12
SCHOOL_RADIUS, SCHOOL_EVERY, SCHOOL_P = 8, 20, 0.15
BELL_RADIUS, BELL_TICK, BELL_MOOD = 20, 80, 8.0  # it rings at 8:00
# a building of the same kind this close is used instead of starting another (actions.REUSE_WITHIN)
REUSE_WITHIN = {"well": 8, "granary": 12, "mill": 15, "smithy": 15, "watchtower": 12, "school": 15, "bell_tower": 25,
                "steam_pump": 10, "sawmill": 15, "printing_press": 25, "power_station": 20, "street_lamp": 4,
                "town_hall": 30, "plaza": 15, "tavern": 20, "bakery": 15, "healer": 20, "tailor": 20, "park": 10,
                "university": 30, "theatre": 30, "harbour": 20, "palisade": 30}
_FX = ("well", "granary", "watchtower", "school", "smithy", "bell_tower", "great_library", "aqueduct", "lighthouse",
       "steam_pump", "sawmill", "printing_press", "power_station", "street_lamp", "town_hall", "plaza",
       "tavern", "bakery", "healer", "tailor", "park", "university", "theatre", "harbour", "palisade")
PALISADE_RADIUS = 22  # a palisade keeps wolves out of this much of the town round its gate
CITY_ONLY = ("university", "theatre")  # the build verb refuses them outside a city
UNI_RADIUS, UNI_EVERY, UNI_P = 20, 30, 0.08
THEATRE_RADIUS, THEATRE_TICK, THEATRE_MOOD = 15, 200, 8.0  # 20:00
HARBOUR_RADIUS = 12
TAVERN_RADIUS, TAVERN_TICK, TAVERN_MOOD, ALE_MOOD = 10, 190, 3.0, 6.0  # 19:00; with an ale, 3 + 6
BAKED, BAKERY_MULT = ("bread", "loaf", "berry_tart"), 2
HEALER_RADIUS, HEALER_MULT = 10, 3.0
PARK_RADIUS = 6
PLAZA_RADIUS, PLAZA_TICK, PLAZA_MOOD = 12, 180, 4.0  # the evening gathering on a town square, at 18:00
TOWN_CENTRE = ("market", "library", "school", "bell_tower", "great_library", "monument", "plaza", "printing_press",
               "shrine", "tavern", "bakery", "healer", "tailor", "fountain", "park", "university", "theatre")  # go up around a town hall
HALL_PULL = 30  # a hall this near the builder draws them
PUMP_RADIUS, PUMP_GROWTH = 10, 1.5  # farms this near a steam pump grow faster, and through a drought
SAW_RADIUS = 12  # wood cut this near a sawmill comes in double
POWER_RADIUS, POWER_SPEED = 20, 1.5  # station work this near a power station goes faster
LAMP_RADIUS = 6  # no wolf bites this near a street lamp
PRESS_REACH = 15  # a printing press takes its paper from stores this near, and shelves in a library within 30
GREAT_WORKS = ("monument", "great_library", "lighthouse", "aqueduct")
LIBRARY_REACH, STUDY_MULT = 40, 2.0  # study within this reach of a great library goes twice as far
AQUEDUCT_RADIUS, AQUEDUCT_GROWTH = 20, 1.3  # farms this near an aqueduct grow faster, and through a drought


# ---------------------------------------------------------------------------- which buildings are standing
def fx(world) -> Dict[str, Any]:
    """The working wells, granaries, towers, schools, smithies and bell towers, looked up once a tick. The tiles near
    a well are only recomputed when the set of working ones changes."""
    c = getattr(world, "_bfx", None)
    if c is not None and c["tick"] == world.tick:
        return c
    found: Dict[str, List] = {k: [] for k in _FX}
    for s in world.structures.values():
        lst = found.get(s.design)
        if lst is not None and s.functional:
            lst.append(s)
    sig = tuple(s.id for k in _FX for s in found[k])
    if c is None or c["sig"] != sig:
        rest = set()
        for s in found["well"]:
            for y in range(max(0, s.y - WELL_RADIUS), min(world.h, s.y + s.h + WELL_RADIUS)):
                for x in range(max(0, s.x - WELL_RADIUS), min(world.w, s.x + s.w + WELL_RADIUS)):
                    rest.add(y * world.w + x)
        c = {"sig": sig, "rest": rest}
    c.update(found)
    c["tick"] = world.tick
    world._bfx = c
    return c


def gap(a, b) -> int:
    """Tiles between two structures' footprints (0 when they touch or overlap)."""
    dx = max(a.x - (b.x + b.w - 1), b.x - (a.x + a.w - 1), 0)
    dy = max(a.y - (b.y + b.h - 1), b.y - (a.y + a.h - 1), 0)
    return max(dx, dy)


def step(world) -> None:
    """Called by World.step every tick, after the chits have acted."""
    t = world.tick
    if t % SCHOOL_EVERY == 0:
        _school(world)
    if t % UNI_EVERY == 0:
        _university(world)
    if t % TICKS_PER_DAY == THEATRE_TICK:
        _theatre(world)
    if t % TICKS_PER_DAY == BELL_TICK:
        _bell(world)
    if t % TICKS_PER_DAY == PLAZA_TICK:
        _plaza(world)
    if t % TICKS_PER_DAY == TAVERN_TICK:
        _tavern(world)
    if t % TICKS_PER_DAY == 0:
        _spoil(world)
        _mice(world)
        _mines(world)
        _mills(world)
        _presses(world)


# ---------------------------------------------------------------------------- homes
def residents(world, st) -> int:
    return sum(1 for o in world.agents.values() if o.home == st.id)


def birth_home(world, a: Agent, b: Agent):
    """Where a couple's child would be born, and how likely it is there: in whichever of their homes has the most
    room. A full home halves the chance; two or more past full, no child comes until someone moves out or the home
    is made bigger."""
    homes = [h for h in (world.structures.get(a.home or ""), world.structures.get(b.home or ""))
             if h is not None and h.functional]
    if not homes:
        return None, 0.0
    room = {h.id: HOME_CAP.get(h.design, 3) - residents(world, h) for h in homes}
    best = max(homes, key=lambda h: room[h.id])
    r = room[best.id]
    return best, (1.0 if r > 0 else 0.5 if r > -2 else 0.0)


def salvage_needs(old: str, new: str) -> Dict[str, int]:
    """What rebuilding an `old` home as a `new` one still needs: what the old one was made of is used again."""
    have = DESIGNS[old].material_map
    return {k: n - min(n, have.get(k, 0)) for k, n in DESIGNS[new].materials if n > have.get(k, 0)}


def _free_for(world, x: int, y: int, own) -> bool:
    if (x, y) in own:
        return True
    if not world.inb(x, y):
        return False
    i = y * world.w + x
    if i in world.occupied or i in world.roads or not T.PASSABLE[world.tiles[i]]:
        return False
    return not (world.tiles[i] == T.FOREST and world.res_amt[i] > 0 and world.res_kind[i] == T.R_WOOD)


def upgrade_spot(world, st, to: str) -> Optional[Tuple[int, int]]:
    """Where the bigger home would stand: over the old one, growing into free ground beside it."""
    w, h = DESIGNS[to].size
    own = set(st.cells())
    for oy in range(max(0, h - st.h) + 1):
        for ox in range(max(0, w - st.w) + 1):
            x, y = st.x - ox, st.y - oy
            if all(_free_for(world, cx, cy, own) for cy in range(y, y + h) for cx in range(x, x + w)):
                return x, y
    return None


def upgrade_target(world, a: Agent, st, raw: Any = None) -> Tuple[Optional[str], str]:
    """The home design this chit would rebuild `st` into, or (None, why not)."""
    opts = UPGRADES.get(st.design, ())
    old = DESIGNS[st.design].name
    if not opts:
        return None, f"a {old} is already as big as it gets"
    if raw:
        key = normalize_design(raw)
        if key not in opts:
            names = " or ".join(DESIGNS[k].name for k in opts)
            return None, f"a {old} can be rebuilt as a {names}, not a {DESIGNS[key].name if key else raw}"
        if not a.knows_design(key):
            return None, f"I don't know how to build a {DESIGNS[key].name} yet"
        return key, ""
    known = [k for k in opts if a.knows_design(k)]
    if not known:
        return None, f"I don't know how to build anything bigger than a {old} yet"
    stock = _stock_around(world, st)

    def ready(k: str) -> float:
        need = salvage_needs(st.design, k)
        return sum(min(n, a.inventory.get(m, 0) + stock.get(m, 0)) for m, n in need.items()) / max(1, sum(need.values()))

    return max(known, key=lambda k: (ready(k) >= 1.0, HOME_CAP.get(k, 0), ready(k))), ""


def _stock_around(world, st, radius: int = 25) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in world.structures_near(int(st.x), int(st.y), radius, "stockpile"):
        if p.functional:
            for k, n in p.storage.items():
                out[k] = out.get(k, 0) + n
    return out


def upgrade_instead(world, a: Agent, key: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """`build` a bigger home while living in a smaller one close by: that one is rebuilt where it stands (an upgrade
    step) rather than a second house going up beside it."""
    if key not in HOME_CAP:
        return None
    home = world.structures.get(a.home or "")
    if home is None or not home.functional or key not in UPGRADES.get(home.design, ()):
        return None
    if home.dist(a.x, a.y) > 8 or upgrade_spot(world, home, key) is None:
        return None
    return {"do": "upgrade", "to": key, "target": home.id}


def do_upgrade(world, a: Agent, step: Dict[str, Any], s: Dict[str, Any]) -> str:
    """Rebuild a home bigger where it stands: bring what it still needs, then work on it. The home stays lived in
    all the while, and everyone living there still does when it's done."""
    from .actions import DONE, RUNNING, _goto_structure, _stockpile_with

    st = world.structures.get(s.get("home") or "")
    if st is None:
        ref = step.get("target") or step.get("site")
        st = world.structures.get(str(ref)) if ref else None
        st = st if st is not None and st.design in UPGRADES else world.structures.get(a.home or "")
        if st is None or st.design not in UPGRADES:
            return "I have no home to make bigger (build a hut first)"
        if not st.upgrade and st.id != a.home and st.design in HOME_CAP:
            return "I can only rebuild my own home bigger (or help with one that's already being rebuilt)"
        s["home"] = st.id
    if not st.functional:
        return f"the {DESIGNS[st.design].name} is in ruins: repair it first"
    old = DESIGNS[st.design].name
    if not st.upgrade and s.get("to"):  # someone else finished it while this chit was away
        s["note"] = f"The {old} is already rebuilt"
        return DONE
    if not st.upgrade:
        key, why = upgrade_target(world, a, st, step.get("to") or step.get("what"))
        if key is None:
            return why
        if upgrade_spot(world, st, key) is None:
            return f"there's no clear ground beside the {old} to make it a {DESIGNS[key].name}"
        need = salvage_needs(st.design, key)
        st.upgrade = {"to": key, "needs": dict(need), "work": 0.0, "total": DESIGNS[key].work * UPGRADE_WORK,
                      "by": {}, "tick": world.tick}
        world.dirty_struct.add(st.id)
        words = ", ".join(f"{n} {world.item_name(k)}" for k, n in need.items()) or "only work"
        whose = "their" if a.home == st.id else "a"
        world.emit("site", f"{a.name} began rebuilding {whose} {old} as a {DESIGNS[key].name} (needs {words})", 2, a.id,
                   *st.center(), design=key, structure=st.id, upgrade=True)
        a.remember(world.tick, f"I began rebuilding our {old} as a {DESIGNS[key].name}; it needs {words}", 3, "build")
    up = st.upgrade
    new = DESIGNS[up["to"]].name
    s["to"] = up["to"]
    if s.get("fetch_from"):  # a trip to the stockpile for what it still needs
        pile = world.structures.get(s["fetch_from"])
        mv = _goto_structure(world, a, s, pile) if pile else "blocked"
        if mv not in ("arrived", "blocked"):
            return RUNNING
        if mv == "arrived":
            for k in list(up["needs"]):
                take = min(up["needs"][k], pile.storage.get(k, 0))
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
        return f"couldn't reach the {old}"
    if mv != "arrived":
        return RUNNING
    for k in list(up["needs"]):
        give = min(up["needs"][k], a.inventory.get(k, 0))
        if give:
            a.remove(k, give)
            up["needs"][k] -= give
            if up["needs"][k] <= 0:
                up["needs"].pop(k)
            up["by"][a.id] = up["by"].get(a.id, 0) + give
            world.dirty_struct.add(st.id)
    if up["needs"]:
        pile = _stockpile_with(world, a, list(up["needs"]), 25)
        if pile and s.get("trips", 0) < 4 and a.free_space() > 0:
            s["trips"] = s.get("trips", 0) + 1
            s["fetch_from"] = pile.id
            s.pop("goal_sig", None)
            s["repath"] = 0
            a.path = []
            return RUNNING
        words = ", ".join(f"{n} {world.item_name(k)}" for k, n in up["needs"].items())
        s["note"] = f"The {new} still needs {words}"
        return DONE
    a.activity = f"building a {new}"
    a.emote = "🔨"
    a.emote_until = world.tick + 2
    up["work"] += a.skill_speed("building") * (1.1 if a.mood > 70 else 1.0)
    up["by"][a.id] = up["by"].get(a.id, 0) + 1
    a.practice("building", 0.3)
    if world.tick % 6 == 0:
        world.dirty_struct.add(st.id)
    if up["work"] < up["total"]:
        return RUNNING
    if not finish_upgrade(world, st, a):
        return f"something was built in the way: there's no room left to make the {old} a {new}"
    s["note"] = f"Rebuilt the {old} as a {new}!"
    return DONE


def finish_upgrade(world, st, by: Agent) -> bool:
    up = st.upgrade
    to, old = up["to"], st.design
    spot = upgrade_spot(world, st, to)
    if spot is None:
        st.upgrade = {}
        world.dirty_struct.add(st.id)
        return False
    d = DESIGNS[to]
    for cx, cy in st.cells():
        world.occupied.pop(cy * world.w + cx, None)
    st.x, st.y = spot
    st.w, st.h = d.size
    for cx, cy in st.cells():
        world.occupied[cy * world.w + cx] = st.id
    st.design, st.durability, st.ruined_at, st.completed, st.upgrade = to, 100.0, -1, world.tick, {}
    world.dirty_struct.add(st.id)
    hands = [world.agents[i] for i in up["by"] if i in world.agents] or [by]
    names = [x.name for x in hands]
    from .world import _join_names

    first = f"design:{to}" not in world.first
    world.emit("built", f"{_join_names(names)} rebuilt a {DESIGNS[old].name} as {'the first' if first else 'a'} "
                        f"{d.name}", 4 if first else 2, by.id, *st.center(), design=to, structure=st.id,
               builders=[x.id for x in hands], together=len(hands) >= 2, first=first, upgraded_from=old)
    if first:
        world.first[f"design:{to}"] = {"tick": world.tick, "by": by.id, "name": by.name}
        world.update_era()
    for x in hands:
        x.learn(f"design:{to}", "built", world.tick)
        x.made_it_work(f"design:{to}", world.tick)
        x.bump("built")
    for o in world.agents.values():
        if o.home == st.id:
            o.mood = min(100.0, o.mood + 5)
            o.remember(world.tick, f"Our {DESIGNS[old].name} is now a {d.name}, with room for {HOME_CAP[to]}", 3, "home")
    return True


# ---------------------------------------------------------------------------- the bridge
def lay_bridges(world, blk, cost) -> None:
    """A finished bridge is a walkable deck over the water (World.rebuild_block)."""
    for st in world.structures.values():
        if st.design == "bridge" and st.complete:
            for cx, cy in st.cells():
                i = cy * world.w + cx
                blk[i] = 0
                cost[i] = 1.0


def off_the_bridge(world, st) -> None:
    """A bridge crumbled away: anyone standing on it scrambles to the nearest bank."""
    cells = set(st.cells())
    for a in world.agents.values():
        if (a.x, a.y) in cells:
            pos = world.ring_scan(a.x, a.y, 4, lambda x, y, i: world.passable(x, y))
            if pos:
                a.x, a.y = pos
                a.path = []


def crossings(world, a: Agent, ox: int, oy: int, radius: int, toward: Optional[int] = None) -> List[tuple]:
    """Places near (ox, oy) where 1-3 tiles of water separate this chit's land from walkable land on the far side,
    best first: (score, x, y, w, h, far land, near bank tile, far bank tile). With `toward`, only onto that land."""
    comp = world._components()
    W = world.w
    mine = comp[a.y * W + a.x]
    out = []
    for y in range(max(0, oy - radius), min(world.h, oy + radius + 1)):
        for x in range(max(0, ox - radius), min(W, ox + radius + 1)):
            if comp[y * W + x] != mine:
                continue
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                cells = []
                cx, cy = x + dx, y + dy
                while len(cells) < BRIDGE_MAX and world.inb(cx, cy) and world.tiles[cy * W + cx] in WATER \
                        and world.block[cy * W + cx] and (cy * W + cx) not in world.occupied:
                    cells.append((cx, cy))
                    cx, cy = cx + dx, cy + dy
                if not cells or not world.inb(cx, cy) or world.block[cy * W + cx]:
                    continue
                far = comp[cy * W + cx]
                if toward is not None and far != toward:
                    continue
                deep = sum(1 for px, py in cells if world.tiles[py * W + px] == T.DEEP)
                score = max(abs(x - ox), abs(y - oy)) + 2 * len(cells) + 3 * deep + (8 if far == mine else 0)
                bx, by = min(c[0] for c in cells), min(c[1] for c in cells)
                out.append((score, bx, by, len(cells) if dx else 1, len(cells) if dy else 1, far, (x, y), (cx, cy)))
    out.sort()
    return out


def _long_way_round(world, c: tuple) -> bool:
    """Both banks are the same land: a bridge is only worth it when the walk round is long."""
    (sx, sy), end = c[6], c[7]
    path = world.find_path(sx, sy, {end}, limit=4000)
    return path is None or len(path) > max(15, 5 * (c[3] + c[4]))


def best_crossing(world, a: Agent, ox: int, oy: int, radius: int, toward: Optional[int] = None):
    mine = world._components()[a.y * world.w + a.x]
    checked = 0
    for c in crossings(world, a, ox, oy, radius, toward):
        if c[5] != mine:
            return c
        if checked < 4:  # (a path search each: only the best few)
            checked += 1
            if _long_way_round(world, c):
                return c
    return None


def land_of(world, x: int, y: int) -> Optional[int]:
    """The connected land a tile is on (or beside, for a resource on a tile a chit can't stand on)."""
    comp = world._components()
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        if world.inb(x + dx, y + dy) and comp[(y + dy) * world.w + x + dx]:
            return comp[(y + dy) * world.w + x + dx]
    return None


def build_bridge(world, a: Agent, step: Dict[str, Any], s: Dict[str, Any]) -> str:
    """Start a bridge at the nearest narrow crossing (near "near", onto the land of "toward"), or join one."""
    from .actions import DONE, _do_help, _resolve_place

    for st in world.structures_near(a.x, a.y, 12, "bridge"):
        if not st.complete and a.reflex_rest.get("unreach:" + st.id, 0) <= world.tick and world.same_land(a, st):
            s["site"] = st.id
            s["joined"] = True
            return _do_help(world, a, step, s)
    cap = step.get("_cap")
    if cap and sum(1 for x in world.structures.values() if x.design == "bridge") >= cap:
        s["note"] = "There are enough bridges already"
        return DONE
    if world.block[a.y * world.w + a.x]:
        return "I can't see a way across from here"
    ox, oy = a.x, a.y
    near = step.get("near") or step.get("at")
    if near:
        p = _resolve_place(world, a, near)
        if p:
            ox, oy = p
    toward = None
    if step.get("toward"):
        p = _resolve_place(world, a, step["toward"])
        toward = land_of(world, *p) if p and world.inb(*p) else None
    c = best_crossing(world, a, ox, oy, 12, toward)
    if c is None and (ox, oy) != (a.x, a.y):
        c = best_crossing(world, a, a.x, a.y, 12, toward)
    if c is None:
        a.reflex_rest["nobuild:bridge"] = world.tick + TICKS_PER_DAY
        return ("there's no narrow water here to bridge (1 to 3 tiles across, with land on both sides that isn't "
                "already an easy walk round)")
    x, y, w, h = c[1:5]
    st = world.place_site("bridge", x, y, a)
    st.w, st.h = w, h
    for cx, cy in st.cells():
        world.occupied[cy * world.w + cx] = st.id
    st.builders[a.id] = 0.0
    s["site"] = st.id
    need = ", ".join(f"{n} {world.item_name(k)}" for k, n in DESIGNS["bridge"].materials)
    world.emit("site", f"{a.name} started building a bridge (needs {need})", 2, a.id, *st.center(), design="bridge",
               structure=st.id)
    a.remember(world.tick, f"I started a bridge at ({st.x},{st.y}); it needs {need}", 3, "build")
    return _do_help(world, a, step, s)


def resource_sides(world, a: Agent, kind: str, radius: int = 26):
    """The nearest tile of a resource on this chit's own land, and the nearest on other land (with that land's id):
    ((dist, x, y) or None, (dist, x, y, land) or None)."""
    k = T.RES_INDEX.get(kind)
    comp = world._components()
    W = world.w
    mine = comp[a.y * W + a.x]
    own = other = None
    for y in range(max(0, a.y - radius), min(world.h, a.y + radius + 1)):
        for x in range(max(0, a.x - radius), min(W, a.x + radius + 1)):
            i = y * W + x
            if world.res_kind[i] != k or world.res_amt[i] <= 0:
                continue
            d = max(abs(x - a.x), abs(y - a.y))
            lands = {comp[(y + dy) * W + x + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                     if 0 <= x + dx < W and 0 <= y + dy < world.h} - {0}
            if mine in lands:
                if own is None or d < own[0]:
                    own = (d, x, y)
            elif lands and (other is None or d < other[0]):
                other = (d, x, y, min(lands))
    return own, other


# ---------------------------------------------------------------------------- wells, granaries, smithies, towers
# ---------------------------------------------------------------------------- mines
MINE_PER_DAY = 4  # ore a mine's seam gives back each day
MINE_SEAM = 16  # the most a seam holds at once (of each ore)
MINE_YIELD = {"ore": 1, "iron_ore": 3}  # what a seam gives back each day: MINE_PER_DAY, split by how common each ore is
MINE_ROCK = 2  # a mine is dug within this many tiles of rock or hills
PIT_PER_DAY, PIT_HOLD = 4, 16  # sand a pit gives back each day, and the most it holds


MINE_TUNNEL_REACH = 10  # a mine tunnels into rock this far from itself
MINE_TUNNEL_MAX = 40  # rock tiles one mine digs out in all
TUNNEL_ORE_NEAR = 3  # it digs towards ore: only rock with ore this close is worth tunnelling


def _mines(world) -> None:
    """The deposits near a village run out (the live worlds failed "no copper ore anywhere nearby" 5,600 times and never
    built a forge); a mine's seam fills again every day. And every day a mine digs one rock tile out towards the ore:
    all 780 deposits on the 512 island lie on rock, which chits can't walk on, so only the rock's edge could ever be
    mined. World A had none left within 120 tiles of its village while ore lay inside the rock 19 tiles away."""
    dug = False
    for s in world.structures.values():
        if s.design == "sand_pit" and s.functional and s.storage.get("sand", 0) < PIT_HOLD:
            s.storage["sand"] = min(PIT_HOLD, s.storage.get("sand", 0) + PIT_PER_DAY)
            world.dirty_struct.add(s.id)
        if s.design != "mine" or not s.functional:
            continue
        for kind, n in MINE_YIELD.items():  # (copper and iron ore: iron is the commoner, issue #4)
            if s.storage.get(kind, 0) < MINE_SEAM:
                s.storage[kind] = min(MINE_SEAM, s.storage.get(kind, 0) + n)
                world.dirty_struct.add(s.id)
        dug = _tunnel(world, s) or dug
    if dug:
        world.rebuild_block()


def _tunnel(world, s) -> bool:
    """Dig one rock tile beside walkable ground near the mine: the one nearest ore (then nearest the mine)."""
    from . import terrain as T

    tunnels = world.tunnels
    if sum(1 for sid in tunnels.values() if sid == s.id) >= MINE_TUNNEL_MAX:
        return False
    W, H = world.w, world.h
    cx, cy = (int(v) for v in s.center())
    ore = [(i % W, i // W) for y in range(max(0, cy - MINE_TUNNEL_REACH - TUNNEL_ORE_NEAR), min(H, cy + MINE_TUNNEL_REACH + TUNNEL_ORE_NEAR + 1))
           for x in range(max(0, cx - MINE_TUNNEL_REACH - TUNNEL_ORE_NEAR), min(W, cx + MINE_TUNNEL_REACH + TUNNEL_ORE_NEAR + 1))
           for i in (y * W + x,) if world.res_kind[i] == T.R_ORE and world.res_amt[i] > 0]
    if not ore:
        return False
    best = None
    for y in range(max(1, cy - MINE_TUNNEL_REACH), min(H - 1, cy + MINE_TUNNEL_REACH + 1)):
        for x in range(max(1, cx - MINE_TUNNEL_REACH), min(W - 1, cx + MINE_TUNNEL_REACH + 1)):
            i = y * W + x
            if world.tiles[i] != T.ROCK or i in tunnels or world.block[i] == 0:
                continue
            if not any(world.block[j] == 0 for j in (i - 1, i + 1, i - W, i + W)):
                continue  # only from the rock's face
            if min(max(abs(x - ox), abs(y - oy)) for ox, oy in ore) > TUNNEL_ORE_NEAR:
                continue
            d_ore = min((x - ox) ** 2 + (y - oy) ** 2 for ox, oy in ore)  # straight at it, not round the corner
            key = (d_ore, max(abs(x - cx), abs(y - cy)), i)
            if best is None or key < best:
                best = key
    if best is None:
        return False
    i = best[2]
    first = not any(sid == s.id for sid in tunnels.values())
    tunnels[i] = s.id
    world.roads.add(i)
    world.dirty_roads.add(i)
    if first:
        world.emit("tunnel", "The miners began tunnelling into the rock towards the copper ore", 3, None, i % W, i // W,
                   mine=s.id)
    return True


# ---------------------------------------------------------------------------- mills
MILL_SAND = 4  # sand a mill grinds from stone a day
SAND_SHORT = 8  # ...while the stockpiles around it hold less than this


def _mills(world) -> None:
    """Sand lies only by coasts and lakes, and the live villages had used up theirs ("no sand anywhere nearby" was
    World A's commonest failure, and there's no brick or glass without it): a mill grinds stone into sand when the
    stockpiles around it run short."""
    for s in world.structures.values():
        if s.design != "mill" or not s.functional:
            continue
        piles = [p for p in world.structures_near(s.x, s.y, 12, "stockpile") if p.design in HOME_STORES and p.functional]
        if not piles or sum(p.storage.get("sand", 0) for p in piles) >= SAND_SHORT:
            continue
        src = max(piles, key=lambda p: (p.storage.get("stone", 0), p.id))
        n = min(MILL_SAND, src.storage.get("stone", 0) - 2)  # leave a little stone
        if n <= 0:
            continue
        src.storage["stone"] -= n
        src.storage["sand"] = src.storage.get("sand", 0) + n
        world.dirty_struct.add(src.id)
        if not world.counters.get("mill_sand"):
            world.emit("mill_sand", "The mill began grinding stone into sand", 3, None, s.x, s.y)
        world.counters["mill_sand"] = world.counters.get("mill_sand", 0) + n


PIT_REACH = 30  # a mine or sand pit is sited up to this far from its builder (World.find_site), and used from as far


def mine_near(world, a: Agent, radius: int = PIT_REACH, kind: str = "ore"):
    """The nearest working mine (or, for sand, sand pit) with some in its seam that this chit can walk to; failing
    that, the nearest whose seam is out for the day, to dig deep (three times the work: a stocked mine a little
    farther came second to it, Codex #43)."""
    deep = None
    for s in world.structures_near(a.x, a.y, radius, PIT_OF[kind]):
        if s.functional and world.same_land(a, s) and a.reflex_rest.get("unreach:" + s.id, 0) <= world.tick:
            if s.storage.get(kind, 0) > 0:
                return s
            if deep is None and kind in DEEP_DIG:
                deep = s
    return deep


DEEP_DIG = {"ore": 3.0, "iron_ore": 3.0}  # a mine whose seam is dug out for the day can still be dug, this many times as slowly (#6)


PIT_OF = {"ore": "mine", "iron_ore": "mine", "sand": "sand_pit"}


def rest_mult(world, a: Agent) -> float:
    return WELL_REST if (a.y * world.w + a.x) in fx(world)["rest"] else 1.0


def growth_mult(world, farm) -> float:
    m = WELL_GROWTH if any(gap(farm, w) <= WELL_RADIUS for w in fx(world)["well"]) else 1.0
    m *= PUMP_GROWTH if pumped(world, farm) else 1.0
    return m * (AQUEDUCT_GROWTH if any(gap(farm, q) <= AQUEDUCT_RADIUS for q in fx(world)["aqueduct"]) else 1.0)


def pumped(world, farm) -> bool:
    return any(gap(farm, p) <= PUMP_RADIUS for p in fx(world)["steam_pump"])


def watered(world, farm) -> bool:
    """A farm an aqueduct or a steam pump reaches: it grows faster, and keeps growing through a drought."""
    return any(gap(farm, q) <= AQUEDUCT_RADIUS for q in fx(world)["aqueduct"]) or pumped(world, farm)


def sawn(world, x: int, y: int) -> bool:
    """Wood cut here goes to a sawmill: each log gives twice the wood."""
    return any(s.dist(x, y) <= SAW_RADIUS for s in fx(world)["sawmill"])


def powered(world, x: int, y: int) -> bool:
    return any(p.dist(x, y) <= POWER_RADIUS for p in fx(world)["power_station"])


def lamp_near(world, x: int, y: int):
    for lp in fx(world)["street_lamp"]:
        if lp.dist(x, y) <= LAMP_RADIUS:
            return lp
    return None


def study_mult(world, a: Agent) -> float:
    """Study near a great library goes twice as far."""
    return STUDY_MULT if any(g.dist(a.x, a.y) <= LIBRARY_REACH for g in fx(world)["great_library"]) else 1.0


def voyage_ticks(world) -> int:
    """How long a boat is at sea: half as long from an island with a lighthouse."""
    return 60 if fx(world)["lighthouse"] else 120


def keeps_fresh(world, pile) -> bool:
    return any(gap(pile, g) <= GRANARY_RADIUS for g in fx(world)["granary"])


SEED_KEEP, MICE_SHARE = 30, 0.1  # a store's first 30 seeds are safe; mice eat a tenth of any more each day


def _mice(world) -> None:
    """Once a day, mice get at the seed piled in a store beyond what any village sows, unless a granary keeps it."""
    eaten, where = 0, None
    for p in list(world.structures.values()):
        if p.design not in STORES or not p.functional:
            continue
        extra = p.storage.get("seeds", 0) - SEED_KEEP
        if extra <= 0 or keeps_fresh(world, p):
            continue
        n = max(1, int(extra * MICE_SHARE))
        p.storage["seeds"] -= n
        world.dirty_struct.add(p.id)
        eaten += n
        where = where or p
    if eaten >= 20 and where is not None:
        world.emit("spoiled", f"Mice got into the stores and ate {eaten} seeds nobody was going to sow", 1, None,
                   *where.center(), lost=eaten, structure=where.id, item="seeds")


def _spoil(world) -> None:
    """Once a day, food in the stockpiles rots a little: none within reach of a granary, and none of what the clay
    pots stored with it hold."""
    rng = world.rng_for("spoil")
    lost_all, worst = 0, None
    for p in list(world.structures.values()):
        if p.design not in STORES or not p.functional:  # (warehouse food never rotted)
            continue
        food = {k: n for k, n in p.storage.items() if n > 0 and (it := world.item(k)) is not None and it.food > 0}
        if not food or keeps_fresh(world, p):
            continue
        exposed = sum(food.values()) - POT_KEEPS * p.storage.get("pot", 0)
        if exposed <= 0:
            continue
        want = exposed * SPOIL_PER_DAY
        n = int(want) + (1 if rng.random() < want - int(want) else 0)
        lost = 0
        for k in sorted(food, key=lambda k: (PERISH.index(k) if k in PERISH else len(PERISH), k)):
            take = min(n - lost, p.storage.get(k, 0))
            if take:
                p.storage[k] -= take
                if p.storage[k] <= 0:
                    p.storage.pop(k)
                lost += take
            if lost >= n:
                break
        if lost:
            world.dirty_struct.add(p.id)
            if worst is None or lost > worst[0]:
                worst = (lost, p)
            lost_all += lost
    if lost_all >= 3 and worst:
        world.emit("spoiled", f"{lost_all} stored food rotted away overnight (a granary nearby would keep it)", 1, None,
                   *worst[1].center(), lost=lost_all, structure=worst[1].id)


def craft_speed(world, a: Agent, key: str) -> float:
    """Metal tools come quicker off a smithy's anvil; work at a station goes quicker with a power station near."""
    it = world.item(key)
    m = 1.0
    if it is not None and it.tool and "metal" in it.props and any(sm.dist(a.x, a.y) <= 2 for sm in fx(world)["smithy"]):
        m = SMITHY_SPEED
    r = world.recipe(key)
    if r is not None and r.station and powered(world, a.x, a.y):
        m *= POWER_SPEED
    return m


def tower_near(world, x: int, y: int):
    for tw in fx(world)["watchtower"]:
        if tw.dist(x, y) <= TOWER_RADIUS:
            return tw
    return None


def drove_off(world, tw) -> None:
    key = f"tower:{tw.id}:{world.tick // TICKS_PER_DAY}"
    if key not in world._wolf_nights:
        world._wolf_nights.add(key)
        world.emit("wolf", "The lookout on the watchtower spotted a wolf and drove it off", 2, None, *tw.center(),
                   structure=tw.id, driven_off=True)


# ---------------------------------------------------------------------------- schools and bell towers
def _school(world) -> None:
    """Children near a school pick up, now and then, a recipe one of the grown-ups around it has made work."""
    schools = fx(world)["school"]
    if not schools:
        return
    rng = world.rng_for("school")
    t = world.tick
    how = "taught" if world.flags.get("teach") else "observed"
    for sc in schools:
        near = [o for o in world.agents.values() if sc.dist(o.x, o.y) <= SCHOOL_RADIUS and o.activity != "sleeping"]
        kids = [o for o in near if o.is_child(t)]
        if not kids:
            continue
        adults = [o for o in near if not o.is_child(t)]
        for kid in kids:
            if rng.random() >= SCHOOL_P:
                continue
            opts = [(k, ad) for ad in adults for k, v in ad.knows.items()
                    if k.startswith("recipe:") and v.get("status") == "worked" and k not in kid.knows]
            if opts:
                k, ad = opts[rng.randrange(len(opts))]
                if world.learned(kid, k, how, ad):
                    kid.bump("school_lessons")


def _presses(world) -> None:
    """Once a day each printing press prints one recipe that only one or two living chits still know and no tablet
    anyone can reach holds, on a sheet of paper from a store near it, and shelves it in the nearest library."""
    from . import lore
    from .actions import village_stores
    from .world import Tablet

    presses = fx(world)["printing_press"]
    if not presses:
        return
    keep = lore.keepers(world)
    libs = [s for s in world.structures.values() if s.design in ("library", "great_library") and s.functional]
    readable = {world.tablets[t].knowledge for lib in libs for t in lib.shelf if t in world.tablets}
    readable |= {t.knowledge for t in world.tablets.values() if t.in_structure is None}
    for pr in presses:
        thin = sorted((len(ks), k) for k, ks in keep.items() if len(ks) <= 2 and k not in readable)
        if not thin:
            return
        store = next((p for p in village_stores(world, pr.x, pr.y, PRESS_REACH) if p.storage.get("paper", 0) > 0), None)
        if store is None:
            continue
        k = thin[0][1]
        store.storage["paper"] -= 1
        if not store.storage["paper"]:
            store.storage.pop("paper")
        world.dirty_struct.add(store.id)
        lib = min((x for x in libs if x.dist(pr.x, pr.y) <= 30), key=lambda x: (x.dist(pr.x, pr.y), x.id), default=None)
        tid = world._new_id("tablet")
        key = k.split(":", 1)[1]
        text = world.catalog.describe(world.recipe(key))
        tb = Tablet(tid, k, pr.id, "the printing press", world.tick, pr.x, pr.y, lib.id if lib else None, text)
        world.tablets[tid] = tb
        if lib is not None:
            lib.shelf.append(tid)
            world.dirty_struct.add(lib.id)
        readable.add(k)
        world.emit("printed", f"The printing press printed how to make {world.item_name(key)}"
                   + (" for the library" if lib else ""), 3, None, pr.x, pr.y, structure=pr.id, knowledge=k)


def walled(world, x: int, y: int):
    """The palisade whose wall (x, y) lies inside, if any."""
    for p in fx(world)["palisade"]:
        if p.dist(x, y) <= PALISADE_RADIUS:
            return p
    return None


def hall_near(world, a: Agent, radius: int = HALL_PULL):
    """The nearest working town hall on this chit's land, if one is this near."""
    halls = [h for h in fx(world)["town_hall"] if h.dist(a.x, a.y) <= radius and world.same_land(a, h)]
    return min(halls, key=lambda h: (h.dist(a.x, a.y), h.id), default=None)


def bake_mult(world, a: Agent, key: str) -> int:
    """Bread, loaves and tarts baked at a bakery come out two for one."""
    if key in BAKED and any(b.dist(a.x, a.y) <= 2 for b in fx(world)["bakery"]):
        return BAKERY_MULT
    return 1


def heal_mult(world, a: Agent) -> float:
    return HEALER_MULT if any(h.dist(a.x, a.y) <= HEALER_RADIUS for h in fx(world)["healer"]) else 1.0


def _tavern(world) -> None:
    """Evening at the tavern: those within reach drop in. Each drinks an ale from the stores near it if there is one
    (twice the cheer, and the drinkers warm to each other); without ale, a little cheer all the same."""
    from .actions import village_stores

    for tv in fx(world)["tavern"]:
        near = [o for o in world.agents.values() if tv.dist(o.x, o.y) <= TAVERN_RADIUS and not o.is_child(world.tick)]
        if len(near) < 2:
            continue
        stores = [p for p in village_stores(world, tv.x, tv.y, 12) if p.storage.get("ale", 0) > 0]
        drank = []
        for o in near:
            pile = next((p for p in stores if p.storage.get("ale", 0) > 0), None)
            if pile is not None:
                pile.storage["ale"] -= 1
                if not pile.storage["ale"]:
                    pile.storage.pop("ale")
                world.dirty_struct.add(pile.id)
                drank.append(o)
                o.mood = min(100.0, o.mood + TAVERN_MOOD + ALE_MOOD)
            else:
                o.mood = min(100.0, o.mood + TAVERN_MOOD)
        for i, o in enumerate(drank):
            for q in drank[i + 1:]:
                o.like(q.id, 0.5)
                q.like(o.id, 0.5)
        world.emit("tavern", f"{len(near)} chits spent the evening at the tavern" + (f"; {len(drank)} had an ale" if drank else ""),
                   1, None, *tv.center(), structure=tv.id, gathered=len(near), ale=len(drank))


def city_of(world, x: int, y: int):
    """The city whose town hall stands within reach of (x, y), if any."""
    from . import pioneers as PIs
    from .settlements import HALL_REACH

    for v in PIs.villages(world):
        if v.rank == "city" and v.hall in world.structures and world.structures[v.hall].dist(x, y) <= HALL_REACH + 5:
            return v
    return None


def fished(world, x: int, y: int) -> bool:
    return any(h.dist(x, y) <= HARBOUR_RADIUS for h in fx(world)["harbour"])


def _university(world) -> None:
    """Grown-ups near a university pick up, now and then, a recipe another grown-up there has made work."""
    unis = fx(world)["university"]
    if not unis:
        return
    rng = world.rng_for("university")
    t = world.tick
    how = "taught" if world.flags.get("teach") else "observed"
    for u in unis:
        near = [o for o in world.agents.values() if u.dist(o.x, o.y) <= UNI_RADIUS and o.activity != "sleeping"
                and not o.is_child(t)]
        for o in near:
            if rng.random() >= UNI_P:
                continue
            opts = sorted((k, b.id) for b in near if b is not o for k, v in b.knows.items()
                          if k.startswith("recipe:") and v.get("status") == "worked" and k not in o.knows)
            if opts:
                k, bid = opts[rng.randrange(len(opts))]
                if world.learned(o, k, how, world.agents.get(bid)):
                    o.bump("university_lessons")


def _theatre(world) -> None:
    """An evening show: everyone within reach of a theatre in better spirits, and friendlier."""
    for th in fx(world)["theatre"]:
        near = [o for o in world.agents.values() if th.dist(o.x, o.y) <= THEATRE_RADIUS]
        if len(near) < 3:
            continue
        for o in near:
            o.mood = min(100.0, o.mood + THEATRE_MOOD)
        for i, o in enumerate(near):
            for q in near[i + 1:]:
                o.like(q.id, 0.4)
                q.like(o.id, 0.4)
        world.emit("theatre", f"{len(near)} chits watched the evening show at the theatre", 2, None, *th.center(),
                   structure=th.id, gathered=len(near))


def _plaza(world) -> None:
    """Evening on the square: the chits within reach of a plaza gather for a moment, and neighbours become friends."""
    for p in fx(world)["plaza"]:
        near = [o for o in world.agents.values() if p.dist(o.x, o.y) <= PLAZA_RADIUS and not o.is_child(world.tick)]
        if len(near) < 3:
            continue
        for o in near:
            o.mood = min(100.0, o.mood + PLAZA_MOOD)
        for i, o in enumerate(near):
            for q in near[i + 1:]:
                o.like(q.id, 0.3)
                q.like(o.id, 0.3)
        world.emit("plaza", f"{len(near)} chits gathered on the town square for the evening", 1, None, *p.center(),
                   structure=p.id, gathered=len(near))


def _bell(world) -> None:
    """Morning: each bell tower rings, and the chits within earshot gather for a moment. Spirits lift and they warm
    to each other; where chits can talk, the chief (if there) tells everyone its plan."""
    for b in fx(world)["bell_tower"]:
        near = [o for o in world.agents.values() if b.dist(o.x, o.y) <= BELL_RADIUS]
        if len(near) < 2:
            continue
        for o in near:
            o.mood = min(100.0, o.mood + BELL_MOOD)
        for i, o in enumerate(near):
            for p in near[i + 1:]:
                o.like(p.id, 0.5)
                p.like(o.id, 0.5)
        chief = world.agents.get(world.leader or "")
        told = 0
        if chief is not None and chief in near and chief.objective and world.flags.get("say"):
            for o in near:
                if o is not chief and not o.objective:
                    o.objective, o.objective_since = chief.objective, world.tick
                    o.remember(world.tick, f'At the bell, Chief {chief.name} said we must: "{chief.objective}"', 3, "plan")
                    told += 1
        world.emit("bell", f"The bell tower rang and {len(near)} chits gathered"
                   + (f"; Chief {chief.name} told {told} of them the plan" if told else ""), 2, None, *b.center(),
                   structure=b.id, gathered=len(near), told=told)


# ---------------------------------------------------------------------------- what a chit sees (prompt)
def state_words(world, s, a: Agent) -> List[str]:
    """Extra words about a structure for the prompt's list of what is around."""
    out: List[str] = []
    if s.design in HOME_CAP and s.functional:
        n, cap = residents(world, s), HOME_CAP[s.design]
        out.append(f"{n} living here, room for {cap}" + (" (crowded)" if n > cap else ""))
    if s.upgrade:
        need = ", ".join(f"{n} {world.item_name(k)}" for k, n in s.upgrade.get("needs", {}).items())
        out.append(f"being rebuilt as a {DESIGNS[s.upgrade['to']].name}" + (f", still needs {need}" if need else ""))
    if s.design in STORES and s.functional and not keeps_fresh(world, s) \
            and any(n > 0 and (it := world.item(k)) is not None and it.food > 0 for k, n in s.storage.items()):
        out.append("its food slowly rots (no granary within 10 tiles)")
    if s.design == "farm" and s.functional and growth_mult(world, s) > 1.0:
        out.append("watered by a well")
    return out
