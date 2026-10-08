#!/usr/bin/env python3
"""#161 population diagnostic: run one world (control or uncapped tree) and record, daily,
population, births, deaths (by cause), starvation, housing capacity/occupancy, food, settlements,
tick time and memory. One JSON line per day, plus a final summary line."""
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", type=int)
    ap.add_argument("--days", type=int, default=250)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--chits", type=int, default=18)
    ap.add_argument("--server", default=str(HERE.parents[1] / "server"))
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)

    server = Path(args.server).resolve()
    if not (server / "chits").is_dir():
        sys.exit(f"{server} is not a server dir (no chits/ in it)")
    sys.path[:0] = [str(server), str(HERE)]
    os.chdir(server)
    import chits
    where = Path(getattr(chits, "__file__", None) or next(iter(chits.__path__), "")).resolve()
    if server not in where.parents:
        sys.exit(f"chits was imported from {where}, not from {server}")

    from chits.sim.world import World
    from chits.sim import settlements as SETT
    from chits.sim.buildings import HOME_CAP
    from probe import Probe

    w = World("A", args.tag or "A", args.seed, "direct", args.size, args.chits)
    p = Probe(w)
    low = len(w.agents)
    tick_ms = []
    detect_ms = []
    with p:
        for day in range(args.days):
            t0 = time.perf_counter()
            for _ in range(240):
                w.step(p.hook)
                p.after_tick()
                low = min(low, len(w.agents))
            tick_ms.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            sts = SETT.detect(w)
            detect_ms.append((time.perf_counter() - t0) * 1000)
            homes = [s for s in w.structures.values() if s.complete and s.design in HOME_CAP]
            cap = sum(HOME_CAP[s.design] for s in homes)
            store = {}
            for s in w.structures.values():
                for k, n in s.storage.items():
                    store[k] = store.get(k, 0) + n
            food = sum(n for k, n in store.items() if (it := w.item(k)) is not None and it.food > 0)
            deaths = p.events.get("death", 0)
            row = {"tag": args.tag, "seed": args.seed, "day": day + 1, "pop": len(w.agents),
                   "births": p.events.get("birth", 0), "deaths": deaths,
                   "starved": len(p.starved), "preventable": sum(1 for s in p.starved if s["preventable"]),
                   "homes": len(homes), "housing_cap": cap,
                   "occupancy": round(len(w.agents) / cap, 2) if cap else 0.0,
                   "food_stored": food, "loose": sum(n for pile in w.ground.values() for k, n in pile.items() if k != "_t"),
                   "settlements": len(sts), "largest_pop": max((len(s.residents) for s in sts), default=0),
                   "ranks": sorted(s.rank for s in sts),
                   "structures": len(w.structures), "era": w.era()[0],
                   "tick_ms_day": round(tick_ms[-1], 1), "detect_ms": round(detect_ms[-1], 2),
                   "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()