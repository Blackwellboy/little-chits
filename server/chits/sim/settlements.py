"""Villages are inferred from what chits built, never assigned."""

from __future__ import annotations

import zlib
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from .buildings import HOMES  # hut, brick house, longhouse, two-storey house
LINK = 8  # structures within this many tiles belong to the same cluster

# ranks: a village with a town hall and 20 people is a town; a town of 40 with five kinds of civic building around its
# hall and paved streets is a city. Without a hall a settlement is a hamlet or a village however big it grows.
RANKS = ("hamlet", "village", "town", "city")
HAMLET_POP, TOWN_POP, CITY_POP = 8, 20, 40
CIVIC = ("market", "library", "school", "bell_tower", "great_library", "monument", "well", "granary", "smithy", "mill",
         "plaza", "shrine", "printing_press", "lighthouse", "aqueduct", "watchtower", "tavern", "bakery", "healer",
         "tailor", "park", "fountain")
HALL_REACH = 25  # civic buildings this near the hall count towards a city
CITY_CIVIC, CITY_STREETS, STREET_REACH = 5, 30, 20  # kinds of civic building; paved tiles within STREET_REACH

_FIRST = ["Moss", "Stone", "Ember", "Willow", "Fern", "Amber", "Clay", "Reed", "Thorn", "Ash", "Brook", "Hollow",
          "Pebble", "Bramble", "Cinder", "Oak", "Maple", "Heather", "Frost", "Honey", "Copper", "Salt", "Birch", "Elder"]
_SECOND = ["brook", "hollow", "ford", "vale", "mere", "field", "ridge", "wick", "stead", "haven", "moor", "dell",
           "worth", "combe", "leigh", "ton", "burrow", "glen", "wold", "bank"]


@dataclass
class Settlement:
    id: str
    name: str
    x: float
    y: float
    structures: List[str] = field(default_factory=list)
    homes: int = 0
    residents: List[str] = field(default_factory=list)
    founded: int = 0
    rank: str = "village"
    hall: str = ""  # its town hall, the heart of a town

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["population"] = len(self.residents)
        return d


def _num(sid: str) -> int:
    digits = "".join(ch for ch in sid if ch.isdigit())
    return int(digits) if digits else 0


def village_name(seed: int, sid: str) -> str:
    h = zlib.crc32(f"{seed}:{sid}".encode())
    return _FIRST[h % len(_FIRST)] + _SECOND[(h // len(_FIRST)) % len(_SECOND)]


def streets_near(world, x: int, y: int, r: int = STREET_REACH) -> int:
    """Paved tiles within r of (x, y)."""
    w, roads = world.w, world.roads
    return sum(1 for yy in range(max(0, y - r), min(world.h, y + r + 1))
               for xx in range(max(0, x - r), min(w, x + r + 1)) if yy * w + xx in roads)


def rank_of(world, members, n: int):
    """(rank, town hall id) of a settlement with these structures and n residents."""
    halls = sorted((s for s in members if s.design == "town_hall" and s.functional), key=lambda s: _num(s.id))
    small = "hamlet" if n < HAMLET_POP else "village"
    if not halls:
        return small, ""
    hall = halls[0]
    if n < TOWN_POP:
        return small, hall.id
    kinds = {s.design for s in world.structures_near(hall.x, hall.y, HALL_REACH) if s.functional and s.design in CIVIC}
    if n >= CITY_POP and len(kinds) >= CITY_CIVIC and streets_near(world, hall.x, hall.y) >= CITY_STREETS:
        return "city", hall.id
    return "town", hall.id


def detect(world) -> List[Settlement]:
    sts = [s for s in world.structures.values() if s.complete and s.durability > 0 and s.design != "road"]
    parent = {s.id: s.id for s in sts}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(sts):
        ax, ay = a.center()
        for b in sts[i + 1:]:
            if b.dist(int(round(ax)), int(round(ay))) <= LINK:
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    parent[ra] = rb
    groups: Dict[str, List] = {}
    for s in sts:
        groups.setdefault(find(s.id), []).append(s)
    out = []
    for members in groups.values():
        homes = [s for s in members if s.design in HOMES]
        if len(members) < 3 or len(homes) < 2:
            continue
        ids = sorted((s.id for s in members), key=_num)
        sid = ids[0]
        known = world.settlements.get(sid, {})
        home_ids = {s.id for s in homes}
        residents = sorted(a.id for a in world.agents.values() if a.home in home_ids)
        cx = sum(s.center()[0] for s in members) / len(members)
        cy = sum(s.center()[1] for s in members) / len(members)
        rank, hall = rank_of(world, members, len(residents))
        if hall:  # a town's heart is its hall, not the middle of its houses
            cx, cy = world.structures[hall].center()
        out.append(Settlement(sid, known.get("name") or village_name(world.seed, sid), cx, cy, ids, len(homes),
                              residents, known.get("founded", world.tick), rank, hall))
    out.sort(key=lambda s: _num(s.id))
    return out
