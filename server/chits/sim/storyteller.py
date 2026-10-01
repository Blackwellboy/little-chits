"""The storyteller (RimWorld's Cassandra, Frostpunk): every few days the world sets its village a challenge, announced
so its minds can prepare, and now and then a gift. It gives each week a story arc, and each challenge has an answer
the village can build or learn (warm homes and stored firewood, spears and watchtowers, wells and granaries).

Both worlds of a match get the same challenge on the same day (the schedule depends only on the seed and the day), and
it is applied with the same random stream in both, so a versus stays fair; different world conditions can still
change which challenge can happen. Nothing here hands out knowledge: a traveller only points at what a chit has seen.
Play games only: the runtime doesn't call it in an experiment.
"""

from __future__ import annotations

import random
import zlib
from typing import Any, Callable, Dict, List, Optional, Tuple

from .agent import TICKS_PER_DAY

FIRST_DAY = 5  # nothing before the village has found its feet
CHANCE = 0.2  # of a challenge on any day after that: about one every five days
COLD_SNAP = 0.12  # how much colder a hard winter is


def _center(world) -> Optional[Tuple[int, int]]:
    ags = list(world.agents.values())
    if not ags:
        return None
    xs = sorted(a.x for a in ags)
    ys = sorted(a.y for a in ags)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def _spot(world, rng, near: Tuple[int, int], lo: int, hi: int) -> Optional[Tuple[int, int]]:
    for _ in range(200):
        x, y = near[0] + rng.randint(-hi, hi), near[1] + rng.randint(-hi, hi)
        if max(abs(x - near[0]), abs(y - near[1])) >= lo and world.inb(x, y) and world.passable(x, y):
            return x, y
    return None


# ---------------------------------------------------------------- the challenges (each returns its announcement)
def hard_winter(world, rng) -> Optional[str]:
    if world.season != "autumn":
        return None
    # the coming winter: from now to the end of the next winter
    world.cold_until = world.tick + TICKS_PER_DAY * 6
    return "The elders smell a hard winter coming: nights will be colder than any before. Firewood, warm homes and warm clothes."


def wolf_pack(world, rng) -> Optional[str]:
    from . import animals as AN

    if world.season not in ("autumn", "winter") or getattr(world, "animals", None) is None:
        return None
    c = _center(world)
    if c is None:
        return None
    n = max(3, AN.targets(world)["wolf"] // 2)
    for _ in range(n):
        p = _spot(world, rng, c, 16, 24)
        if p:
            AN._add(world, "wolf", *p)
    return "A wolf pack has come down from the hills and circles the village. Stay near the fires, and keep your spears close."


def drought(world, rng) -> Optional[str]:
    if world.season != "summer" or not hasattr(world, "set_weather"):
        return None
    world.set_weather("drought", 2.0)
    return "The rains have stopped: a drought. Nothing will grow for days. Stored food will matter."


def sickness(world, rng) -> Optional[str]:
    ags = sorted(world.agents.values(), key=lambda a: a.id)
    if len(ags) < 6:
        return None
    for a in rng.sample(ags, max(1, len(ags) // 5)):
        a.health = max(15.0, a.health - 25)
        a.energy = max(5.0, a.energy - 30)
        a.remember(world.tick, "A sickness laid me low", 4, "danger")
    return "A sickness spreads through the village. The sick need rest, food and warmth."


def fire(world, rng) -> Optional[str]:
    homes = sorted((s for s in world.structures.values() if s.design in ("hut", "brick_house", "longhouse")
                    and s.functional), key=lambda s: s.id)
    if not homes:
        return None
    s = rng.choice(homes)
    s.durability = max(5.0, s.durability - (30 if s.design == "brick_house" else 60))
    world.dirty_struct.add(s.id)
    owner = next((a for a in world.agents.values() if a.home == s.id), None)
    return f"Fire! {owner.name + chr(39) + 's' if owner else 'A'} {s.design.replace('_', ' ')} caught light. It stands, badly burned: it needs mending."


def meteorite(world, rng) -> Optional[str]:
    c = _center(world)
    p = _spot(world, rng, c, 12, 24) if c else None
    if not p:
        return None
    world.put_ground(p[0], p[1], "meteorite", 1)
    return f"A star fell from the sky and landed at ({p[0]},{p[1]}), not far from the village! Something strange lies there."


def stranger(world, rng) -> Optional[str]:
    """A visitor draws attention to an observed property; it never grants a recipe."""
    if world.day < 20 or not world.agents or not world.flags.get("say"):
        return None
    hosts = sorted(world.agents.values(), key=lambda a: a.id)
    host = rng.choice(hosts)
    seen = sorted(k for k in host.familiar if world.item(k) and world.item(k).props)
    if not seen:
        return None
    item = rng.choice(seen)
    prop = rng.choice(list(world.item(item).props))
    note = f"A traveller wondered what I could do with {world.item_name(item)}: it is {prop}."
    host.remember(world.tick, note, 4, "wonder")
    return f"A traveller passed through and asked {host.name} to look again at {world.item_name(item)}: it is {prop}."


def bumper_harvest(world, rng) -> Optional[str]:
    if world.season not in ("spring", "summer"):
        return None
    farms = [s for s in world.structures.values() if s.design == "farm" and s.functional and s.planted]
    if len(farms) < 3:
        return None
    for s in farms:
        s.growth = 1.0
        world.dirty_struct.add(s.id)
    return f"The fields ripened all at once: a bumper harvest! {len(farms)} farms are ready to bring in."


CHALLENGES: List[Tuple[str, int, Callable]] = [
    ("hard_winter", 3, hard_winter), ("wolf_pack", 3, wolf_pack), ("drought", 2, drought), ("sickness", 2, sickness),
    ("fire", 2, fire), ("meteorite", 1, meteorite), ("stranger", 2, stranger), ("bumper_harvest", 1, bumper_harvest),
]


def today(seed: int, day: int) -> List[str]:
    """Which challenges the storyteller would try today, in order (empty on quiet days). Depends only on the seed
    and the day, so both worlds of a match are offered the same one."""
    rng = random.Random(zlib.crc32(f"story:{seed}:{day}".encode()))
    if day < FIRST_DAY or rng.random() >= CHANCE:
        return []
    kinds = [k for k, _, _ in CHALLENGES]
    weights = [w for _, w, _ in CHALLENGES]
    first = rng.choices(kinds, weights)[0]
    return [first] + [k for k in kinds if k != first]  # if the first can't happen here, the next that can


def daily(world) -> Optional[str]:
    """Once a day (the runtime calls it at dawn): end a finished challenge, maybe start a new one."""
    ch = getattr(world, "challenge", None) or {}
    if ch and world.tick >= ch.get("until", 0):
        world.challenge = {}
    if world.challenge or not world.agents:
        return None
    fns = {k: fn for k, _, fn in CHALLENGES}
    rng = random.Random(zlib.crc32(f"story-apply:{world.seed}:{world.day}".encode()))
    for kind in today(world.seed, world.day):
        text = fns[kind](world, rng)
        if text:
            world.challenge = {"kind": kind, "text": text, "day": world.day, "until": world.tick + 2 * TICKS_PER_DAY}
            c = _center(world) or (None, None)
            world.emit("storyteller", text, 5, None, c[0], c[1], challenge=kind)
            return kind
    return None
