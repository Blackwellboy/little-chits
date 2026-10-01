"""Villages are inferred from what chits built, never assigned."""

from __future__ import annotations

import zlib
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from .buildings import HOMES  # hut, brick house, longhouse, two-storey house
LINK = 8  # structures within this many tiles belong to the same cluster

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
        out.append(Settlement(sid, known.get("name") or village_name(world.seed, sid), cx, cy, ids, len(homes),
                              residents, known.get("founded", world.tick)))
    out.sort(key=lambda s: _num(s.id))
    return out
