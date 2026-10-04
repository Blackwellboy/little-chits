#!/usr/bin/env python3
"""A/B two trees over many seeds with tools/harness/run.py, and print per-seed and mean tables, the starvations (each
with its autopsy file), stuck chits, and which mechanisms never fired on each side.

    python tools/harness/ab.py BASE NEW [--seeds "42 7 99 1 2 3 4 5 6 11 12 13"] [--days 30] [--label ab]
                               [--jobs 8] [--culture direct] [--size 128] [--out harness-out]

BASE and NEW are checkouts (or their ``server`` dirs). Both sides run this harness, so an older tree is measured the
same way. Rows go to OUT/LABEL.jsonl; every run's ``--autopsy`` text to OUT/LABEL/SEED-TAG.txt.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = ["disc", "era", "pop", "low", "starved", "preventable", "stuck", "produced", "stockpile", "campfire", "farm",
        "homes", "useful", "food", "copper", "iron", "projects", "hints", "outposts", "forgot", "villages", "spread",
        "tunnels", "loose"]
SIDES = ("base", "new")


def server_dir(p: str) -> Path:
    p = Path(p).expanduser().resolve()
    return p if (p / "chits").is_dir() else p / "server"


def one(server: Path, seed: int, tag: str, args, logs: Path) -> dict:
    cmd = [sys.executable, str(HERE / "run.py"), str(seed), "--days", str(args.days), "--size", str(args.size),
           "--culture", args.culture, "--server", str(server), "--tag", tag, "--autopsy"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = logs / f"{seed}-{tag}.txt"
    out.write_text(r.stdout + (("\n--- stderr\n" + r.stderr) if r.stderr.strip() else ""))
    last = r.stdout.strip().splitlines()[-1:] or [""]
    if r.returncode or not last[0].startswith("{"):
        print(f"seed {seed} {tag} failed (exit {r.returncode}): see {out}", file=sys.stderr)
        return {"tag": tag, "seed": seed, "failed": True}
    row = json.loads(last[0])
    row["autopsy"] = str(out)
    return row


def table(by: dict) -> list:
    L = ["seed " + " ".join(f"{k[:8]:>9}" for k in KEYS)]
    tot = {t: defaultdict(float) for t in SIDES}
    for s in sorted(by):
        line = f"{s:>4} "
        for k in KEYS:
            b, n = (by[s].get(t, {}).get(k, "-") for t in SIDES)
            line += f"{str(b) + '>' + str(n):>9} "
            for t in SIDES:
                v = by[s].get(t, {}).get(k, 0)
                tot[t][k] += v if isinstance(v, (int, float)) else 0
        L.append(line)
    n = max(1, len(by))
    L.append("mean " + " ".join(f"{tot['base'][k] / n:>4.1f}>{tot['new'][k] / n:<4.1f}" for k in KEYS))
    return L


def report(rows: list) -> str:
    by = defaultdict(dict)
    for r in rows:
        by[r["seed"]][r["tag"]] = r
    L = table(by)
    L.append(f"rows {sum(1 for r in rows if not r.get('failed'))} of {2 * len(by)}")
    strip = lambda r: {k: v for k, v in r.items() if k not in ("tag", "autopsy")}
    same = [s for s in sorted(by) if all(t in by[s] for t in SIDES) and strip(by[s]["base"]) == strip(by[s]["new"])]
    L.append("identical: every seed" if len(same) == len(by) else
             f"identical: {len(same)} of {len(by)} seeds" + (f" ({' '.join(map(str, same))})" if same else ""))
    ok = [r for r in rows if not r.get("failed")]
    names = list(ok[0]["fired"]) if ok else []
    L.append("\nfired (mean per seed, base>new; * where they differ)")
    for m in names:
        b, n = ([r["fired"].get(m, 0) for r in ok if r["tag"] == t] for t in SIDES)
        mb, mn = sum(b) / max(1, len(b)), sum(n) / max(1, len(n))
        L.append(f"  {m:<18} {mb:>8.1f} > {mn:<8.1f}{' *' if b != n else ''}")
    never = {t: [m for m in names if all(r["fired"].get(m, 0) == 0 for r in ok if r["tag"] == t)] for t in SIDES}
    L.append(f"\nnever fired on base (any seed): {', '.join(never['base']) or 'none'}")
    L.append(f"never fired on new (any seed):  {', '.join(never['new']) or 'none'}")
    lost, gained = [m for m in never["new"] if m not in never["base"]], [m for m in never["base"] if m not in never["new"]]
    L.append(f"never-fired diff: fires on base only: {', '.join(lost) or 'none'}; fires on new only: "
             f"{', '.join(gained) or 'none'}")
    L.append("\nstarvations (explain each one from its autopsy file)")
    starved = [r for r in ok if r.get("starved")]
    for r in sorted(starved, key=lambda r: (r["seed"], r["tag"])):
        L.append(f"  seed {r['seed']} {r['tag']}: {r['starved']} starved, {r['preventable']} preventable  {r['autopsy']}")
    if not starved:
        L.append("  none")
    L.append("\nstuck chits")
    for r in sorted(ok, key=lambda r: (r["seed"], r["tag"])):
        if r.get("stuck"):
            L.append(f"  seed {r['seed']} {r['tag']}: {r['stuck']} chits, {r['stuck_episodes']} episodes  {r['autopsy']}")
    if not any(r.get("stuck") for r in ok):
        L.append("  none")
    return "\n".join(L)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("base")
    ap.add_argument("new")
    ap.add_argument("--seeds", default="42 7 99 1 2 3 4 5 6 11 12 13")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--label", default="ab")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--culture", default="direct")
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--out", default="harness-out")
    args = ap.parse_args(argv)
    trees = {"base": server_dir(args.base), "new": server_dir(args.new)}
    for t, p in trees.items():
        if not (p / "chits").is_dir():
            sys.exit(f"{t}: {p} has no chits/ in it")
    out = Path(args.out).expanduser().resolve()
    logs = out / args.label
    logs.mkdir(parents=True, exist_ok=True)
    jobs = [(trees[t], int(s), t) for s in args.seeds.split() for t in SIDES]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        rows = list(ex.map(lambda j: one(*j, args, logs), jobs))
    (out / f"{args.label}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(report(rows))


if __name__ == "__main__":
    main()
