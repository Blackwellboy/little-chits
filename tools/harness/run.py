#!/usr/bin/env python3
"""Run one N-day instinct world and print one JSON line: what it came to, plus what tools/harness/probe.py saw
(preventable deaths, stuck chits, how often each mechanism fired). ``--autopsy`` first prints, for every chit that
starved, what it was doing before it died, and examples of stuck chits; the JSON line is always the last line.

    python tools/harness/run.py SEED [--days 30] [--size 128] [--chits 18] [--culture direct] [--server DIR]
                                     [--tag TAG] [--autopsy] [--mind scripted|URL [--style cascade] [--model-only] ...]

``--mind`` drives the chits through the game's Mind instead (mindrun.py): ``scripted`` is the scripted model
(scripted.py, deterministic, no GPU), a URL is a real OpenAI-compatible server. Never a real server unless given one.
``--model-only`` (a diagnostic) takes instinct out of a --mind run: no menu, no fallback and no body reflexes.

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
    # issue #161: what the late ages physically stand on, and when each was truly earned (the A/B judges the
    # label, not only the fate: a lower era under deeds can be the old label losing fake credit)
    ages = {}
    for name, key in (("machine_day", "recipe:engine"), ("electric_day", "recipe:dynamo"),
                      ("space_day", "design:launch_pad")):
        rec = w.age_record(key)
        if rec:
            ages[name] = round(rec.get("tick", 0) / 240)
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
            "loose": sum(n for pile in w.ground.values() for k, n in pile.items() if k != "_t"),
            "machines": sum(b.get(k, 0) for k in ("steam_pump", "sawmill", "factory")),
            "power_stations": b.get("power_station", 0), "street_lamps": b.get("street_lamp", 0),
            "launch_pads": b.get("launch_pad", 0), "launches": w.lifetime("launch"),
            "structures": len(w.structures), "stored": sum(store.values()),
            "settlements": len(getattr(w, "settlements", {}) or {}),
            **ages}


def world_rules(rules):
    """The tree under test's WorldRules for a rules object (None: the world's default, as before rules). Anything else
    that isn't a rules object (false, 0, []) is refused by WorldRules, never read as the default (Codex on #137)."""
    if rules is None:
        return {}
    from chits.sim.rules import WorldRules  # (a tree from before world rules has none: asking for rules there fails)

    return {"rules": WorldRules.from_dict(rules)}


def run(seed: int, days: int, size: int = 128, chits: int = 18, culture: str = "direct", tag: str = "",
        mind: str = "", rules=None, **mind_opts):
    """Run the world with a Probe attached; returns (the JSON row, the probe). With ``mind`` ("scripted" or a server
    URL) the chits are driven through the game's Mind instead of instinct (mindrun.py): the row gains a "mind" section
    and the probe a ``.mind`` (the ModelProbe)."""
    from chits.sim.world import World
    from probe import Probe

    report = None
    if mind:
        from mindrun import run_world

        w, p, mp, low, report = run_world(seed, days, size, chits, culture, mind, rules=rules, **mind_opts)
        p.mind = mp
    else:
        w = World("A", "A", seed, culture, size, chits, **world_rules(rules))
        p = Probe(w)
        p.mind = None
        low = len(w.agents)
        with p:
            for t in range(240 * days):
                w.step(p.hook)
                p.after_tick()
                low = min(low, len(w.agents))  # (every tick: a death and a birth between daily samples hid a dip)
    row = {"tag": tag, "seed": seed, "days": days, "size": size, "culture": culture,
           **({"rules": rules} if rules is not None else {})}
    row.update(metrics(w, low, len(p.starved)))
    row["births"] = p.events.get("birth", 0)
    row["forgot"] = p.events.get("forgotten", 0)
    row.update(p.report())
    if report is not None:
        style = "full" if mind_opts.get("model_only") else mind_opts.get("style", "cascade")
        row["mind"] = {"brain": mind, "style": style, "model_led": bool(mind_opts.get("model_led")),
                       "hashseed": os.environ.get("PYTHONHASHSEED"), **report}
    return row, p


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("seed", type=int)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--chits", type=int, default=18)
    ap.add_argument("--culture", default="direct")
    ap.add_argument("--rules", default="", help='world rules as JSON, e.g. {"religion": false} (docs/WORLD_RULES.md)')
    ap.add_argument("--server", default=str(HERE.parents[1] / "server"), help="the server dir of the tree under test")
    ap.add_argument("--tag", default="")
    ap.add_argument("--autopsy", action="store_true", help="print the starved chits' last moments and stuck chits")
    g = ap.add_argument_group("model in the loop (mindrun.py)")
    g.add_argument("--mind", default="", help="'scripted' (the scripted model: no GPU, deterministic) or an "
                   "OpenAI-compatible base URL such as http://127.0.0.1:18191/v1. Default: instinct only")
    g.add_argument("--style", default="cascade", choices=("full", "compact", "choose", "cascade"),
                   help="the brain's prompt_style (the live game's brains use cascade)")
    g.add_argument("--slots", type=int, default=8, help="the brain's max_concurrency")
    g.add_argument("--bad-rate", type=float, default=0.15, help="scripted: share of answers that go wrong")
    g.add_argument("--bad-kinds", default="", help="scripted: comma-separated subset of scripted.BAD_KINDS")
    g.add_argument("--plan-ticks", type=int, default=8, help="scripted: world ticks a written plan takes to arrive")
    g.add_argument("--choice-ticks", type=int, default=1, help="scripted: world ticks a one-letter answer takes")
    g.add_argument("--loop-after", type=int, default=3, help="a step failing for the same reason more than this "
                   "many times in a row is a loop")
    g.add_argument("--tick-seconds", type=float, default=0.5, help="URL: wall seconds per tick (0.5 is the game at 1x)")
    g.add_argument("--model-only", action="store_true", help="diagnostic: nothing from instinct covers for the model "
                   "(the full prompt whatever --style says, no instinct plans, no body reflexes); counts what the "
                   "reflexes would have done. Never for comparisons")
    g.add_argument("--model-led", action="store_true", help="model-led play (docs/MODEL_LED.md): no instinct plans, filler or "
                   "fallback for the model's chits; the body's reflexes stay")
    args = ap.parse_args(argv)
    if args.model_led and args.model_only:
        ap.error("--model-led and --model-only are different modes: pick one")
    if args.model_led and not args.mind:
        ap.error("--model-led needs --mind (scripted or a URL)")
    if args.model_only and not args.mind:
        ap.error("--model-only needs --mind (scripted or a URL): an instinct run has no model to leave alone")
    if args.mind and "PYTHONHASHSEED" not in os.environ:
        # a prompt's text depends on string hashing (world.village_failed counts a set: ties in "Others around here
        # already tried these" come out in hash order), so a model run is only the same run with the hash pinned
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve())]
                 + list(sys.argv[1:] if argv is None else argv))
    server = Path(args.server).resolve()
    if not (server / "chits").is_dir():
        sys.exit(f"{server} is not a server dir (no chits/ in it)")
    sys.path[:0] = [str(server), str(HERE)]
    os.chdir(server)
    import chits

    where = Path(getattr(chits, "__file__", None) or next(iter(chits.__path__), "")).resolve()
    if server not in where.parents:  # (a chits installed in the venv would otherwise stand in for the tree under test)
        sys.exit(f"chits was imported from {where}, not from {server}")
    opts = {}
    if args.mind:
        opts = {"style": args.style, "slots": args.slots, "bad_rate": args.bad_rate,
                "bad_kinds": tuple(k for k in args.bad_kinds.split(",") if k) or None,
                "plan_ticks": args.plan_ticks, "choice_ticks": args.choice_ticks, "loop_after": args.loop_after,
                "tick_seconds": args.tick_seconds, "model_only": args.model_only, "model_led": args.model_led}
    try:
        row, p = run(args.seed, args.days, args.size, args.chits, args.culture, args.tag, args.mind,
                     json.loads(args.rules) if args.rules != "" else None, **opts)
    except ValueError as e:
        sys.exit(str(e))
    if args.autopsy:
        for text in (p.autopsy_text(), p.mind.autopsy_text() if p.mind else ""):
            if text:
                print(text)
    print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
