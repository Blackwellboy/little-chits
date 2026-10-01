"""Daughter villages. Both live worlds sat at 60 chits in one village on a 512 island that was mostly empty. A village
now holds VILLAGE_CAP chits: when one is full, PARTY young adults set out to found a new village a day's walk away, with
wood, food and stone around it and no other village near. They light its first fire and build their homes there; the
world's own settlement detection (sim/settlements.py) names it when it stands. (Stopping births in a full village as
well cost 19 chits by day 30 across 12 seeds while it was the only village: a village's size only sends the pioneers
out.) All six daughter villages in the live worlds then died out with their founders: the pioneers were up to 35 days
old and rarely couples, and at the world's cap every child was born in the big village. So the party is young couples
first, the smallest villages have their children first, and a village of VILLAGE_ROOM has none while another has room."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from . import terrain as T
from .agent import TICKS_PER_DAY, Agent
from .buildings import HOMES

VILLAGE_CAP = 40  # a village this full sends pioneers out
VILLAGE_ROOM = 50  # ...and one this full has no more children while another village has room (World._births)
PARTY = 6
PARTY_AGE = 30  # pioneers are young: at 35 (of 50-70 days) the founders of all six daughter villages aged out
FAR_MIN, FAR_MAX = 35, 70  # how far from the old village the new one is sought
APART = 30  # no other building this close to the new site
START_DAY = 20
GIVE_UP_DAYS = 15  # a party that hasn't founded a village by then settles where it is


def _day(world) -> int:
    return world.tick // TICKS_PER_DAY


def villages(world):
    """sim.settlements.detect, once per tick (the new day asks for it more than once)."""
    from .settlements import detect

    memo = world.__dict__.get("_villages")  # a cache, not saved: the same tick always gives the same villages
    if memo is None or memo[0] != world.tick or memo[1] != len(world.structures):
        memo = world.__dict__["_villages"] = (world.tick, len(world.structures), detect(world))
    return memo[2]


def daily(world) -> None:
    """Called at the start of each day (World.new_day)."""
    if not world.flags.get("say"):
        return  # six chits agreeing to leave together, and where to, needs words: a silent village stays put
    em = world.civic.get("emigration")
    vs = villages(world)
    if em:
        new = next((v for v in vs if math.hypot(v.x - em["x"], v.y - em["y"]) <= 14 and v.id != em["from"]), None)
        if new is not None:
            world.civic["emigration"] = None
            world.civic.setdefault("daughters", []).append({"id": new.id, "name": new.name, "from": em["from_name"],
                                                            "day": _day(world)})
            world.emit("daughter_village", f"{new.name} was founded by pioneers from {em['from_name']}", 5, None,
                       new.x, new.y, settlement=new.id, name=new.name, mother=em["from"])
        elif _day(world) - em["day"] > GIVE_UP_DAYS:
            world.civic["emigration"] = None
            world.emit("pioneers", f"The pioneers from {em['from_name']} never founded their village", 2, None, em["x"], em["y"])
        return
    if _day(world) < START_DAY or not vs:
        return
    big = max(vs, key=lambda v: len(v.residents))
    if len(big.residents) < VILLAGE_CAP:
        return
    site = pick_site(world, big)
    if site is None:
        return
    party = _party(world, big)
    if len(party) < 3:
        return
    world.civic["emigration"] = {"x": site[0], "y": site[1], "from": big.id, "from_name": big.name,
                                 "members": [a.id for a in party], "day": _day(world)}
    for a in party:
        a.remember(world.tick, f"We set out from crowded {big.name} to found a new village at ({site[0]},{site[1]})", 5, "event")
        a.bump_rev("it set out as a pioneer")
    names = ", ".join(a.name for a in party[:-1]) + f" and {party[-1].name}"
    world.emit("pioneers", f"{big.name} is full: {names} set out to found a new village", 4, party[0].id, site[0], site[1],
               members=[a.id for a in party], mother=big.id)


def village_sizes(world) -> Tuple[Dict[str, int], int]:
    """How many chits live in each chit's village (0 for a chit outside any), and how many villages there are."""
    vs = villages(world)
    size: Dict[str, int] = {}
    for v in vs:
        for i in v.residents:
            size[i] = len(v.residents)
    return size, len(vs)


def _couple(a: Agent, b: Agent) -> bool:
    from .world import BOND_TO_BREED

    return (a.affinity.get(b.id, 0) >= BOND_TO_BREED and b.affinity.get(a.id, 0) >= BOND_TO_BREED
            and b.id not in a.parents and a.id not in b.parents and not set(a.parents) & set(b.parents))


def _party(world, village) -> List[Agent]:
    """The boldest young adults, couples first: a village of six that can't have children dies with its founders."""
    t = world.tick
    young = [world.agents[i] for i in village.residents if i in world.agents]
    young = [a for a in young if not a.is_child(t) and a.age(t) < PARTY_AGE and not a.origin
             and a.id != getattr(world, "leader", "")]
    young.sort(key=lambda a: (-(a.traits.get("curiosity", 0.5) + 1 - a.traits.get("caution", 0.5)), a.id))
    party: List[Agent] = []
    for a in young:
        if a in party or len(party) + 2 > PARTY:
            continue
        mates = [b for b in young if b is not a and b not in party and _couple(a, b)]
        if mates:
            party += [a, max(mates, key=lambda b: (a.affinity[b.id] + b.affinity[a.id], b.id))]
    party += [a for a in young if a not in party][:PARTY - len(party)]
    return party


def pick_site(world, village) -> Optional[Tuple[int, int]]:
    """A grassy spot a day's walk out on the same land, with wood, food and stone around it and nothing built near."""
    cx, cy = int(round(village.x)), int(round(village.y))
    comp = world._components()
    home = next((comp[a.y * world.w + a.x] for a in (world.agents.get(i) for i in village.residents) if a), 0)
    built = [s.center() for s in world.structures.values()]
    best = None
    for r in range(FAR_MIN, FAR_MAX + 1, 5):
        for k in range(24):
            ang = k * math.tau / 24
            x, y = int(cx + r * math.cos(ang)), int(cy + r * math.sin(ang))
            if not (9 <= x < world.w - 9 and 9 <= y < world.h - 9):  # (it looks 8 tiles about)
                continue
            i = y * world.w + x
            if world.tiles[i] not in (T.GRASS, T.MEADOW) or comp[i] != home or not world.tile_free(x, y):
                continue
            if any(abs(bx - x) < APART and abs(by - y) < APART for bx, by in built):
                continue
            seen, food = set(), 0
            for dy in range(-8, 9, 2):
                for dx in range(-8, 9, 2):
                    j = (y + dy) * world.w + x + dx
                    kind = world.res_kind[j]
                    if kind == T.R_WOOD:
                        seen.add("wood")
                    elif kind == T.R_BERRIES:
                        food += 1
                        seen.add("food")
                    elif kind == T.R_STONE:
                        seen.add("stone")
                    if world.tiles[j] == T.SHALLOW:
                        seen.add("water")
            if not {"wood", "food"} <= seen:
                continue
            score = 3 * len(seen) + 0.6 * food - 0.05 * r
            if best is None or score > best[0]:
                best = (score, x, y)
    return (best[1], best[2]) if best else None


def pioneer(world, a: Agent) -> Optional[Dict[str, Any]]:
    em = (getattr(world, "civic", None) or {}).get("emigration")
    return em if em and a.id in em["members"] else None


def builds_home_at(world, a: Agent, x: int, y: int) -> bool:
    """A pioneer building by its new village's site: a home there even though it has one back in the old village."""
    em = pioneer(world, a)
    return bool(em) and max(abs(x - em["x"]), abs(y - em["y"])) <= 12


def moves_in(world, a: Agent, home) -> bool:
    """A pioneer moves into the home it builds by the new village's site."""
    em = pioneer(world, a)
    return bool(em) and home.design in HOMES and home.dist(em["x"], em["y"]) <= 12


def scene_line(world, a: Agent) -> str:
    em = pioneer(world, a)
    if not em:
        return ""
    return (f"You are one of the pioneers who left crowded {em['from_name']} to found a new village at "
            f"({em['x']},{em['y']}): light its first fire and build your home there.")
