"""Size the world to the model: how many chits a brain keeps up with, and what that means for a new game.

A new game used to start with the same number of chits whatever the model's speed: a 5-second model with 4 slots
answered a few percent of its world's decisions and nobody was told why. The number here is diag.py's estimate
(slots × 15 s ÷ the median decision time), taken from the brain's live replies or, when it has none yet, from a short
probe of real decision requests (tools/doctor.py), run only when someone asks for it."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional

from .brain.mind import INSTINCT
from .diag import _quant, keeps_up_with

LIVE_SAMPLES = 3  # live replies before their median counts as a measurement
PROBE_SAMPLES = 4  # decisions asked by a probe
MIN_CHITS, MAX_CHITS = 2, 60  # what a new game accepts (app.reset)


def _chits(n: int) -> str:
    return f"{n} chit" + ("" if n == 1 else "s")


def capacity(brain) -> Dict[str, Any]:
    """What is known about one brain's speed: {"chits": how many it keeps up with (None: not measured),
    "latency_ms", "slots", "source": "live" | "probe" | None, "text"}."""
    slots = max(1, brain.cfg.max_concurrency)
    live = list(brain.latencies)
    probe = getattr(brain, "probe", None) or {}
    out: Dict[str, Any] = {"chits": None, "latency_ms": 0, "slots": slots, "source": None,
                           "text": "Speed not measured yet."}
    if len(live) >= LIVE_SAMPLES or (live and not probe.get("latency_ms")):
        out.update(source="live", latency_ms=round(_quant(live, 0.5)))
    elif probe.get("latency_ms"):
        out.update(source="probe", latency_ms=round(probe["latency_ms"]))
    elif probe.get("error"):
        out.update(error=probe["error"], text=f"Could not measure its speed: {probe['error']}")
    if out["source"]:
        n = out["chits"] = keeps_up_with(slots, out["latency_ms"])
        out["text"] = f"Keeps up with about {_chits(n)}." if n else "Too slow to keep up with even one chit."
    return out


async def measure(brain, samples: int = PROBE_SAMPLES) -> Dict[str, Any]:
    """Measure a brain that has no live measurement: a handful of real decisions, asked one at a time the way its
    prompt style asks them, on a client of their own (the brain's stats, queue and any tape are left alone). A cascade
    brain picks by one token and writes a full plan for a share of its decisions: both are timed."""
    from .tools.doctor import check_brain

    lock = brain.__dict__.setdefault("_measuring", asyncio.Lock())
    async with lock:  # (two dialogs asking at once share one probe)
        if capacity(brain)["source"] == "live":
            return capacity(brain)
        cfg = replace(brain.cfg, enabled=True)
        r = await check_brain(cfg, samples=samples, style=cfg.prompt_style)
        ms = r["latency_p50_ms"]
        if r["ok"] and cfg.prompt_style == "cascade":
            full = await check_brain(cfg, samples=max(1, samples // 2), style="full")
            if full["latency_p50_ms"]:
                ms += float(cfg.escalate_share or 0) * full["latency_p50_ms"]
        brain.probe = {"latency_ms": ms if r["ok"] else 0, "at": time.time(), "samples": r["samples"],
                       "valid": r["valid"], "error": "" if r["ok"] else r["error"]}
        return capacity(brain)


def recommend(mind, brains: Dict[str, str]) -> Dict[str, Any]:
    """Chits per world for a new game whose worlds think with `brains` (world id -> brain id): what the slowest
    model keeps up with, halved when one model drives two worlds. Instinct has no limit."""
    load = Counter(bid for bid in brains.values() if bid != INSTINCT and bid in mind.brains)
    if not load:
        return {"chits": None, "unmeasured": [], "limited_by": None, "text": "Instinct has no limit: any number of chits works."}
    caps = {bid: capacity(mind.brains[bid]) for bid in load}
    unmeasured = [bid for bid in load if caps[bid]["chits"] is None]
    if unmeasured:
        b = mind.brains[unmeasured[0]]
        return {"chits": None, "unmeasured": unmeasured, "limited_by": None, "capacity": caps,
                "text": f"{b.label}: {caps[unmeasured[0]]['text']}"}
    per_world, bid = min((caps[bid]["chits"] // n, bid) for bid, n in load.items())
    n = max(MIN_CHITS, min(MAX_CHITS, per_world))
    text = f"{mind.brains[bid].label} keeps up with about {_chits(caps[bid]['chits'])}"
    text += f", shared by {load[bid]} worlds: about {n} each." if load[bid] > 1 else "."
    if per_world < MIN_CHITS:
        text += f" That is too slow even for {MIN_CHITS}: most moves will be instinct."
    return {"chits": n, "unmeasured": [], "limited_by": bid, "capacity": caps, "text": text}


def hint_lines(rt) -> List[str]:
    """For each model driving a world right now: does it keep up, and if not, the size of world it could drive.
    (Advice only: a running world is never resized.)"""
    using = {wid: bid for wid, bid in rt.mind.world_brain.items() if wid in rt.worlds}
    drives: Counter = Counter()
    for w in rt.worlds.values():
        for a in w.agents.values():
            drives[a.brain] += 1
    out = []
    rec = recommend(rt.mind, using)
    for bid in dict.fromkeys(b for b in using.values() if b != INSTINCT and b in rt.mind.brains):
        b = rt.mind.brains[bid]
        cap = capacity(b)
        if cap["chits"] is None:
            out.append(f"{b.label}: {cap['text']}")
        elif cap["chits"] >= drives[bid]:
            out.append(f"{b.label} keeps up with about {_chits(cap['chits'])}. It drives {drives[bid]}.")
        else:
            line = (f"{b.label} keeps up with about {_chits(cap['chits'])}, but it drives {drives[bid]}: "
                    f"most moves will be instinct.")
            if rec["chits"]:
                line += (f" For a world it can drive, start a new game with {_chits(rec['chits'])} per world "
                         f"(New game, then \"Use {_chits(rec['chits'])}\").")
            out.append(line)
    return out


async def first_run_hint(rt, say: Callable[[str], None] = print) -> List[str]:
    """The first run's hint (the `little-chits` command prints it): measure each model the new worlds think with,
    and say whether it keeps up."""
    from .brain import checkup

    for bid in {b for wid, b in rt.mind.world_brain.items() if wid in rt.worlds and b in rt.mind.brains}:
        if rt.mind.brains[bid].cfg.detect and rt.contract != "experiment":
            await checkup.test_brain(rt.mind, rt.mind.brains[bid])  # (a model just found: settle what its server takes)
        await measure(rt.mind.brains[bid])
    lines = hint_lines(rt)
    for line in lines:
        say(line)
    return lines
