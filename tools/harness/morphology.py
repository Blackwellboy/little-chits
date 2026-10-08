#!/usr/bin/env python3
"""The civilisation morphology baseline (issue #161, Phase 11): what did the world PHYSICALLY become?

Runs one instinct world (the harness's own Probe) and, at day milestones, records the built civilisation:
population, settlements and their ranks, housing capacity and occupancy, every structure by design, the
late-age/industrial/civic/educational counts, stored and loose goods, roads, transport items, power and space
infrastructure, the current age and the provenance of every age reached. Written as JSON (the receipt) and
Markdown (the reading copy) under --out.

    python tools/harness/morphology.py SEED [--days 500] [--size 256] [--chits 18] [--culture direct]
                                          [--milestones 60,120,250,500] [--out harness-out/morphology] [--tag TAG]

Read-only over the simulation: nothing here changes the world's rules, RNG or physics. The report is the
"before" (and, after the overhaul, the "after") receipt: what the UI's age label claims, next to what stands.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# what counts as which part of the built civilisation (designs that exist on main, 7381944)
INDUSTRIAL = ("kiln", "smithy", "workshop", "mill", "bakery", "sawmill", "steam_pump", "factory",
              "printing_press", "power_station", "quarry", "mine")
CIVIC = ("market", "plaza", "monument", "well", "granary", "watchtower", "bell_tower", "tavern", "healer",
         "town_hall", "shrine", "park", "aqueduct", "lighthouse", "harbour", "theatre")
EDUCATION = ("school", "library", "great_library", "university")
POWER = ("power_station", "street_lamp")
SPACE = ("launch_pad",)
TRANSPORT = ("sled", "cart", "wagon", "wheel")


def morphology(w, births: int, starved: int, low: int, day: int) -> dict:
    """The built civilisation, read from the finished/running world. Honest about what is not simulated:
    road types (roads are bare tiles; PR #156 draws their look from the age) and powered loads (household
    electricity is display-only) are recorded as such, never inferred."""
    from chits.sim.buildings import HOME_CAP
    from chits.sim import settlements
    from chits.sim.world import ERAS, CAPABILITY_AGES

    built = [s for s in w.structures.values() if s.complete]
    by_design = Counter(s.design for s in built)
    homes = {d: by_design.get(d, 0) for d in HOME_CAP}
    capacity = sum(n * HOME_CAP[d] for d, n in homes.items())

    # settlements: freshly detected (world.settlements only keeps names); read-only, nothing saved
    sts = settlements.detect(w)
    ranks = Counter(s.rank for s in sts)
    biggest = max(sts, key=lambda s: len(s.residents)) if sts else None

    # transport items: everywhere they physically are (stores, the ground, hands)
    transport = Counter()
    for s in w.structures.values():
        for k, n in s.storage.items():
            if k in TRANSPORT:
                transport[k] += n
    for pile in w.ground.values():
        for k, n in pile.items():
            if k in TRANSPORT:
                transport[k] += n
    for a in w.agents.values():
        for k, n in a.inventory.items():
            if k in TRANSPORT:
                transport[k] += n

    stored = sum(sum(s.storage.values()) for s in w.structures.values())
    food = sum(n for s in w.structures.values() for k, n in s.storage.items()
               if (it := w.item(k)) is not None and it.food > 0)

    # the age, and the provenance of every age: what earned it, who, when (knowledge mode while ERA_BY_DEEDS is off)
    idx, name = w.era()
    evidence = []
    for i, (age, key) in enumerate(ERAS):
        if not key:
            continue
        rec = w.age_record(key)
        if rec:
            deeds = getattr(w, "era_by_deeds", False) and (
                key.startswith("design:") or (getattr(w, "age_rules", 1) >= 2 and key in CAPABILITY_AGES))
            evidence.append({"age": age, "key": key, "mode": "deeds" if deeds else "knowledge",
                             "by": rec.get("name"), "tick": rec.get("tick"),
                             "day": round(rec.get("tick", 0) / 240),
                             **({"evidence": rec["evidence"]} if rec.get("evidence") else {})})

    return {
        "day": day, "tick": w.tick,
        "population": len(w.agents), "deaths": len(w.dead), "births": births, "starved": starved, "low": low,
        "generations": max([a.generation for a in w.agents.values()] or [0]),
        "age": {"index": idx, "name": name},
        "age_evidence": evidence,
        "settlements": {"count": len(sts),
                        "ranks": {r: ranks.get(r, 0) for r in ("hamlet", "village", "town", "city")},
                        "largest": ({"name": biggest.name, "rank": biggest.rank,
                                     "population": len(biggest.residents),
                                     "structures": len(biggest.structures)} if biggest else None),
                        "list": [{"name": s.name, "rank": s.rank, "population": len(s.residents),
                                  "structures": len(s.structures), "founded": s.founded} for s in sts]},
        "housing": {"homes": sum(homes.values()), "by_design": {d: n for d, n in homes.items() if n},
                    "capacity": capacity, "occupancy": round(len(w.agents) / capacity, 2) if capacity else 0.0},
        "structures": {"total": len(built), "sites": sum(1 for s in w.structures.values() if not s.complete),
                       "by_design": dict(sorted(by_design.items()))},
        "industry": {d: by_design.get(d, 0) for d in INDUSTRIAL if by_design.get(d)},
        "civic": {d: by_design.get(d, 0) for d in CIVIC if by_design.get(d)},
        "education": {d: by_design.get(d, 0) for d in EDUCATION if by_design.get(d)},
        "storage": {"stored": stored, "food": food,
                    "loose": sum(n for pile in w.ground.values() for k, n in pile.items() if k != "_t")},
        "roads": {"tiles": len(w.roads), "types": "none: roads are bare tiles; their look follows the age (PR #156)"},
        "transport_items": dict(transport),
        "power": {"stations": by_design.get("power_station", 0), "street_lamps": by_design.get("street_lamp", 0),
                  "powered_loads": "not simulated: household electricity is display-only (PR #156)"},
        "space": {"launch_pads": by_design.get("launch_pad", 0),
                  "rocket_parts": sum(n for s in w.structures.values() for k, n in s.storage.items() if k == "rocket_part")
                  + sum(n for pile in w.ground.values() for k, n in pile.items() if k == "rocket_part"),
                  "launches": w.lifetime("launch"),
                  "note": "Space Age key is design:launch_pad; ERA_BY_DEEDS/age_rules decide knowledge vs deeds"},
        "knowledge": len({k for a in w.agents.values() for k in a.knows}),
        "discoveries": len(w.first),
    }


def markdown(row: dict) -> str:
    L = [f"# Civilisation morphology — seed {row['seed']}, day {row['day']}", "",
         f"Age: **{row['age']['name']}** ({row['age']['index']}) · population **{row['population']}** "
         f"(low {row['low']}, births {row['births']}, deaths {row['deaths']}, starved {row['starved']}) · "
         f"generations {row['generations']}", ""]
    L += ["## Ages: what earned each", ""]
    for e in row["age_evidence"]:
        L.append(f"- {e['age']} ({e['mode']}): {e['by']}, day {e['day']} — `{e['key']}`")
    s = row["settlements"]
    L += ["", "## Settlements", "",
          f"{s['count']} settlements: " + ", ".join(f"{n} {r}{'s' if n != 1 else ''}"
                                                    for r, n in s["ranks"].items() if n) + "."]
    if s["largest"]:
        b = s["largest"]
        L.append(f"Largest: **{b['name']}** ({b['rank']}), {b['population']} residents, {b['structures']} structures.")
    for x in s["list"]:
        L.append(f"- {x['name']}: {x['rank']}, {x['population']} residents, {x['structures']} structures"
                 + (f" (founded day {round(x['founded'] / 240)})" if x.get("founded") else ""))
    h = row["housing"]
    L += ["", "## Housing", "",
          f"{h['homes']} homes, capacity {h['capacity']}, occupancy {h['occupancy']}. " +
          ("By design: " + ", ".join(f"{d} ×{n}" for d, n in h["by_design"].items()) if h["by_design"] else "none")]
    st = row["structures"]
    L += ["", "## Structures", "",
          f"{st['total']} standing ({st['sites']} unfinished)."]
    for part in ("industry", "civic", "education", "power", "space"):
        if row[part] and isinstance(row[part], dict) and any(isinstance(v, int) and v for v in row[part].values()):
            L.append(f"- {part}: " + ", ".join(f"{d} ×{v}" for d, v in row[part].items()
                                               if isinstance(v, int) and v))
    g = row["storage"]
    L += ["", "## Goods and roads", "",
          f"Stored {g['stored']} (food {g['food']}), loose {g['loose']}. Roads: {row['roads']['tiles']} tiles "
          f"({row['roads']['types']}).",
          f"Transport items: " + (", ".join(f"{k} ×{n}" for k, n in row["transport_items"].items())
                                  if row["transport_items"] else "none") + ".",
          f"Knowledge {row['knowledge']}, discoveries {row['discoveries']}.", ""]
    return "\n".join(L)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("seed", type=int)
    ap.add_argument("--days", type=int, default=500)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--chits", type=int, default=18)
    ap.add_argument("--culture", default="direct")
    ap.add_argument("--milestones", default="60,120,250,500")
    ap.add_argument("--out", default=str(HERE.parents[1] / "harness-out" / "morphology"))
    ap.add_argument("--tag", default="")
    ap.add_argument("--server", default=str(HERE.parents[1] / "server"))
    args = ap.parse_args(argv)
    milestones = sorted({int(x) for x in args.milestones.split(",") if x.strip()})
    server = Path(args.server).resolve()
    if not (server / "chits").is_dir():
        sys.exit(f"{server} is not a server dir (no chits/ in it)")
    sys.path[:0] = [str(server), str(HERE)]
    import os
    os.chdir(server)
    import chits

    where = Path(getattr(chits, "__file__", None) or next(iter(chits.__path__), "")).resolve()
    if server not in where.parents:
        sys.exit(f"chits was imported from {where}, not from {server}")

    from chits.sim.world import World
    from probe import Probe

    w = World("A", "A", args.seed, args.culture, args.size, args.chits)
    p = Probe(w)
    low = len(w.agents)
    samples = []
    out = Path(args.out) / ((f"{args.tag}-" if args.tag else "") + f"seed{args.seed}-size{args.size}")
    out.mkdir(parents=True, exist_ok=True)
    with p:
        for t in range(240 * args.days):
            w.step(p.hook)
            p.after_tick()
            low = min(low, len(w.agents))
            if (t + 1) % 240 == 0:
                day = (t + 1) // 240
                if day in milestones:
                    row = {"seed": args.seed, "size": args.size, "culture": args.culture, "tag": args.tag,
                           "taken": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           **morphology(w, p.events.get("birth", 0), len(p.starved), low, day)}
                    samples.append(row)
                    (out / f"day{day:04d}.json").write_text(json.dumps(row, indent=2, sort_keys=True))
                    (out / f"day{day:04d}.md").write_text(markdown(row))
                    print(f"day {day}: pop {row['population']}, age {row['age']['name']}, "
                          f"settlements {row['settlements']['count']}, structures {row['structures']['total']}",
                          flush=True)
    (out / "morphology.json").write_text(json.dumps(
        {"seed": args.seed, "size": args.size, "days": args.days, "culture": args.culture, "tag": args.tag,
         "milestones": milestones, "samples": samples}, indent=2, sort_keys=True))
    print(f"wrote {out}/morphology.json ({len(samples)} milestones)", flush=True)


if __name__ == "__main__":
    main()
