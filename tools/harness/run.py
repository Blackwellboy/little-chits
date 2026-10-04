#!/usr/bin/env python3
"""Run one N-day instinct world and print one JSON line: what it came to, plus what tools/harness/probe.py saw
(preventable deaths, stuck chits, how often each mechanism fired). ``--autopsy`` first prints, for every chit that
starved, what it was doing before it died, and examples of stuck chits; the JSON line is always the last line.

    python tools/harness/run.py SEED [--days 30] [--size 128] [--chits 18] [--culture direct] [--server DIR]
                                     [--tag TAG] [--autopsy]

``--server`` is the ``server`` directory of the tree under test (default: this repo's own), so one harness can run
two trees side by side (tools/harness/ab.py). The world runs from that directory, as the game does.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOMES = ("hut", "brick_house", "longhouse", "two_storey_house")
USEFUL = ("well", "granary", "mill", "smithy", "watchtower", "school", "bell_tower", "bridge")


def metrics(w, low: int, starved: int) -> dict:
    """The per-seed numbers the A/B tables have always shown (the old sweep3.py), read from the finished world."""
    st = w.stats()
    b = st["by_design"]
    store = {}
    for s in w.structures.values():
        for k, n in s.storage.items():
            store[k] = store.get(k, 0) + n
    civ = getattr(w, "civic", None) or {}
    try:
        from chits.sim import pioneers

        villages = len(pioneers.villages(w))
    except Exception:  # (an older tree)
        villages = -1
    c = [x.center() for x in w.structures.values()]
    spread = 0
    if c:
        cx, cy = sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c)
        d = sorted(math.hypot(p[0] - cx, p[1] - cy) for p in c)
        spread = round(d[int(len(d) * 0.9)], 1)
    return {"disc": st["discoveries"], "era": w.era()[0], "pop": st["population"], "low": min(low, len(w.agents)),
            "starved": starved, "produced": sum(sum(getattr(s, "produced", {}).values()) for s in w.structures.values()),
            "stockpile": b.get("stockpile", 0), "campfire": b.get("campfire", 0), "kiln": b.get("kiln", 0),
            "farm": b.get("farm", 0), "homes": sum(b.get(h, 0) for h in HOMES),
            "useful": sum(b.get(k, 0) for k in USEFUL),
            "food": sum(n for k, n in store.items() if (it := w.item(k)) is not None and it.food > 0),
            "copper": store.get("copper", 0), "iron": store.get("iron", 0),
            "projects": len(civ.get("done", [])), "hints": civ.get("hints_given", 0),
            "outposts": b.get("outpost", 0), "villages": villages, "spread": spread,
            "tunnels": len(getattr(w, "tunnels", {}) or {}),
            "loose": sum(n for pile in w.ground.values() for k, n in pile.items() if k != "_t")}


def run(seed: int, days: int, size: int = 128, chits: int = 18, culture: str = "direct", tag: str = ""):
    """Run the world with a Probe attached; returns (the JSON row, the probe)."""
    from chits.sim.world import World
    from probe import Probe

    w = World("A", "A", seed, culture, size, chits)
    p = Probe(w)
    low = len(w.agents)
    with p:
        for t in range(240 * days):
            w.step(p.hook)
            p.after_tick()
            if t % 240 == 0:
                low = min(low, len(w.agents))
    row = {"tag": tag, "seed": seed, "days": days, "size": size, "culture": culture}
    row.update(metrics(w, low, len(p.starved)))
    row["births"] = p.events.get("birth", 0)
    row["forgot"] = p.events.get("forgotten", 0)
    row.update(p.report())
    return row, p


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("seed", type=int)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--chits", type=int, default=18)
    ap.add_argument("--culture", default="direct")
    ap.add_argument("--server", default=str(HERE.parents[1] / "server"), help="the server dir of the tree under test")
    ap.add_argument("--tag", default="")
    ap.add_argument("--autopsy", action="store_true", help="print the starved chits' last moments and stuck chits")
    args = ap.parse_args(argv)
    server = Path(args.server).resolve()
    if not (server / "chits").is_dir():
        sys.exit(f"{server} is not a server dir (no chits/ in it)")
    sys.path[:0] = [str(server), str(HERE)]
    os.chdir(server)
    import chits

    where = Path(getattr(chits, "__file__", None) or next(iter(chits.__path__), "")).resolve()
    if server not in where.parents:  # (a chits installed in the venv would otherwise stand in for the tree under test)
        sys.exit(f"chits was imported from {where}, not from {server}")
    row, p = run(args.seed, args.days, args.size, args.chits, args.culture, args.tag)
    if args.autopsy:
        text = p.autopsy_text()
        if text:
            print(text)
    print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
