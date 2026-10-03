"""Animals (T31): deer to hunt, sheep to tame, wolves in the dark.

Everything random here draws from the world's own "animals" stream (F6), so adding animals never shifts the
weather, births or anything else that was already deterministic."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import buildings as BLD
from . import terrain as T

DEER_TILES = (T.GRASS, T.MEADOW, T.FOREST)
SHEEP_TILES = (T.GRASS, T.MEADOW)
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def targets(world) -> Dict[str, int]:
    area = world.w * world.h
    return {"deer": max(2, area // 1500), "sheep": max(1, area // 3000), "wolf": max(1, area // 6000)}


def _rng(world):
    return world.rng_for("animals")


def _tiles(world, kinds) -> List[Tuple[int, int]]:
    return [(i % world.w, i // world.w) for i, t in enumerate(world.tiles) if t in kinds and world.passable(i % world.w, i // world.w)]


def _add(world, kind: str, x: int, y: int) -> Dict[str, Any]:
    world.counters["animal"] = world.counters.get("animal", 0) + 1
    aid = f"n{world.counters['animal']}"  # not "a…": chit ids already start with "a"
    a = {"id": aid, "kind": kind, "x": x, "y": y, "hp": 10, "tame": False, "pen": ""}
    world.animals[aid] = a
    return a


def spawn(world, kind: str, n: int) -> int:
    if n <= 0:
        return 0
    rng = _rng(world)
    if kind == "wolf":
        spots = [p for p in _tiles(world, (T.FOREST,))
                 if all(max(abs(p[0] - c.x), abs(p[1] - c.y)) >= 15 for c in world.agents.values())]
    else:
        spots = _tiles(world, DEER_TILES if kind == "deer" else SHEEP_TILES)
    if not spots:
        return 0
    for _ in range(n):
        x, y = rng.choice(spots)
        _add(world, kind, x, y)
    return n


def count(world, kind: str, wild_only: bool = True) -> int:
    return sum(1 for a in world.animals.values() if a["kind"] == kind and not (wild_only and a["tame"]))


def initial(world) -> None:
    t = targets(world)
    spawn(world, "deer", t["deer"])
    spawn(world, "sheep", t["sheep"])


def daily(world) -> None:
    t = targets(world)
    for kind in ("deer", "sheep"):
        if count(world, kind) < t[kind] / 2:
            spawn(world, kind, max(1, t[kind] // 10))
    if world.season in ("autumn", "winter"):
        spawn(world, "wolf", t["wolf"] - count(world, "wolf"))
    elif world.season == "spring":
        for aid in [k for k, a in world.animals.items() if a["kind"] == "wolf"]:
            del world.animals[aid]
    # tame sheep give wool
    for a in world.animals.values():
        if a["kind"] == "sheep" and a["tame"]:
            pen = world.structures.get(a["pen"])
            if pen and pen.functional:
                pen.storage["wool"] = pen.storage.get("wool", 0) + 1
                world.dirty_struct.add(pen.id)


def _step(world, a: Dict[str, Any], dx: int, dy: int) -> None:
    nx, ny = a["x"] + dx, a["y"] + dy
    if world.passable(nx, ny):
        a["x"], a["y"] = nx, ny


def _toward(a, x, y, sign=1) -> Tuple[int, int]:
    dx = (x > a["x"]) - (x < a["x"])
    dy = (y > a["y"]) - (y < a["y"])
    if dx and dy:
        return (dx * sign, 0) if abs(x - a["x"]) >= abs(y - a["y"]) else (0, dy * sign)
    return dx * sign, dy * sign


def _near_fire(world, x: int, y: int, r: int = 4) -> bool:
    return any(s.lit and s.dist(x, y) <= r for s in world.structures_near(x, y, r + 2, "campfire"))


def move(world) -> None:
    """Every 4 ticks."""
    rng = _rng(world)
    night = world.is_night
    for a in world.animals.values():
        kind = a["kind"]
        if kind == "sheep" and a["tame"]:
            pen = world.structures.get(a["pen"])
            if pen:
                cells = list(pen.cells())
                a["x"], a["y"] = rng.choice(cells)
            continue
        if kind == "wolf" and (tw := BLD.tower_near(world, a["x"], a["y"])) is not None:
            # spotted from a watchtower: shouted and chased off, it runs from the village
            cx, cy = tw.center()
            for _ in range(2):
                _step(world, a, *_toward(a, int(cx), int(cy), -1))
            if night:
                BLD.drove_off(world, tw)
            continue
        if kind == "wolf" and night and a.get("fled") == world.tick // 240:
            _step(world, a, *rng.choice(STEPS))  # driven off: it keeps its distance for the rest of the night
            continue
        if kind == "wolf" and night:
            near = [c for c in world.agents.values() if max(abs(c.x - a["x"]), abs(c.y - a["y"])) <= 10]
            if near:
                c = min(near, key=lambda c: (max(abs(c.x - a["x"]), abs(c.y - a["y"])), c.id))
                away = _near_fire(world, c.x, c.y) or _near_fire(world, a["x"], a["y"])
                _step(world, a, *_toward(a, c.x, c.y, -1 if away else 1))
                continue
        if kind == "deer":
            near = [c for c in world.agents.values() if max(abs(c.x - a["x"]), abs(c.y - a["y"])) <= 3]
            if near:
                c = near[0]
                _step(world, a, *_toward(a, c.x, c.y, -1))
                continue
        _step(world, a, *rng.choice(STEPS))


def attacks(world) -> None:
    """Every 10 ticks at night: a wolf next to a chit out in the open bites. Never fatal."""
    if not world.is_night:
        return
    night = world.tick // 240
    for w in world.animals.values():
        if w["kind"] != "wolf" or w.get("fled") == night:
            continue
        if BLD.tower_near(world, w["x"], w["y"]) is not None or BLD.lamp_near(world, w["x"], w["y"]) is not None \
                or BLD.walled(world, w["x"], w["y"]) is not None:
            continue  # (under a watchtower's eye, or in a street lamp's light, no wolf gets close enough to bite)
        for c in world.agents.values():
            if max(abs(c.x - w["x"]), abs(c.y - w["y"])) > 1 or world.in_home(c) \
                    or BLD.walled(world, c.x, c.y) is not None:  # (a wolf just outside the wall bit those inside, Codex #47)
                continue
            if _defend(world, w, c, night):
                break
            c.health = max(10.01, c.health - 6) if c.health > 10.01 else c.health
            key = f"{c.id}:{night}"
            if key not in world._wolf_nights:
                world._wolf_nights.add(key)
                c.remember(world.tick, "A wolf attacked me in the dark", 4, "danger")
                c.set_emote("😱", world.tick, 20)
                world.emit("wolf", f"A wolf attacked {c.name} in the dark!", 3, c.id, c.x, c.y)


WEAPON_ODDS = {"spear": 0.6, "weapon": 0.85}  # the chance a chit holding one drives a wolf off (armed friends add to it)


def _defend(world, w: Dict[str, Any], c, night: int) -> bool:
    """A chit with a spear (or anyone armed close by) fights back. Wolves bit 51 chits in World B, which carried
    40 spears and never used one. Driven off, the wolf flees and keeps its distance until morning."""
    rng = _rng(world)
    armed = [o for o in world.agents.values() if max(abs(o.x - c.x), abs(o.y - c.y)) <= 3
             and (o.best_tool("spear") or o.best_tool("weapon"))]
    if not armed:
        return False
    odds = 1.0
    for o in armed:
        odds *= 1.0 - WEAPON_ODDS["weapon" if o.best_tool("weapon") else "spear"]
    if rng.random() >= 1.0 - odds:
        return False
    hero = min(armed, key=lambda o: max(abs(o.x - c.x), abs(o.y - c.y)))
    w["fled"] = night
    for _ in range(12):  # it runs a good way off
        _step(world, w, *_toward(w, hero.x, hero.y, -1))
    hero.remember(world.tick, "I drove off a wolf in the dark", 4, "danger")
    hero.practice("gathering", 0.3)
    hero.set_emote("💪", world.tick, 20)
    if hero is not c:
        c.like(hero.id, 6)
    who = hero.name if hero is c else f"{hero.name}, standing by {c.name},"
    world.emit("wolf_driven_off", f"{who} drove off a wolf with a {world.item_name(hero.best_tool('weapon') or hero.best_tool('spear'))}!",
               3, hero.id, hero.x, hero.y)
    return True


def nearest(world, x: int, y: int, kind: str, radius: int, wild: bool = True) -> Optional[Dict[str, Any]]:
    best = None
    for a in world.animals.values():
        if a["kind"] != kind or (wild and a["tame"]):
            continue
        d = max(abs(a["x"] - x), abs(a["y"] - y))
        if d <= radius and (best is None or d < best[0] or (d == best[0] and a["id"] < best[1]["id"])):
            best = (d, a)
    return best[1] if best else None
