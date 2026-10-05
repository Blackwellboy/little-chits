"""Run model vs model headless, as fast as the models allow, and drop a folder ready to post.

    python -m chits.tools.experiment --a http://127.0.0.1:18191/v1 --b http://127.0.0.1:18192/v1 --days 3

Both worlds grow from the same seed. By default (--mode versus) both can talk, so the models are the only
difference; --mode culture instead lets World A talk ("direct") while World B can only watch and leave marks
("stigmergy"). Both models get the same explicit sampling settings (--top-p, --top-k, --min-p), so the servers'
own defaults (vLLM and llama.cpp differ) don't become a difference too. The output is a multi-axis scoreboard,
never a verdict on which model is "best".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import diag
from .. import invariants as INV
from ..brain import prompt as P
from ..brain.llm import BrainConfig
from ..brain.mind import INSTINCT, Mind
from ..sim.agent import TICKS_PER_DAY
from ..sim.world import World
from ..story.card import scoreboard_svg
from ..story.moments import find_moments
from ..story.xpost import _d, make_thread, pick_clip

MODES = {"versus": {"A": "direct", "B": "direct"}, "culture": {"A": "direct", "B": "stigmergy"}}
CULTURE = MODES["culture"]  # (the old default: two cultures)
SAMPLING = {"top_p": 0.95, "top_k": 40, "min_p": 0.05}
BRAIN_FAIL_STOP = 12  # a brain that fails this many requests in a row has stopped answering: the run is invalid  # sent to both models, whatever their server defaults
LABEL = {"direct": "Direct culture", "stigmergy": "Stigmergy only"}


def _waiting(w: World, mind: Mind) -> bool:
    """More than half of the model-driven chits are idle, waiting on a reply."""
    model = [a for a in w.agents.values() if (b := mind.brain_for(a)) is not None and b.healthy()]
    if not model:
        return False
    idle = sum(1 for a in model if a.thinking and (not a.plan or a.plan[0].get("_filler")))
    return idle * 2 > len(model)


def _axes(w: World, events: List[dict], brain, dg) -> Dict[str, Any]:
    st = w.stats()
    kinds = Counter(e["kind"] for e in events)
    causes = Counter(a.cause_of_death or "unknown" for a in w.dead.values())
    pace = sorted(f["tick"] // TICKS_PER_DAY + 1 for f in w.first.values())
    pop = max(1, len(w.agents))
    plans = sum(dg.plans.values())
    out = {
        "population": st["population"], "deaths": st["deaths"], "deaths_by_cause": dict(causes),
        "births": kinds.get("birth", 0), "discoveries": st["discoveries"], "discovery_days": pace,
        "inventions": kinds.get("invention", 0),
        "knowledge_per_chit": round(sum(len(a.knows) for a in w.agents.values()) / pop, 2),
        "taught": kinds.get("learned", 0), "structures": st["structures"], "building_kinds": len(st["by_design"]),
        "speech": kinds.get("speech", 0),
        "fallback_rate": round((dg.plans.get("fallback", 0) + dg.plans.get("filler", 0)) / plans, 3) if plans else 0.0,
    }
    if brain is not None:
        s = brain.stats
        out["latency_ms"] = round(s.latency_ms_avg)
        out["unreadable_rate"] = round(s.parse_failed / s.requests, 3) if s.requests else 0.0
    return out


def _compute(brain, recs: List[Dict[str, Any]], dg, days_run: float, discoveries: int) -> Dict[str, Any]:
    """What a world's thinking cost (research plan item 29), beside what it achieved: a model that discovers as much
    on a fifth of the tokens is a result too. Token counts are the server's own (every call: plans, retries,
    reflections, a chief's choice); request seconds add up each call's time, so calls that overlapped count twice."""
    if brain is None:
        return {}
    s = brain.stats
    tokens = (s.tokens_in or 0) + (s.tokens_out or 0)
    from ..brain.mind import CIVIC_STYLES

    plans = [r for r in recs if r.get("style") not in CIVIC_STYLES]
    adopted = sum(1 for r in plans if r.get("outcome") == "adopted")
    repairs = sum(1 for r in plans if r.get("style") == "repair")
    done = dg.outcomes.get(("model", "ok"), 0)
    tried = done + dg.outcomes.get(("model", "fail"), 0)

    def per(n, d, k=1):
        return round(n / d * k, 1) if d else None

    return {"requests": s.requests, "failed_requests": s.failed, "retries": getattr(s, "retries", 0),
            "tokens_in": s.tokens_in, "tokens_out": s.tokens_out, "tokens": tokens,
            "tokens_per_day": per(tokens, days_run), "decisions_adopted": adopted,
            "tokens_per_decision": per(tokens, adopted), "tokens_per_discovery": per(tokens, discoveries),
            "request_seconds": round(sum(r.get("latency_ms") or 0 for r in recs) / 1000, 1),
            "repair_rate": round(repairs / len(plans), 3) if plans else 0.0,
            "model_steps_done": done, "model_step_success": round(done / tried, 3) if tried else None,
            "model_steps_done_per_1k_tokens": per(done, tokens, 1000)}


def _md(summary: Dict[str, Any], moments: Dict[str, list], thread: List[str]) -> str:
    ws = summary["worlds"]
    title = " vs ".join(f"{w['label']} (World {wid})" for wid, w in ws.items())
    stop = (summary.get("invariants") or {}).get("broken") or []
    lines = [f"# {title}", ""] + ([f"**Stopped on day {summary['ticks'] // TICKS_PER_DAY + 1}: "
                                   f"{'a model stopped answering' if any(b['kind'] == 'brain_unavailable' for b in stop) else 'an invariant broke'}** ("
                                   + "; ".join(f"World {b['world']} {b['kind']}: {b['what']}" for b in stop[:3])
                                   + "). Nothing below is a result.", ""] if stop else []) + [
             f"Seed {summary['seed']} · {summary['days']} days · {summary['ticks']} ticks · {summary['wall_s']} s wall time", "",
             ("Same island, same chits. World A can talk; World B can only watch and leave marks. "
              if summary.get("mode", "culture") == "culture" else "Same island, same chits, both can talk: the models "
              "are the only difference. ") + "Each row is its own axis: there is no overall winner.", "",
             "## Scoreboard", "", "| | " + " | ".join(f"World {wid} · {w['label']}" for wid, w in ws.items()) + " |",
             "|---|" + "---|" * len(ws)]
    rows = [("Population", "population"), ("Deaths", "deaths"), ("Births", "births"), ("Discoveries", "discoveries"),
            ("Inventions", "inventions"), ("Knowledge per chit", "knowledge_per_chit"), ("Lessons passed on", "taught"),
            ("Buildings", "structures"), ("Kinds of building", "building_kinds"), ("Things said", "speech"),
            ("Model latency (ms)", "latency_ms"), ("Unreadable-reply rate", "unreadable_rate"),
            ("Instinct fallback rate", "fallback_rate")]
    for name, key in rows:
        lines.append(f"| {name} | " + " | ".join(str(w["axes"].get(key, "–")) for w in ws.values()) + " |")
    cost = [("Tokens", "tokens"), ("Tokens per day", "tokens_per_day"), ("Tokens per adopted plan", "tokens_per_decision"),
            ("Tokens per discovery", "tokens_per_discovery"), ("Requests", "requests"),
            ("Request seconds", "request_seconds"), ("Repair rate", "repair_rate"),
            ("Model steps done per 1k tokens", "model_steps_done_per_1k_tokens")]
    if any(w.get("compute") for w in ws.values()):
        lines += ["", "## What the thinking cost", "", "| | " + " | ".join(f"World {wid}" for wid in ws) + " |",
                  "|---|" + "---|" * len(ws)]
        for name, key in cost:
            cells = [w.get("compute", {}).get(key) for w in ws.values()]
            lines.append(f"| {name} | " + " | ".join("–" if c is None else str(c) for c in cells) + " |")
    for wid, w in ws.items():
        causes = ", ".join(f"{c} {n}" for c, n in w["axes"]["deaths_by_cause"].items()) or "none"
        days = ", ".join(map(str, w["axes"]["discovery_days"])) or "none"
        lines += ["", f"World {wid}: deaths by cause: {causes}. Discoveries on days: {days}. "
                      f"Model plans adopted: {w['model_plans']}."]
    for wid, ms in moments.items():
        lines += ["", f"## Top moments · World {wid} · {ws[wid]['label']}", ""]
        top = sorted((_d(m) for m in ms), key=lambda m: (-m["score"], m["tick"]))[:5]
        lines += [f"- Day {m['tick'] // TICKS_PER_DAY + 1}: {m['text']}" for m in top] or ["- (nothing notable yet)"]
    lines += ["", "## X thread", ""]
    for i, p in enumerate(thread, 1):
        lines += [f"{i}. {p}", ""]
    return "\n".join(lines).rstrip() + "\n"


async def run_experiment(brains: Dict[str, Optional[BrainConfig]], days: float, out_dir: Path, *, seed: int = 1234,
                         chits: int = 12, max_wall_s: Optional[float] = None, mode: Optional[str] = None,
                         sampling: Optional[Dict[str, Any]] = None, tape: Optional[Any] = None,
                         lockstep: bool = True, repair: bool = False, request_seeds: bool = True) -> Dict[str, Any]:
    """`tape`: a BrainTape (brain/tape.py) that records every model reply, or replays a recording instead of asking
    the model servers (a run on the same code then reproduces exactly).
    `lockstep` (the default): every model call made on a tick (plans, reflections, a chief's choice) is answered
    before the next tick. How fast a model answers then changes nothing in the world, only the wall time: a slow
    model's chits don't fall behind a fast one's, and a replay lands every answer on the same tick.
    `repair`: bounded action repair (research plan item 40), off unless declared: a model's failed step goes back to
    it once with the exact reason.
    `request_seeds` (the default): every request carries a sampling seed made from the run's seed and the exact
    prompt (brain/llm.request_seed), unless a brain's own settings fix one."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mind = Mind(out_dir / "brains.json")
    mind.strict = True  # experiment contract: a model's chits never get instinct plans
    mind.repair = repair
    decisions: List[Dict[str, Any]] = []
    mind.on_decision = decisions.append
    worlds: Dict[str, World] = {}
    events: Dict[str, List[dict]] = {}
    # F7: callers must state what differs. The one frozen T15 acceptance shape predates `mode` and explicitly
    # expects A=model/direct vs B=instinct/stigmergy, so preserve only that exact compatibility path.
    if mode is None:
        legacy_t15 = brains.get("A") is not None and brains.get("B") is None
        if not legacy_t15:
            raise TypeError("run_experiment() requires mode='versus' or mode='culture'")
        mode = "culture"
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    sampling = dict(SAMPLING if sampling is None else sampling)
    for wid in ("A", "B"):
        cul = MODES[mode][wid]
        w = World(wid, f"World {wid}", seed, cul, 128, chits, label=LABEL[cul])
        events[wid] = []
        w.listeners = [lambda ev, wid=wid: events[wid].append(ev.to_dict())]
        cfg = brains.get(wid)
        if cfg is not None:
            body = {**sampling, **(cfg.extra_body or {})}  # the same sampling for both (a config's own wins)
            mind.upsert({**cfg.__dict__, "id": cfg.id or f"brain{wid}", "extra_body": body})
            mind.assign(w, cfg.id or f"brain{wid}")
            if tape is not None:
                mind.brains[cfg.id or f"brain{wid}"].tape = tape
            if lockstep:  # the world waits for every answer: a wall-clock back-off after failures only adds noise
                mind.brains[cfg.id or f"brain{wid}"].cooldown = False
            if request_seeds:
                mind.brains[cfg.id or f"brain{wid}"].seed_base = seed
        else:
            mind.assign(w, INSTINCT)
        worlds[wid] = w
    target = int(round(days * TICKS_PER_DAY))
    t0 = time.time()
    ticks = 0
    broken: List[Dict[str, Any]] = []  # a hard invariant broke (invariants.py): the run stops, its outputs say why
    own = {wid: ((brains[wid].id or f"brain{wid}") if brains.get(wid) is not None else INSTINCT) for wid in worlds}
    try:
        while ticks < target:
            if max_wall_s is not None and time.time() - t0 > max_wall_s:
                break
            if lockstep:
                while mind._tasks:  # (a task may start another: wait until none is left)
                    await asyncio.wait(list(mind._tasks))
            elif any(_waiting(w, mind) for w in worlds.values()):
                await asyncio.sleep(0.02)
                continue
            for w in worlds.values():
                w.step(mind.hook)
            ticks += 1
            # the experiment's gates, after every tick (audit F1, F2): a hard invariant, or a world whose model has
            # stopped answering (its chits would stand still while the other world's kept deciding)
            for wid, w in worlds.items():
                broken += [dict(b, world=wid) for b in INV.check(w, "experiment", own[wid]) if b["level"] == "hard"]
                b = mind.brains.get(own[wid])
                if b is not None and (not b.healthy() or b.stats.consecutive_fail >= BRAIN_FAIL_STOP):
                    broken.append({"kind": "brain_unavailable", "level": "hard", "tick": w.tick, "world": wid,
                                   "what": f"{b.label}: {b.stats.consecutive_fail} requests failed in a row"
                                           + (f" ({b.stats.last_error})" if b.stats.last_error else "")
                                           + ("" if b.cfg.enabled else " (disabled)")})
            if broken:
                print("STOPPED: " + "; ".join(f"{b['world']} {b['kind']}: {b['what']}" for b in broken[:5]), flush=True)
                break
            if ticks % 5 == 0:
                await asyncio.sleep(0)
            if ticks % TICKS_PER_DAY == 0:
                print(f"day {ticks // TICKS_PER_DAY} done · " + " · ".join(
                    f"{wid}: {len(w.agents)} chits, {len(w.first)} discoveries" for wid, w in worlds.items()), flush=True)
        # the last tick's calls are answered too: cancelled half-way, a recording lost the ones still on the wire
        # while a replay, answering from the tape at once, asked them anyway (the one-miss replay seen in CI)
        while lockstep and mind._tasks:
            await asyncio.wait(list(mind._tasks))
    finally:
        wall = round(time.time() - t0, 1)
        await mind.close()

    summary: Dict[str, Any] = {"seed": seed, "days": days, "ticks": ticks, "wall_s": wall, "mode": mode, "worlds": {},
                               "invariants": {"broken": broken, "soft": [dict(b, world=wid) for wid, w in worlds.items()
                                                                      for b in INV.check(w, "experiment", own[wid])
                                                                      if b["level"] == "soft"]}}
    cards, moments = [], {}
    for wid, w in worlds.items():
        cfg = brains.get(wid)
        brain = mind.brains.get(cfg.id or f"brain{wid}") if cfg is not None else None
        dg = diag.of(w)
        names = {a.id: a.name for a in list(w.agents.values()) + list(w.dead.values())}
        moments[wid] = find_moments(events[wid], names)
        label = (brain.label if brain else "Instinct")
        summary["worlds"][wid] = {
            "brain": cfg.id if cfg else INSTINCT, "label": label, "culture": w.culture, "stats": w.stats(),
            "decisions": sum(a.decisions for a in list(w.agents.values()) + list(w.dead.values())),
            "model_plans": dg.plans.get("model", 0),
            "brain_stats": dict(brain.stats.__dict__) if brain else {},
            "axes": _axes(w, events[wid], brain, dg),
            "compute": _compute(brain, [r for r in decisions if r.get("world") == w.id], dg, ticks / TICKS_PER_DAY,
                                w.stats()["discoveries"]),
        }
        cards.append({"id": wid, "name": w.name, "brain": label, "culture": w.culture, "day": w.day + 1, "stats": w.stats()})
        (out_dir / f"events_{wid}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events[wid]))
    thread = make_thread(cards, moments)
    manifest = {"contract": "experiment", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": seed, "chits": chits,
                "size": 128, "prompt_version": P.PROMPT_VERSION,
                "rng_scheme": next(iter(worlds.values())).rng_scheme if worlds else None, "mode": mode, "sampling": sampling, "lockstep": lockstep, "repair": repair,
                "request_seeds": request_seeds,
                "worlds": {wid: {"culture": w.culture, "uuid": w.uuid, "epoch": w.epoch,
                                 "brain": ({k: v for k, v in brains[wid].__dict__.items() if k != "api_key"}
                                           if brains.get(wid) else "instinct")} for wid, w in worlds.items()}}
    try:
        from ..runtime import source_commit
        manifest["source_commit"] = source_commit()
    except Exception:
        pass
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "decisions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in decisions))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    from ..story.divergence import compare, to_markdown

    (out_dir / "summary.md").write_text(_md(summary, moments, thread) + "\n" + to_markdown(compare(worlds["A"], worlds["B"])))
    (out_dir / "card.svg").write_text(scoreboard_svg(cards, pick_clip(moments)))
    return summary


def _cfg(url: str, model: str, wid: str) -> Optional[BrainConfig]:
    if not url or url.lower() == INSTINCT:
        return None
    return BrainConfig(id=f"brain{wid}", label=model or f"World {wid} model", base_url=url, model=model or "")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default=INSTINCT, help="World A: a model server URL, or 'instinct'")
    ap.add_argument("--b", default=INSTINCT, help="World B: a model server URL, or 'instinct'")
    ap.add_argument("--model-a", default="")
    ap.add_argument("--model-b", default="")
    ap.add_argument("--days", type=float, default=3)
    ap.add_argument("--chits", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", default="")
    ap.add_argument("--mode", choices=sorted(MODES), default="versus",
                    help="versus: both worlds can talk, only the models differ (default); culture: World B can't talk")
    ap.add_argument("--top-p", type=float, default=SAMPLING["top_p"])
    ap.add_argument("--top-k", type=int, default=SAMPLING["top_k"])
    ap.add_argument("--min-p", type=float, default=SAMPLING["min_p"])
    ap.add_argument("--tape", default="", help="record every model reply to this file (a BrainTape)")
    ap.add_argument("--replay", default="", help="replay a recorded BrainTape instead of asking the model servers")
    ap.add_argument("--no-lockstep", action="store_true",
                    help="let the world run on while models think (then a slow model's chits fall behind)")
    ap.add_argument("--no-request-seeds", action="store_true",
                    help="don't send a per-request sampling seed (made from --seed and the prompt)")
    ap.add_argument("--repair", action="store_true",
                    help="bounded action repair: a model's failed step goes back to it once with the exact reason")
    args = ap.parse_args(argv)
    tape = None
    if args.tape or args.replay:
        from ..brain.tape import BrainTape

        tape = BrainTape(args.replay, "replay") if args.replay else BrainTape(args.tape, "record")
    out = Path(args.out or Path(__file__).resolve().parents[3] / "data" / "experiments" / time.strftime("%Y%m%d-%H%M%S"))
    brains = {"A": _cfg(args.a, args.model_a, "A"), "B": _cfg(args.b, args.model_b, "B")}
    asyncio.run(run_experiment(brains, args.days, out, seed=args.seed, chits=args.chits, mode=args.mode,
                               sampling={"top_p": args.top_p, "top_k": args.top_k, "min_p": args.min_p}, tape=tape, lockstep=not args.no_lockstep,
                               repair=args.repair, request_seeds=not args.no_request_seeds))
    if tape is not None:
        print(f"BrainTape: {tape.recorded} recorded, {tape.played} replayed, {tape.misses} missing, "
              f"{tape.remaining() if tape.mode == 'replay' else 0} left unplayed")
    print(f"Written to {out}")
    print(f"Read {out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
