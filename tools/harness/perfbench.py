#!/usr/bin/env python3
"""#161 population/performance benchmark: frozen synthetic worlds (pure performance, not demographics).

One child process per (size, population, layout, repeat): builds ONE developed world, measures it, prints
one JSON object (summaries AND raw samples, so a p95 can be recomputed), exits — no shared allocator arenas.
The parent runs the matrix (size 256+512 × 60/100/150/250 × dense, plus distributed at 150/250 × repeats)
and collects: harness-out/perfbench/<name>.json (everything) and harness-out/perfbench.jsonl (summaries).

Benchmark construction is held to invariants, loudly (a ConstructionError, never a silent malformed world):
  - the dense anchor is the founders' centroid resolved to real buildable land (never the geometric map
    centre, which on a 512 island can be water); distributed resolves each quadrant centre the same way,
    and the four anchors must stay far enough apart to be separate settlements (recorded, with distances)
  - actual population == requested target (the game's own hold-back, World.cap, freezes it)
  - housing capacity >= 1.2x the target, every required infrastructure design >= 1, road_tiles > 0
  - no incomplete construction sites (leftovers of the warm-up are completed by the same authoritative
    path, and counted), no ruined structures, before any timing starts
  - a deterministic morphology fingerprint (size, target, layout, seed, anchors, structures by design,
    housing, roads, settlements) proves repeats benchmark equivalent worlds

Measured, p50/p95(/p99/mean/max where noted), never one timing:
  1. simulation tick cost (LAST, after every read-only family: instinct minds, no model, no network)
  2. settlement detection (settlements.detect, uncached, 30 reps)
  3. pathfinding (World.find_path, 100 seeded valid pairs: short / mid / cross-map, success + lengths)
  4. memory (VmRSS current + ru_maxrss peak, method recorded)
  5. serialization: World.to_dict() and its JSON encoding, separately
  6. API: views.snapshot() and its JSON encoding, separately
  7. renderer: not measured by headless perfbench (display-only, #156; the web client needs its own)

Synthetic population (World(n_agents=N)) is correct HERE and only here: these worlds are frozen benches,
not demographic simulations — do not read birth/survival balance from them.

    python tools/harness/perfbench.py                # the full matrix (parent)
    python tools/harness/perfbench.py --child --size 512 --target 250 --layout dense --repeat 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import statistics as st
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

BASE_INFRA = ("stockpile", "granary", "well", "farm", "smithy", "watchtower", "school", "kiln")
BIG_INFRA = ("theatre", "university", "printing_press", "steam_pump", "sawmill", "factory",
             "power_station", "street_lamp")  # (the late-age set; a big town also gets 6 lamps, 1 suffices)


class ConstructionError(RuntimeError):
    """The benchmark world could not be built to its morphology invariants: no timings are produced."""


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0.0


def summ(xs):
    return {"p50": round(pct(xs, 0.5), 3), "p95": round(pct(xs, 0.95), 3), "max": round(max(xs), 3)} if xs else {}


# --------------------------------------------------------------------- the frozen world
def _put(w, a, design, x, y, r, failures):
    """Place+complete a design near (x, y), widening the search until it fits. Returns the structure or
    None, recording every failure with its reason (never silently: the invariants judge them)."""
    for rad in (r, 30, 60, 120):
        try:
            spot = w.find_site(design, x, y, rad)
            if spot is not None:
                s = w.place_site(design, *spot, a)
                w.complete_structure(s, a)
                return s
        except Exception as e:  # (a placement problem is recorded, then the wider search may still fit)
            failures.append({"design": design, "radius": rad, "reason": str(e)[:120]})
    failures.append({"design": design, "radius": r, "reason": "no buildable spot anywhere within 120 tiles"})
    return None


def _resolve_anchor(w, a, x, y, failures):
    """A known-passable civilisation anchor: the first store that actually stands at/near (x, y)."""
    s = _put(w, a, "stockpile", x, y, 0, failures)
    if s is None:
        raise ConstructionError(f"no buildable land near ({x}, {y}): nowhere to anchor a district")
    return (s.x, s.y)


def furnish(w, target, layout):
    """A developed civilisation: 1.2-1.5x housing (apartments weighted in big towns), the required
    infrastructure, power in the big ones, and real roads (the authoritative way: a completed road
    structure dissolves into world.roads). Construction is NOT timed. Returns the construction morphology;
    raises ConstructionError when an invariant cannot be met."""
    from chits.sim.buildings import HOME_CAP

    a = next(iter(w.agents.values()))
    big = target >= 150
    failures: list = []
    if layout == "dense":
        xs = [ag.x for ag in w.agents.values()]
        ys = [ag.y for ag in w.agents.values()]
        intended = [(round(sum(xs) / len(xs)), round(sum(ys) / len(ys)))]  # (the founders' centroid)
        shares = [target]
    else:  # distributed: four developed districts, one per quadrant, each resolved to real land
        intended = [(w.w // 4, w.h // 4), (3 * w.w // 4, w.h // 4),
                    (w.w // 4, 3 * w.h // 4), (3 * w.w // 4, 3 * w.h // 4)]
        shares = [target // 4] * 3 + [target - 3 * (target // 4)]
    anchors = [_resolve_anchor(w, a, x, y, failures) for x, y in intended]
    inter = [max(abs(p[0] - q[0]), abs(p[1] - q[1])) for i, p in enumerate(anchors) for q in anchors[i + 1:]]
    if layout == "distributed" and inter and min(inter) < 30:  # (pioneers.APART: nearer would be one settlement)
        raise ConstructionError(f"distributed anchors {anchors} would merge (min apart {min(inter)} < 30)")

    infra_needed = Counter()
    for (ax, ay), want in zip(anchors, shares):
        # homes: a big town grows up, not out (apartments, then two-storeys, then longhouses)
        homes = 0
        while sum(HOME_CAP.get(s.design, 0) for s in w.structures.values()
                  if s.complete and max(abs(s.x - ax), abs(s.y - ay)) <= 40) < int(want * 1.35) + 6:
            design = (("apartment", "two_storey_house", "longhouse", "brick_house") if big
                      else ("longhouse", "two_storey_house", "brick_house", "hut"))[homes % 4]
            ring = homes % 10
            if _put(w, a, design, ax + (ring % 5 - 2) * 4, ay + (ring // 5 - 1) * 4, 14, failures) is not None:
                homes += 1
            if homes > 80:  # (the capacity invariant below judges, but the loop must always end)
                break
        # infrastructure: every required design at least once in every district
        for i, design in enumerate(BASE_INFRA + (BIG_INFRA if big else ())):
            if _put(w, a, design, ax + (i % 6 - 3) * 3, ay + (i // 6 - 1) * 3, 12, failures) is not None:
                infra_needed[design] += 1
        # roads: paved corridors through the district, one tile at a time, only where the land is free
        for dx, dy in ((0, 0), (6, 0), (0, 6), (-6, 0), (0, -6)):
            for step in range(-10, 11):
                x, y = (ax + dx, ay + step) if dx == 0 else (ax + step, ay + dy)
                i = y * w.w + x
                if not (0 <= x < w.w and 0 <= y < w.h) or i in w.roads or i in w.occupied:
                    continue
                try:
                    s = w.place_site("road", x, y, a)
                    w.complete_structure(s, a)
                except Exception as e:
                    failures.append({"design": "road", "radius": 0, "reason": f"({x},{y}): {str(e)[:100]}"})

    # ---- the construction invariants, judged before any timing (loudly)
    by_design = Counter(s.design for s in w.structures.values() if s.complete)
    housing = sum(n * HOME_CAP.get(d, 0) for d, n in by_design.items() if d in HOME_CAP)
    if housing < 1.2 * target:
        raise ConstructionError(f"housing capacity {housing} < 1.2x{target} (placement failures: {failures[-3:]})")
    missing = [d for d in (BASE_INFRA + (BIG_INFRA if big else ())) if infra_needed[d] == 0]
    if missing:
        raise ConstructionError(f"required infrastructure never stood: {missing} (failures: {failures[-3:]})")
    if not w.roads:
        raise ConstructionError(f"no roads were paved (placement failures: {failures[-3:]})")
    if any(not s.complete for s in w.structures.values()):
        raise ConstructionError("incomplete construction sites after furnish")
    if any(s.ruined for s in w.structures.values()):
        raise ConstructionError("ruined structures in the freshly built world")
    return {"anchors": [list(p) for p in anchors], "inter_anchor_chebyshev": inter,
            "shares": shares, "by_design": dict(by_design), "housing_capacity": housing,
            "road_tiles": len(w.roads), "placement_failures": failures}


def child(size, target, layout, repeat, seed, warm_days, measure_ticks):
    sys.path[:0] = [str(REPO / "server"), str(HERE)]
    os.chdir(REPO / "server")
    import chits  # noqa: F401 (the tree under test)

    from chits.brain.instinct import Instinct
    from chits.sim import settlements as SETT
    from chits.sim.buildings import HOME_CAP
    from chits.sim.world import World
    from chits.views import snapshot

    w = World("A", "A", seed, "direct", size, target)
    w.cap = target  # (the game's own hold-back: the bench population stays exactly its target)
    morph = furnish(w, target, layout)
    brain = Instinct()

    def hook(world, a) -> None:  # (the instinct A/B hook, without the probe's bookkeeping)
        if not a.plan:
            p = brain.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    for _ in range(240 * warm_days):  # warm: placements, hunger, traffic reach a steady state
        w.step(hook)

    # the warm-up may have left sites a chit began: finish them by the authoritative path, then judge
    forced = 0
    for s in [s for s in w.structures.values() if not s.complete]:
        w.complete_structure(s, next(a for a in w.agents.values() if a.id == s.founder) if s.founder in w.agents
                             else next(iter(w.agents.values())))
        forced += 1
    if len(w.agents) != target:
        raise ConstructionError(f"population {len(w.agents)} != requested {target} after the warm-up")
    if any(not s.complete for s in w.structures.values()) or any(s.ruined for s in w.structures.values()):
        raise ConstructionError("the frozen start still has incomplete or ruined structures")

    # ---- the frozen start: what every family hereafter describes, and its deterministic identity
    by_design = Counter(s.design for s in w.structures.values() if s.complete)
    housing = sum(n * HOME_CAP.get(d, 0) for d, n in by_design.items() if d in HOME_CAP)
    n_settlements = len(SETT.detect(w))
    fingerprint = hashlib.sha256(json.dumps(
        {"size": size, "target": target, "layout": layout, "seed": seed, "pop": len(w.agents),
         "anchors": morph["anchors"], "by_design": dict(by_design), "housing_capacity": housing,
         "road_tiles": len(w.roads), "settlements": n_settlements}, sort_keys=True).encode()).hexdigest()[:16]

    # ---- read-only families first, the tick benchmark LAST (the state it describes is still the frozen one)
    det_ms = [(_t0 := time.perf_counter(), SETT.detect(w), (time.perf_counter() - _t0) * 1000)[2] for _ in range(30)]

    import random
    rng = random.Random(seed * 1000 + target)
    open_tiles = [(x, y) for x in range(0, w.w, 3) for y in range(0, w.h, 3) if not w.block[y * w.w + x]]
    pairs = []
    while len(pairs) < 100:  # stratified: short / mid / long, every endpoint passable, all fixed before timing
        (sx, sy), (gx, gy) = rng.choice(open_tiles), rng.choice(open_tiles)
        d = abs(sx - gx) + abs(sy - gy)
        cls = "short" if d <= 12 else "mid" if d <= 60 else "long"
        want = 40 if cls == "short" else 30
        if sum(1 for (c, _) in pairs if c == cls) < want:
            pairs.append((cls, ((sx, sy), (gx, gy))))

    path_ms, path_len, path_cls = [], [], {"short": [], "mid": [], "long": []}
    for _cls, ((sx, sy), (gx, gy)) in pairs:
        t0 = time.perf_counter()
        p = w.find_path(sx, sy, {(gx, gy)})
        ms = (time.perf_counter() - t0) * 1000
        path_ms.append(ms)
        if p is not None:
            path_len.append(len(p))
            path_cls[_cls].append(ms)

    todict_ms, tojson_ms, snap_ms, snapjson_ms, save_bytes, snap_bytes = [], [], [], [], 0, 0
    for _ in range(5):
        t0 = time.perf_counter()
        d = w.to_dict()
        todict_ms.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        save_bytes = len(json.dumps(d, default=str))
        tojson_ms.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        sv = snapshot(w)
        snap_ms.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        snap_bytes = len(json.dumps(sv, default=str))
        snapjson_ms.append((time.perf_counter() - t0) * 1000)

    with open("/proc/self/status") as f:  # (method: VmRSS current + ru_maxrss peak of THIS child)
        vmrss = next(int(l.split()[1]) / 1024 for l in f if l.startswith("VmRSS:"))

    agents0, structs0 = len(w.agents), len(w.structures)
    tick_ms = []
    t_all = time.perf_counter()
    for _ in range(measure_ticks):
        t0 = time.perf_counter()
        w.step(hook)
        tick_ms.append((time.perf_counter() - t0) * 1000)
    tick_wall = time.perf_counter() - t_all

    try:
        r1 = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True, timeout=10)
        sha = (r1.stdout or "").strip()
        r2 = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "server"],
                            capture_output=True, text=True, timeout=10)
        if (r2.stdout or "").strip():
            sha += "+dirty"
    except Exception:
        sha = "unknown"

    return {
        "base_sha": sha, "python": sys.version.split()[0], "seed": seed, "size": size, "target": target,
        "pop": len(w.agents), "layout": layout, "repeat": repeat, "synthetic_population": True,
        "morphology_fingerprint": fingerprint, "anchors": morph["anchors"],
        "inter_anchor_chebyshev": morph["inter_anchor_chebyshev"],
        "by_design": by_design, "housing_capacity": housing, "road_tiles": len(w.roads),
        "settlements": n_settlements, "construction_placement_failures": morph["placement_failures"],
        "warm_sites_force_completed": forced,
        "agents_start": agents0, "agents_end": len(w.agents),
        "structures_start": structs0, "structures_end": len(w.structures),
        "tick_ms": {"p50": round(pct(tick_ms, 0.5), 3), "p95": round(pct(tick_ms, 0.95), 3),
                    "p99": round(pct(tick_ms, 0.99), 3), "mean": round(st.mean(tick_ms), 3),
                    "max": round(max(tick_ms), 3), "total_s": round(tick_wall, 2), "n": len(tick_ms)},
        "detect_ms": summ(det_ms), "path_ms": summ(path_ms),
        "path_success": f"{len(path_len)}/{len(pairs)}",
        "path_len": {"p50": round(pct(path_len, 0.5), 1), "p95": round(pct(path_len, 0.95), 1),
                     "max": max(path_len) if path_len else 0},
        "path_ms_short": summ(path_cls["short"]), "path_ms_mid": summ(path_cls["mid"]),
        "path_ms_long": summ(path_cls["long"]),
        "todict_ms": summ(todict_ms), "tojson_ms": summ(tojson_ms), "save_json_mb": round(save_bytes / 1e6, 2),
        "snapshot_ms": summ(snap_ms), "snapjson_ms": summ(snapjson_ms),
        "snapshot_json_mb": round(snap_bytes / 1e6, 2),
        "memory": {"method": "VmRSS_current+ru_maxrss_peak(child)", "rss_mb": round(vmrss, 1),
                   "peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)},
        "renderer": "not measured by headless perfbench",
        "samples": {"tick_ms": [round(x, 3) for x in tick_ms], "detect_ms": [round(x, 3) for x in det_ms],
                    "path_ms": [round(x, 3) for x in path_ms], "todict_ms": [round(x, 3) for x in todict_ms],
                    "tojson_ms": [round(x, 3) for x in tojson_ms], "snapshot_ms": [round(x, 3) for x in snap_ms],
                    "snapjson_ms": [round(x, 3) for x in snapjson_ms]},
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--target", type=int, default=60)
    ap.add_argument("--layout", default="dense", choices=("dense", "distributed"))
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--warm-days", type=int, default=1)
    ap.add_argument("--measure-ticks", type=int, default=480)
    ap.add_argument("--sizes", default="256,512")
    ap.add_argument("--targets", default="60,100,150,250")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args(argv)

    if args.child:
        print(json.dumps(child(args.size, args.target, args.layout, args.repeat, args.seed,
                               args.warm_days, args.measure_ticks)), flush=True)
        return

    out = REPO / "harness-out" / "perfbench"
    out.mkdir(parents=True, exist_ok=True)
    sizes = [int(s) for s in args.sizes.split(",")]
    targets = [int(t) for t in args.targets.split(",")]
    cells = [(sz, tg, "dense", r) for sz in sizes for tg in targets for r in range(1, args.repeats + 1)]
    cells += [(sz, tg, "distributed", r) for sz in sizes for tg in (150, 250)
              if tg in targets for r in range(1, args.repeats + 1)]

    def run(cell) -> dict:
        sz, tg, lay, r = cell
        name = f"size{sz}-pop{tg}-{lay}-r{r}"
        p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", "--size", str(sz),
                            "--target", str(tg), "--layout", lay, "--repeat", str(r), "--seed", "42",
                            "--measure-ticks", str(args.measure_ticks)],
                           capture_output=True, text=True, timeout=900)
        (out / f"{name}.json").write_text(p.stdout.strip() or (p.stderr or ""))
        if p.returncode != 0:
            return {"name": name, "error": (p.stderr or "")[-400:]}
        row = json.loads(p.stdout)
        assert isinstance(row, dict)
        row["name"] = name
        return row

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        rows = list(ex.map(run, cells))
    ok = [r for r in rows if "error" not in r]
    with (REPO / "harness-out" / "perfbench.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if k != "samples"}) + "\n")
    fps = {r.get("morphology_fingerprint") for r in ok}
    print(f"{len(ok)}/{len(rows)} cells ok, {len(fps)} distinct morphology fingerprints; "
          f"summaries: harness-out/perfbench.jsonl; raw: {out}/")
    for r in ok:
        t, d, p = r["tick_ms"], r["detect_ms"], r["path_ms"]
        print(f"{r['name']:<28} fp={r['morphology_fingerprint']} pop={r['pop']:>3} struct={r['structures']:>3} "
              f"roads={r['road_tiles']:>3} tick={t['p50']:>7.2f}/{t['p95']:>7.2f}/{t['p99']:>7.2f}ms "
              f"detect={d['p50']:>6.2f}ms path={p['p50']:>6.1f}/{p['p95']:>6.1f}ms({r['path_success']}) "
              f"save={r['todict_ms']['p50']:>5.1f}+{r['tojson_ms']['p50']:>5.1f}ms/{r['save_json_mb']}MB "
              f"snap={r['snapshot_ms']['p50']:>5.1f}+{r['snapjson_ms']['p50']:>5.1f}ms/{r['snapshot_json_mb']}MB "
              f"rss={r['memory']['rss_mb']:>5.1f}MB")
    for r in rows:
        if "error" in r:
            print(f"{r['name']}: ERROR {r['error']}")


if __name__ == "__main__":
    main()