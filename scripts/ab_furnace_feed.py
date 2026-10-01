#!/usr/bin/env python3
"""Paired-seed F11 benchmark: same post-F10 code, furnace feeding disabled vs enabled.

This isolates the furnace-feed behavior without comparing unrelated commits. It also records hand-craft vs
station-shift manufacturing for F30.
"""
from __future__ import annotations

import argparse, json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from chits.brain import instinct as I
from chits.brain.instinct import Instinct
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World

DEFAULT_SEEDS = [42, 7, 99, 1, 2, 3, 4, 5, 6, 11, 12, 13]


def _run(seed: int, days: int, feed: bool):
    real = I.feed_furnace_plan
    if not feed:
        I.feed_furnace_plan = lambda world, a: None
    try:
        w = World("A", "A", seed, "direct", 128, 18)
        ins = Instinct()
        def hook(world, a):
            if not a.plan:
                p = ins.plan(world, a)
                a.plan, a.goal, a.plan_source = p["steps"], p["goal"], "instinct"
        for _ in range(days * TICKS_PER_DAY):
            w.step(hook)
        people = list(w.agents.values()) + list(w.dead.values())
        produced = sum(a.stats.get("produced", 0) for a in people)
        handcrafted = 0
        for a in people:
            for k, n in a.stats.items():
                if not k.startswith("made_"):
                    continue
                key = k[5:]
                r = w.recipe(key)
                handcrafted += n * (r.qty if r is not None else 1)
        store = {}
        for s in w.structures.values():
            if not s.functional:
                continue
            for k, n in s.storage.items():
                store[k] = store.get(k, 0) + n
        food = sum(n for k, n in store.items() if (it := w.item(k)) is not None and it.food > 0)
        engine = w.first.get("recipe:engine")
        st = w.stats()
        return {
            "seed": seed, "feed": feed, "discoveries": st["discoveries"], "era": w.era()[0],
            "population": len(w.agents), "deaths": len(w.dead),
            "starvations": sum(1 for a in w.dead.values() if a.cause_of_death == "starvation"),
            "station_units": produced, "hand_units": handcrafted, "manufactured_units": produced + handcrafted,
            "food": food, "iron": store.get("iron", 0), "steel": store.get("steel", 0),
            "gear": store.get("gear", 0), "copper": store.get("copper", 0),
            "machine_age": w.era()[0] >= 8,
            "engine_day": (engine["tick"] // TICKS_PER_DAY + 1) if engine else None,
        }
    finally:
        I.feed_furnace_plan = real


def _pair(args):
    seed, days = args
    return {"seed": seed, "control": _run(seed, days, False), "feed": _run(seed, days, True)}


def _mean(rows, arm, key):
    xs = [p[arm][key] for p in rows]
    return sum(xs) / len(xs) if xs else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    ap.add_argument("--out", default="f11-ab.json")
    ns = ap.parse_args()
    seeds = [int(x) for x in ns.seeds.split(",") if x.strip()]
    with ProcessPoolExecutor(max_workers=max(1, ns.jobs)) as ex:
        rows = list(ex.map(_pair, [(s, ns.days) for s in seeds]))
    keys = ["discoveries","era","population","starvations","station_units","hand_units","manufactured_units",
            "food","iron","steel","gear","copper"]
    summary = {
        "days": ns.days, "seeds": seeds, "n": len(rows),
        "machine_age": {
            "control": sum(p["control"]["machine_age"] for p in rows),
            "feed": sum(p["feed"]["machine_age"] for p in rows),
        },
        "means": {k: {"control": _mean(rows,"control",k), "feed": _mean(rows,"feed",k)} for k in keys},
        "pairs": rows,
    }
    Path(ns.out).write_text(json.dumps(summary, indent=2))
    print(json.dumps({"days": ns.days, "seeds": seeds, "machine_age": summary["machine_age"],
                      "means": summary["means"]}, indent=2))


if __name__ == "__main__":
    main()
