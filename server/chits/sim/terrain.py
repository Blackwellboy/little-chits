"""Deterministic terrain + resource generation from a seed."""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import List, Tuple

# Tile types
DEEP, SHALLOW, SAND, GRASS, MEADOW, FOREST, HILLS, ROCK, CLAY = range(9)
TILE_NAMES = ["deep water", "shallow water", "sand", "grass", "meadow", "forest", "hills", "rock", "clay bank"]
PASSABLE = [False, False, True, True, True, True, True, False, True]
MOVE_COST = [99, 99, 1.2, 1.0, 1.0, 1.4, 1.8, 99, 1.3]

# Resource kinds stored per tile
RES = ["", "wood", "stone", "fiber", "berries", "clay", "sand", "ore", "fish"]
R_NONE, R_WOOD, R_STONE, R_FIBER, R_BERRIES, R_CLAY, R_SAND, R_ORE, R_FISH = range(9)
RES_INDEX = {n: i for i, n in enumerate(RES) if n}
RES_INDEX["iron_ore"] = RES_INDEX["ore"]  # (an ore tile's metal: World.ore_item)

# max amount, regen period in ticks (per +1), winter regen multiplier
RES_PROFILE = {
    R_WOOD: (5, 140, 0.5),
    R_STONE: (8, 500, 0.5),
    R_FIBER: (3, 60, 0.2),
    R_BERRIES: (4, 50, 0.3),
    R_CLAY: (6, 90, 0.5),
    R_SAND: (9, 30, 1.0),
    R_ORE: (6, 0, 0),
    R_FISH: (3, 70, 0.6),
}


class _Noise:
    def __init__(self, seed: int, cell: int):
        self.rng = random.Random(seed)
        self.cell = cell
        self.cache = {}
        self.seed = seed

    def _grid(self, gx: int, gy: int) -> float:
        k = (gx, gy)
        v = self.cache.get(k)
        if v is None:
            h = (gx * 374761393 + gy * 668265263 + self.seed * 2147483647) & 0xFFFFFFFF
            h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
            v = ((h ^ (h >> 16)) & 0xFFFF) / 65535.0
            self.cache[k] = v
        return v

    def at(self, x: float, y: float) -> float:
        fx, fy = x / self.cell, y / self.cell
        x0, y0 = math.floor(fx), math.floor(fy)
        tx, ty = fx - x0, fy - y0
        sx = tx * tx * (3 - 2 * tx)
        sy = ty * ty * (3 - 2 * ty)
        a = self._grid(x0, y0)
        b = self._grid(x0 + 1, y0)
        c = self._grid(x0, y0 + 1)
        d = self._grid(x0 + 1, y0 + 1)
        return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy


def _fbm(seed: int, w: int, h: int, base_cell: int, octaves: int = 4) -> List[List[float]]:
    layers = [_Noise(seed + i * 101, max(2, base_cell >> i)) for i in range(octaves)]
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            amp, tot, norm = 1.0, 0.0, 0.0
            for n in layers:
                tot += n.at(x, y) * amp
                norm += amp
                amp *= 0.5
            row.append(tot / norm)
        out.append(row)
    return out


TERRAIN_VERSION = 2  # 2: rivers (and so clay) scale with the island's area on maps bigger than 128
CHUNK_SEED_SCHEME = 1


def chunk_seed(world_seed: int, chunk_x: int, chunk_y: int, generator_version: int) -> int:
    """Collision-resistant deterministic seed for a future procedural chunk.

    The identity is a typed tuple, not arithmetic such as seed+x+y+version. A domain tag and canonical JSON make
    negative coordinates, swapped axes and generator versions unambiguous; SHA-256 then yields a stable 64-bit RNG
    seed independent of Python's process-randomized hash().
    """
    identity = ["little-chits-chunk", CHUNK_SEED_SCHEME, int(world_seed), int(chunk_x), int(chunk_y),
                int(generator_version)]
    blob = json.dumps(identity, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big", signed=False)




def river_count(w: int, h: int, version: int = TERRAIN_VERSION) -> int:
    if version < 2:
        return 3
    return max(3, round(1.5 * w * h / (128 * 128)))


def generate(seed: int, w: int, h: int, version: int = TERRAIN_VERSION) -> Tuple[bytearray, bytearray, List[int]]:
    rng = random.Random(seed ^ 0x5EED)
    elev = _fbm(seed, w, h, 32, 5)
    moist = _fbm(seed + 7777, w, h, 24, 4)
    tiles = bytearray(w * h)
    cx, cy = w / 2, h / 2
    for y in range(h):
        for x in range(w):
            dx, dy = (x - cx) / cx, (y - cy) / cy
            d = math.sqrt(dx * dx + dy * dy)
            e = elev[y][x] * 1.15 - max(0.0, d - 0.72) * 1.8 + 0.06
            elev[y][x] = e
            m = moist[y][x]
            if e < 0.27:
                t = DEEP
            elif e < 0.32:
                t = SHALLOW
            elif e < 0.355:
                t = SAND
            elif e > 0.80:
                t = ROCK
            elif e > 0.70:
                t = HILLS
            elif m > 0.56:
                t = FOREST
            elif m > 0.47:
                t = MEADOW
            else:
                t = GRASS
            tiles[y * w + x] = t

    # Rivers: walk downhill from a few high points to the sea.
    peaks = [(x, y) for y in range(4, h - 4) for x in range(4, w - 4) if tiles[y * w + x] == HILLS]
    rng.shuffle(peaks)
    for sx, sy in peaks[:river_count(w, h, version)]:
        x, y = sx, sy
        for _ in range(220):
            if tiles[y * w + x] in (DEEP,):
                break
            tiles[y * w + x] = SHALLOW
            best = None
            for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + ddx, y + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    v = elev[ny][nx] + rng.random() * 0.03
                    if best is None or v < best[0]:
                        best = (v, nx, ny)
            if best is None:
                break
            elev[y][x] += 0.2  # prevent loops
            _, x, y = best

    # Clay banks next to shallow water inland.
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            if tiles[i] in (GRASS, MEADOW, SAND) and rng.random() < 0.6:
                if any(tiles[(y + dy) * w + x + dx] == SHALLOW for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    if elev[y][x] > 0.34:
                        tiles[i] = CLAY

    res_kind = bytearray(w * h)
    res_amt = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            t = tiles[i]
            r = rng.random()
            k = R_NONE
            if t == FOREST and r < 0.62:
                k = R_WOOD
            elif t == GRASS:
                if r < 0.10:
                    k = R_FIBER
                elif r < 0.13:
                    k = R_BERRIES
                elif r < 0.15:
                    k = R_WOOD
            elif t == MEADOW:
                if r < 0.20:
                    k = R_BERRIES
                elif r < 0.50:
                    k = R_FIBER
            elif t == HILLS and r < 0.30:
                k = R_STONE
            elif t == ROCK:
                k = R_ORE if r < 0.07 else R_STONE
            elif t == CLAY:
                k = R_CLAY
            elif t == SAND and r < 0.4:
                k = R_SAND
            elif t == SHALLOW and r < 0.28:
                k = R_FISH
            res_kind[i] = k
            if k:
                mx = RES_PROFILE[k][0]
                res_amt[i] = mx if k not in (R_WOOD, R_BERRIES) else rng.randint(max(1, mx - 2), mx)
    return tiles, res_kind, res_amt


def find_spawn(tiles: bytearray, res_kind: bytearray, w: int, h: int, seed: int) -> Tuple[int, int]:
    """A grassy spot with forest, food and water within reach, near the middle."""
    best = None
    for y in range(8, h - 8, 2):
        for x in range(8, w - 8, 2):
            if tiles[y * w + x] not in (GRASS, MEADOW):
                continue
            score = 0.0
            seen = set()
            for dy in range(-8, 9, 2):
                for dx in range(-8, 9, 2):
                    j = (y + dy) * w + (x + dx)
                    t = tiles[j]
                    k = res_kind[j]
                    if k == R_WOOD:
                        seen.add("wood")
                    if k == R_BERRIES:
                        score += 0.6
                        seen.add("food")
                    if t == SHALLOW:
                        seen.add("water")
                    if k == R_STONE:
                        seen.add("stone")
                    if t == CLAY:
                        seen.add("clay")
            score += 3 * len(seen)
            # "near the middle" in proportion to the island: on a 512 map a flat 0.15/tile outweighed having
            # clay (or anything else) within reach. Maps up to 128 are unchanged.
            score -= (abs(x - w / 2) + abs(y - h / 2)) * 0.15 * min(1.0, 128 / max(w, h))
            if best is None or score > best[0]:
                best = (score, x, y)
    if best is None:
        return w // 2, h // 2
    return best[1], best[2]
