"""Compact diagnostics: is the model keeping up, are plans working, is anyone stuck, do chits answer each other?

Counters are kept in memory per world (they reset on restart) and summarised on demand as a short report with
plain-English warnings. It is for checking a run went smoothly and for debugging, not for scoring models."""

from __future__ import annotations

import re
import time
import weakref
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Tuple

_NUM = re.compile(r"\d+(\.\d+)?")
_REPLY_WINDOW = 360  # ticks an addressed chit has to answer (a plan cycle can take 100+)


class WorldDiag:
    def __init__(self) -> None:
        self.started = time.time()
        self.steps: Counter = Counter()          # (verb, "ok"|"fail") -> n
        self.fail_reasons: Counter = Counter()   # normalised failure text -> n
        self.plans: Counter = Counter()          # model | instinct | fallback | filler -> n
        self.authorship: Counter = Counter()
        self.step_sources: Counter = Counter()
        self.recent_steps: deque = deque(maxlen=200)
        self.model_ticks = 0                     # agent-ticks with a model brain
        self.waiting_ticks = 0                   # ... of which idle, waiting on a reply
        self.streak: Dict[str, int] = {}         # agent id -> consecutive failed steps
        self.repeat: Dict[str, list] = {}        # agent id -> [the same failure, how many times in a row]
        self.loops: Counter = Counter()          # plan origin -> loops (LOOP_N identical failures in a row)
        self.loop_examples: deque = deque(maxlen=12)
        self.outcomes: Counter = Counter()       # ("model"|"other", "ok"|"fail") -> finished steps
        self.chief: Counter = Counter()          # the chief's-choice lifecycle: stage -> how many questions reached it
        self.chief_log: deque = deque(maxlen=60)  # finished questions, each with its stage ticks and timings
        self.addressed = 0
        self.replied = 0
        self.pending_talk: Dict[tuple, int] = {}  # (listener, speaker) -> tick addressed
        self.said = 0
        self.heard = 0
        self.recent_fails: deque = deque(maxlen=12)


_DIAG: Dict[int, Any] = {}  # id(world) -> (a weak reference to it, its WorldDiag)


def of(world) -> WorldDiag:
    # (an id is reused once its world is freed: without the identity check a new world, after a reset or in the
    # next test, inherited the old one's counts)
    e = _DIAG.get(id(world))
    if e is None or e[0]() is not world:
        e = _DIAG[id(world)] = (weakref.ref(world, lambda r, k=id(world): _DIAG.pop(k) if _DIAG.get(k, (None,))[0] is r else None), WorldDiag())
    return e[1]


def chief(world, stage: str, ask=None, end: bool = False, **info) -> None:
    """One question to the chief, through its life (audit F12): asked -> sent (or blocked: the chief's brain
    unavailable) -> answered -> adopted, or stale on arrival / invalid / request failed / expired (the chief changed,
    didn't answer, or was never asked) and need decides. Counted per stage; a finished question is logged whole."""
    d = of(world)
    life = ask.setdefault("life", {}) if isinstance(ask, dict) else {}
    if stage not in life:
        d.chief[stage] += 1
    life.setdefault("asked", world.tick)
    life.setdefault(stage, world.tick)
    life.update(info)
    if end and not life.get("ended"):
        life["ended"] = stage
        d.chief_log.append(dict(life))


def chief_summary(world) -> Dict[str, Any]:
    d = of(world)
    log = list(d.chief_log)

    def med(xs):
        xs = sorted(x for x in xs if x is not None)
        return xs[len(xs) // 2] if xs else None

    return {"stages": dict(d.chief), "ended": dict(Counter(x.get("ended") for x in log)),
            "ticks_asked_to_sent": med([x["sent"] - x["asked"] for x in log if "sent" in x]),
            "ticks_asked_to_answered": med([x["answered"] - x["asked"] for x in log if "answered" in x]),
            "queue_ms": med([x.get("queue_ms") for x in log]), "latency_ms": med([x.get("latency_ms") for x in log]),
            "leader_changes": d.chief.get("leader changed", 0), "recent": log[-3:]}


LOOP_N = 4  # the same step failing for the same reason this many times in a row is a loop


def step_done(world, a, verb: str) -> None:
    d = of(world)
    d.steps[(verb, "ok")] += 1
    d.streak[a.id] = 0
    d.repeat.pop(a.id, None)
    a.__dict__.pop("_loop", None)


def step_failed(world, a, verb: str, reason: str, what: str = "", origin: str = "") -> None:
    """Also the loop detector (research plan item 41): the same step (verb and object) failing for the same reason
    LOOP_N times in a row, with nothing done in between, is counted by who planned it (a model's plan or instinct):
    a model comparison should see which one adapts after failure. The chit's next prompt is told, outside experiments
    (brain/prompt.loop_line)."""
    d = of(world)
    d.steps[(verb, "fail")] += 1
    key = f"{verb}: {_NUM.sub('#', reason)[:70]}"
    d.fail_reasons[key] += 1
    d.streak[a.id] = d.streak.get(a.id, 0) + 1
    d.recent_fails.append((world.tick, a.name, key))
    sig = f"{verb} {what}".strip() + " | " + _NUM.sub("#", reason)[:70]
    r = d.repeat.get(a.id)
    if r and r[0] == sig:
        r[1] += 1
    else:
        r = d.repeat[a.id] = [sig, 1]
    a.__dict__["_loop"] = (f"{verb} {what}".strip(), reason, r[1])  # (a planner's note, not saved)
    if r[1] == LOOP_N:
        kind = "model" if str(origin).startswith("model") else (origin or "instinct")
        d.loops[kind] += 1
        d.loop_examples.append({"tick": world.tick, "name": a.name, "origin": kind, "failure": sig})


def plan_from(world, kind: str) -> None:
    of(world).plans[kind] += 1


def spoke(world, a, addressed_to: Optional[str], listeners: int) -> None:
    d = of(world)
    d.said += 1
    d.heard += listeners
    # did this answer someone who spoke to us?
    for (listener, speaker), t in list(d.pending_talk.items()):
        if listener == a.id and speaker == addressed_to and world.tick - t <= _REPLY_WINDOW:
            d.replied += 1
            del d.pending_talk[(listener, speaker)]
    if addressed_to:
        d.addressed += 1
        d.pending_talk[(addressed_to, a.id)] = world.tick
    for k, t in list(d.pending_talk.items()):
        if world.tick - t > _REPLY_WINDOW:
            del d.pending_talk[k]


def _pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _quant(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


PLAN_EVERY_S = 15.0  # at 1× a chit wants a fresh plan about this often (the same yardstick as `make doctor`)


def speed_rating(concurrency: int, latency_ms: float, chits: int, waits: bool = False) -> Dict[str, Any]:
    """Can a model keep up with the chits it drives? It answers `concurrency` requests at once, each taking
    `latency_ms`, so it can serve about concurrency × 15 s / latency chits at 1×. Below that, chits fill in with
    instinct while they wait (or, in an experiment run, just wait: waits=True)."""
    if chits <= 0 or latency_ms <= 0:
        return {"level": "unknown", "capacity": 0, "chits": chits, "text": "Not measured yet."}
    cap = int(max(1, concurrency) * PLAN_EVERY_S * 1000 / latency_ms)
    secs = latency_ms / 1000
    if cap >= chits:
        return {"level": "good", "capacity": cap, "chits": chits,
                "text": f"Capacity estimate: {secs:.0f}s median suggests about {cap} chits (it drives {chits}); mixed choice/full latency and configured slots do not prove useful throughput."}
    if cap * 2 >= chits:
        return {"level": "ok", "capacity": cap, "chits": chits,
                "text": f"Borderline: {secs:.0f}s per decision keeps up with about {cap} of its {chits} chits; "
                        + ("the others wait for it at times." if waits else "the others fill in with instinct at times.")}
    return {"level": "slow", "capacity": cap, "chits": chits,
            "text": f"Too slow for {chits} chits: {secs:.0f}s per decision keeps up with only about {cap}. "
                    + ("Most chits stand waiting for their next plan. " if waits else
                       "Most moves will be instinct and the world slows down to wait. ")
                    + "Use a faster model, more parallel slots, or fewer chits."}


def brain_ratings(rt) -> Dict[str, Dict[str, Any]]:
    """speed_rating for every brain, from its live median latency and the chits it drives right now."""
    chits: Counter = Counter()
    for w in rt.worlds.values():
        for a in w.agents.values():
            b = rt.mind.brain_for(a)
            if b is not None:
                chits[b.id] += 1
    waits = getattr(rt, "contract", "play") == "experiment"  # no instinct stand-ins there: chits wait
    return {bid: speed_rating(b.cfg.max_concurrency, _quant(list(b.latencies), 0.5), chits[bid], waits)
            for bid, b in rt.mind.brains.items()}


def opportunities(world) -> Dict[str, Dict[str, int]]:
    """For everything not yet achieved, how close the world is: known? affordable? tried? ("why didn't this happen?")"""
    from .sim.actions import village_stores
    from .sim.buildings import UPGRADES
    from .sim.items import DESIGNS, RECIPES

    out: Dict[str, Dict[str, int]] = {}
    agents = list(world.agents.values())
    built = {s.design for s in world.structures.values() if s.functional}
    if world.roads:
        built.add("road")
    for key, d in DESIGNS.items():
        if key in built:
            continue
        mats = d.material_map
        knowers = [a for a in agents if a.knows_design(key)]
        afford = 0
        for a in knowers:
            have = dict(a.inventory)
            for p in village_stores(world, a.x, a.y, 20, a):
                for k, n in p.storage.items():
                    have[k] = have.get(k, 0) + n
            if all(have.get(k, 0) >= n for k, n in mats.items()):
                afford += 1
        sites = [s for s in world.structures.values() if s.design == key and not s.complete]
        abandoned = world.lifetime("abandoned", key)  # (whole run, since world.tallies_since)
        # a design reached by rebuilding (a stockpile as a warehouse) is started as an upgrade, not a site: the panel
        # said "never started" while six stockpiles in each live world were half rebuilt as warehouses (audit F10)
        ups = [s for s in world.structures.values() if (s.upgrade or {}).get("to") == key] \
            if any(key in to for to in UPGRADES.values()) else []
        out[f"design:{key}"] = {"known_by": len(knowers), "affordable_by": afford, "sites_started": len(sites),
                                "sites_abandoned": abandoned, "upgrades_started": len(ups),
                                "upgrades_waiting_for": dict(sum((Counter(s.upgrade.get("needs", {})) for s in ups), Counter()))}
    for key, r in RECIPES.items():
        if f"recipe:{key}" in world.first or key.startswith("inv_"):
            continue
        inputs = {k for k, _ in r.inputs}
        handled = sum(1 for a in agents if inputs <= a.familiar)
        names = {k.replace("_", " ") for k in inputs}
        tried = sum(1 for a in agents if any(all(n in f for n in names) for f in a.failed_experiments))
        out[f"recipe:{key}"] = {"inputs_handled_by": handled, "tried_by": tried}
    return out


def capability_use(world) -> Dict[str, Dict[str, int]]:
    """Knowledge, demonstrated manufacture and current holdings are separate facts."""
    out = {}
    for a in world.agents.values():
        for key, knowledge in a.knows.items():
            if not key.startswith("recipe:"):
                continue
            row = out.setdefault(key, {"known_by": 0, "worked_by": 0, "held_units": 0, "stored_units": 0})
            row["known_by"] += 1
            row["worked_by"] += knowledge.get("status") == "worked"
    for key, row in out.items():
        item = key.split(":", 1)[1]
        row["held_units"] = sum(a.inventory.get(item, 0) for a in world.agents.values())
        row["stored_units"] = sum(s.storage.get(item, 0) for s in world.structures.values() if s.functional)
    return out


def action_finished(world, a, step, result: str) -> None:
    state = step.get("_s", {})
    origin = "reflex" if step.get("_reflex") else ("filler" if step.get("_filler") else step.get("_origin", a.plan_source or "unknown"))
    record = {"world": world.id, "world_uuid": world.uuid, "epoch": world.epoch, "tick": world.tick,
              "agent": a.id, "plan_id": None if step.get("_reflex") else a.plan_id, "decision_id": step.get("_decision_id"),
              "step_id": step.get("_step_id"), "tick_started": step.get("_tick_started"),
              "source": origin, "verb": step.get("do"), "outcome": "executed" if result == "done" else "failed",
              "result": state.get("note", "") if result == "done" else result,
              "step": {k: v for k, v in step.items() if not k.startswith("_")}}
    d = of(world)
    d.step_sources[origin] += 1
    d.outcomes[("model" if str(origin).startswith("model") else "other", "ok" if result == "done" else "fail")] += 1
    d.recent_steps.append(record)
    callback = getattr(world, "on_action_outcome", None)
    if callback:
        callback(record)


def _invariants(rt, w) -> Dict[str, Any]:
    """The InvariantMonitor's view (invariants.py), report only: a live world may hold records older than a check."""
    from . import invariants as INV

    try:
        found = INV.check(w, getattr(rt, "contract", "play"), rt.mind.world_brain.get(w.id))
    except Exception as e:  # a report never breaks
        return {"error": f"{type(e).__name__}: {e}"}
    counts: Dict[str, int] = {}
    for b in found:
        counts[b["kind"]] = counts.get(b["kind"], 0) + 1
    return {"hard": sum(1 for b in found if b["level"] == "hard"), "counts": counts,
            "examples": [b["what"] for b in found if b["level"] == "hard"][:4]}


def report(rt) -> Dict[str, Any]:
    """Everything, as data. `text()` turns it into the compact log."""
    out: Dict[str, Any] = {"mode": rt.mode, "speed": rt.speed, "paused": rt.paused, "tps": round(rt.tps, 1),
                           "pacing_to_brain": rt.waiting_on_brain, "worlds": {}, "brains": {}, "warnings": []}
    warn = out["warnings"]
    try:
        rec_storage = rt.recorder.storage_status()
        out["recordings"] = rec_storage
        if rec_storage.get("warning"):
            warn.append("Recorder: " + rec_storage["warning"])
    except Exception as e:
        out["recordings"] = {"error": f"{type(e).__name__}: {e}"}
    out["durability"] = {"durable_tick": {wid: getattr(w, "_durable_tick", -1) for wid, w in rt.worlds.items()},
                         "save_errors": dict(getattr(rt, "save_errors", {})),
                         "invalid_reason": getattr(rt, "invalid_reason", "")}
    for wid, err in out["durability"]["save_errors"].items():
        warn.append(f"World {wid}: checkpoint failed; simulation is paused until an explicit save succeeds ({err[:120]})")
    if out["durability"]["invalid_reason"]:
        warn.append("EXPERIMENT INVALID: " + out["durability"]["invalid_reason"][:180])
    ratings = brain_ratings(rt)
    for bid, b in rt.mind.brains.items():
        st = b.stats
        lat = list(getattr(b, "latencies", []))
        out["brains"][bid] = {
            "label": b.label, "url": b.cfg.base_url, "model": st.resolved_model or b.cfg.model,
            "requests": st.requests, "ok": st.ok, "failed": st.failed, "parse_failed": st.parse_failed,
            "repaired": getattr(st, "repaired", 0), "retries": getattr(st, "retries", 0),
            "in_flight": st.in_flight, "queued": st.queued, "concurrency": b.cfg.max_concurrency,
            "latency_p50_ms": round(_quant(lat, 0.5)), "latency_p95_ms": round(_quant(lat, 0.95)),
            "tok_s": round(b.throughput(), 1), "tok_s_request": round(st.tok_per_s, 1),
            "last_error": st.last_error, "healthy": b.healthy(), "speed": ratings[bid],
        }
        br = out["brains"][bid]
        if st.ok >= 10 and ratings[bid]["level"] == "slow":
            warn.append(f"{b.label}: {ratings[bid]['text']}")
        if st.requests >= 10 and st.failed / max(1, st.requests) > 0.1:
            warn.append(f"{b.label}: {_pct(st.failed, st.requests)}% of requests failed ({st.last_error[:80]})")
        if st.requests >= 10 and st.parse_failed / max(1, st.requests) > 0.15:
            warn.append(f"{b.label}: {_pct(st.parse_failed, st.requests)}% of replies were unreadable. Try the compact "
                        "prompt, lower temperature, or turn off 'skip thinking' if the model needs it")
        if st.queued > 2 * b.cfg.max_concurrency:
            warn.append(f"{b.label}: {st.queued} requests queued behind {b.cfg.max_concurrency} parallel slots. "
                        "Raise parallel requests to match the server (llama-server -np N) or use fewer chits")
        if st.ok >= 10 and br["tok_s_request"] and br["tok_s"] < 1.5 * br["tok_s_request"] and b.cfg.max_concurrency > 1 \
                and st.in_flight > 1:
            warn.append(f"{b.label}: requests may be serializing on the server (throughput "
                        f"{br['tok_s']} ≈ per-request {br['tok_s_request']} tok/s). Verify server batching and queue time; configured concurrency alone does not prove parallelism.")
        if br["latency_p95_ms"] > 30000:
            warn.append(f"{b.label}: slow replies (p95 {br['latency_p95_ms'] / 1000:.0f}s). Check queue time and waiting; pacing does not slow the 1x clock below 2 ticks/s.")
    outcomes: Dict[str, Dict[str, int]] = {}
    for rec in rt.mind.decisions:
        o = outcomes.setdefault(rec.get("world", "?"), {})
        o[rec.get("outcome", "?")] = o.get(rec.get("outcome", "?"), 0) + 1
    for wid, w in rt.worlds.items():
        d = of(w)
        bid = rt.mind.world_brain.get(wid, "instinct")
        plans = dict(d.plans)
        total_plans = sum(plans.values())
        # routine plans are left to instinct on purpose (a brain's focus), and so is a pioneer's duty; so are the plans
        # shed while the model's queue was full (one for every chit that would have queued: counted with the rest, the
        # share read 2.1% on the live game at the same 47 adopted plans a day as before)
        decided = total_plans - plans.get("routine", 0) - plans.get("duty", 0) - plans.get("shed", 0)
        steps_ok = sum(n for (v, r), n in d.steps.items() if r == "ok")
        steps_fail = sum(n for (v, r), n in d.steps.items() if r == "fail")
        by_verb: Dict[str, Dict[str, int]] = {}
        for (v, r), n in d.steps.items():
            by_verb.setdefault(v, {"ok": 0, "fail": 0})[r] += n
        worst = sorted(((v, c["fail"], c["ok"] + c["fail"]) for v, c in by_verb.items() if c["fail"]),
                       key=lambda t: t[1] / max(1, t[2]), reverse=True)[:5]
        stuck = [{"name": a.name, "fails_in_a_row": d.streak.get(a.id, 0), "doing": a.activity,
                  "last": a.last_result[:90]}
                 for a in w.agents.values() if d.streak.get(a.id, 0) >= 5]
        firsts = sorted(v["tick"] for v in w.first.values())
        since_disc = (w.tick - firsts[-1]) / 240 if firsts else w.tick / 240
        hist = w.history[-6:]
        wd = {
            "name": w.name, "brain": bid, "day": w.day + 1, "population": len(w.agents), "discoveries": len(w.first),
            "days_since_last_discovery": round(since_disc, 1),
            "trend": [{"day": h.get("day"), "pop": h.get("population"), "disc": h.get("discoveries"),
                       "structures": h.get("structures")} for h in hist],
            "plans": plans,
            "plan_authorship": dict(d.authorship),
            "step_sources": dict(d.step_sources),
            "recent_steps": list(d.recent_steps),
            "model_share_pct": _pct(plans.get("model", 0), decided),
            "routine_pct": _pct(plans.get("routine", 0), total_plans),
            "waiting_on_model_pct": _pct(d.waiting_ticks, d.model_ticks),
            "steps_ok": steps_ok, "steps_failed": steps_fail, "step_success_pct": _pct(steps_ok, steps_ok + steps_fail),
            "worst_verbs": [{"verb": v, "failed": f, "of": t} for v, f, t in worst],
            "top_failures": d.fail_reasons.most_common(6),
            "talk": {"said": d.said, "avg_listeners": round(d.heard / d.said, 1) if d.said else 0,
                     "addressed": d.addressed, "replied": d.replied, "reply_pct": _pct(d.replied, d.addressed)},
            "stuck": stuck[:6],
            "loops": dict(d.loops), "loop_examples": list(d.loop_examples)[-4:],
            "chief": chief_summary(w),
            "invariants": _invariants(rt, w),
            "decisions": outcomes.get(wid, {}),
            "opportunities": opportunities(w),
            "capability_use": capability_use(w),
        }
        out["worlds"][wid] = wd
        name = w.name
        if bid != "instinct" and decided >= 20 and wd["model_share_pct"] < 70:
            warn.append(f"{name}: only {wd['model_share_pct']}% of the plans that weren't routine came from the model; the "
                        f"rest were instinct ({plans.get('fallback', 0)} while the model was down, {plans.get('filler', 0)} "
                        f"while waiting)" + (f"; {plans['shed']} more were left to instinct because its queue was full"
                                             if plans.get("shed") else ""))
        if bid != "instinct" and d.model_ticks > 2000 and wd["waiting_on_model_pct"] > 40:
            warn.append(f"{name}: for {wd['waiting_on_model_pct']}% of the time a chit's model was still thinking and its "
                        f"instinct kept it busy")
        if steps_ok + steps_fail > 200 and wd["step_success_pct"] < 60:
            warn.append(f"{name}: only {wd['step_success_pct']}% of plan steps succeed; top failure: "
                        f"{d.fail_reasons.most_common(1)[0][0] if d.fail_reasons else '?'}")
        if w.tick > 240 * 4 and since_disc > 5:
            warn.append(f"{name}: no new discovery for {since_disc:.0f} days")
        if d.loops.get("model", 0) >= 5:
            warn.append(f"{name}: the model's plans looped {d.loops['model']} times (the same step failing for the same "
                        f"reason {LOOP_N} times in a row), e.g. {d.loop_examples[-1]['failure'] if d.loop_examples else '?'}")
        if stuck:
            warn.append(f"{name}: {len(stuck)} chit(s) stuck failing repeatedly, e.g. {stuck[0]['name']}: {stuck[0]['last']}")
        if w.flags.get("say") and d.addressed >= 10 and wd["talk"]["reply_pct"] < 20:
            warn.append(f"{name}: chits are spoken to but rarely answer ({wd['talk']['reply_pct']}% replies)")
        if w.tick > 240 * 10 and len(w.agents) < 6:
            warn.append(f"{name}: population is down to {len(w.agents)}")
    return out


def text(r: Dict[str, Any]) -> str:
    L = [f"LITTLE CHITS diagnostics · mode {r['mode']} · speed {r['speed']}{' (paused)' if r['paused'] else ''} · "
         f"{r['tps']} ticks/s{' · pacing to brains' if r['pacing_to_brain'] else ''}"]
    L.append("")
    L.append("WARNINGS" if r["warnings"] else "WARNINGS: none")
    L += [f"  ! {x}" for x in r["warnings"]]
    for bid, b in r["brains"].items():
        L.append("")
        L.append(f"BRAIN {b['label']} [{bid}] {b['url']} model={b['model'] or '?'} {'OK' if b['healthy'] else 'UNHEALTHY'}")
        L.append(f"  requests {b['requests']} ok {b['ok']} failed {b['failed']} unreadable {b['parse_failed']} "
                 f"repaired {b['repaired']} retried {b['retries']}")
        L.append(f"  latency p50 {b['latency_p50_ms']}ms p95 {b['latency_p95_ms']}ms · throughput {b['tok_s']} tok/s "
                 f"(per request {b['tok_s_request']}) · "
                 f"in flight {b['in_flight']}/{b['concurrency']} · queued {b['queued']}")
        L.append(f"  speed: {b['speed']['text']}")
        if b["last_error"]:
            L.append(f"  last error: {b['last_error'][:140]}")
    for wid, w in r["worlds"].items():
        L.append("")
        L.append(f"WORLD {wid} · brain {w['brain']} · day {w['day']} · pop {w['population']} · "
                 f"discoveries {w['discoveries']} (last {w['days_since_last_discovery']}d ago)")
        L.append("  trend: " + " | ".join(f"d{t['day']} pop{t['pop']} disc{t['disc']} bld{t['structures']}" for t in w["trend"]))
        L.append(f"  plans: {w['plans']} → model share {w['model_share_pct']}% · waiting on model {w['waiting_on_model_pct']}%")
        if w.get("decisions"):
            L.append(f"  model decisions: {w['decisions']}")
        L.append(f"  steps: {w['steps_ok']} ok / {w['steps_failed']} failed ({w['step_success_pct']}% ok)")
        c = w.get("chief") or {}
        if c.get("stages"):
            L.append(f"  chief's choice: {c['stages']} · ended {c['ended']} · asked->sent {c['ticks_asked_to_sent']} ticks, "
                     f"asked->answered {c['ticks_asked_to_answered']} ticks, queue {c['queue_ms']} ms, reply {c['latency_ms']} ms")
        if w["worst_verbs"]:
            L.append("  worst verbs: " + ", ".join(f"{v['verb']} {v['failed']}/{v['of']}" for v in w["worst_verbs"]))
        for reason, n in w["top_failures"]:
            L.append(f"    {n:>5}× {reason}")
        t = w["talk"]
        L.append(f"  talk: {t['said']} said · {t['avg_listeners']} listeners each · addressed {t['addressed']} · "
                 f"answered {t['replied']} ({t['reply_pct']}%)")
        gaps = sorted(((k, v) for k, v in w.get("opportunities", {}).items()
                       if k.startswith("design:") and k != "design:boat" and v["known_by"] and not v["sites_started"]),
                      key=lambda kv: (-kv[1]["affordable_by"], -kv[1]["known_by"]))[:5]
        for k, v in gaps:
            L.append(f"  not built yet: {k[7:]}: known by {v['known_by']}, affordable by {v['affordable_by']}, never started")
        for s in w["stuck"]:
            L.append(f"  stuck: {s['name']} ({s['fails_in_a_row']} fails in a row, {s['doing']}): {s['last']}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------- why is it slow?
_NOTHING_NEAR = re.compile(r"there is no (.+?) (?:anywhere )?nearby")
WHY_MAX = 5  # reasons shown per world
WHY_MIN_FAILS = 10  # a failure counts as a reason once it has happened this often


def _plural(n: int, one: str = "chit", many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _fix_line(design: str, opps: Dict[str, Any]) -> str:
    """What the report says about the building that would end a shortage. Nothing while nobody there knows it."""
    from .sim.items import DESIGNS

    name = DESIGNS[design].name
    o = opps.get(f"design:{design}")
    if o is None:  # (opportunities lists only what isn't standing)
        return f" A {name} is already built."
    if not o.get("known_by"):
        return ""
    if o.get("sites_started"):
        return f" A {name} is being built."
    if o.get("affordable_by"):
        return f" A {name} would fix it and {_plural(o['affordable_by'])} could build one."
    return f" A {name} would fix it. {_plural(o['known_by'])} know{'s' if o['known_by'] == 1 else ''} how, but none has the materials."


def _failure_line(key: str, n: int, opps: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """One of the report's top failures in words, and the building it names as the fix (if it names one)."""
    from .sim.buildings import PIT_OF
    from .sim.items import ITEMS

    verb, _, reason = key.partition(": ")
    m = _NOTHING_NEAR.search(reason)
    if m:
        item = next((k for k, it in ITEMS.items() if it.name == m.group(1)), None)
        fix = _fix_line(PIT_OF[item], opps) if item in PIT_OF else ""
        return f"No {m.group(1)} near home: {n} failed tries so far.{fix}", PIT_OF.get(item) if fix else None
    said = reason.strip().rstrip(".") + ("…" if len(reason) >= 70 else ".")  # (step_failed keeps 70 characters)
    return f"Chits keep failing to {verb.replace('_', ' ')}: {n} failed tries so far. They say: {said}", None


def _world_reasons(wd: Dict[str, Any], brains: Dict[str, Any]) -> List[Dict[str, Any]]:
    from .sim.items import DESIGNS

    out: List[tuple] = []  # (score, kind, text): the highest scores are shown

    def add(score: float, kind: str, text: str) -> None:
        out.append((score, kind, text))

    bid = wd.get("brain", "instinct")
    plans = wd.get("plans") or {}
    opps = wd.get("opportunities") or {}
    if bid != "instinct":
        b = brains.get(bid) or {}
        speed = b.get("speed") or {}
        decided = sum(plans.values()) - plans.get("routine", 0) - plans.get("duty", 0) - plans.get("shed", 0)
        share = wd.get("model_share_pct", 0)
        if b and not b.get("healthy", True):
            add(95, "model", "The model is not answering. Chits act on instinct until it does.")
        elif decided >= 20 and share < 70:
            if speed.get("level") == "slow":
                tail = f": it is too slow for {_plural(speed.get('chits', wd.get('population', 0)))}."
            else:
                tail = ". Instinct makes the rest."
            add(90 - share / 2, "model", f"The model answers only {share:g}% of decisions{tail}")
        if plans.get("shed", 0) >= 20:
            add(50, "model", f"{plans['shed']} decisions were left to instinct because the model's queue was full.")
        if wd.get("waiting_on_model_pct", 0) > 40:
            add(55, "model", f"Chits spend {wd['waiting_on_model_pct']:g}% of their time waiting for the model.")
    named: set = set()  # buildings a failure line already spoke of
    for i, (key, n) in enumerate((wd.get("top_failures") or [])[:3]):
        if n >= WHY_MIN_FAILS:
            line, fix = _failure_line(key, n, opps)
            named.add(fix)
            add(70 - 5 * i, "failure", line)
    steps = wd.get("steps_ok", 0) + wd.get("steps_failed", 0)
    if steps > 200 and wd.get("step_success_pct", 100) < 60:
        add(58, "steps", f"Only {wd['step_success_pct']:g}% of plan steps work.")
    stuck = wd.get("stuck") or []
    if stuck:
        s = stuck[0]
        add(45, "stuck", f"{_plural(len(stuck))} keep{'s' if len(stuck) == 1 else ''} failing the same step. "
                         f"{s['name']} failed {s['fails_in_a_row']} times in a row.")
    loops = (wd.get("loops") or {}).get("model", 0)
    if loops >= 5:
        add(42, "loops", f"The model repeated a failing step {LOOP_N} times in a row on {loops} occasions.")
    since = wd.get("days_since_last_discovery", 0)
    if wd.get("day", 0) > 4 and since > 3:
        add(min(65, 30 + 3 * since), "discovery", f"No new discovery for {since:.0f} days.")
    gaps = sorted(((k[7:], v) for k, v in opps.items()
                   if k.startswith("design:") and k != "design:boat" and k[7:] in DESIGNS and k[7:] not in named
                   and v.get("known_by")
                   and v.get("affordable_by") and not v.get("sites_started") and not v.get("upgrades_started")),
                  key=lambda kv: (-kv[1]["affordable_by"], -kv[1]["known_by"], kv[0]))
    for i, (key, v) in enumerate(gaps[:2]):
        add(36 - i, "not_built", f"Nobody has started a {DESIGNS[key].name}. {_plural(v['known_by'])} "
                                 f"know{'s' if v['known_by'] == 1 else ''} how and {v['affordable_by']} "
                                 f"{'has' if v['affordable_by'] == 1 else 'have'} the materials.")
    if wd.get("day", 0) > 10 and wd.get("population", 0) < 6:
        add(75, "population", f"Only {_plural(wd.get('population', 0))} {'is' if wd.get('population') == 1 else 'are'} left.")
    out.sort(key=lambda t: -t[0])
    return [{"kind": kind, "text": text} for _, kind, text in out[:WHY_MAX]]


def why_slow(r: Dict[str, Any]) -> Dict[str, Any]:
    """"Why is nothing happening?" for the observer: the report (report()) as a few plain sentences, the biggest
    reasons first. Every sentence is one of the report's own numbers put into words; nothing here looks at a world, so
    it can say nothing the report doesn't. Counts run since the game server last started (the counters live in memory).
    `game` holds what stops every world at once."""
    game: List[Dict[str, str]] = []
    dur = r.get("durability") or {}
    if dur.get("invalid_reason"):
        game.append({"kind": "invalid", "text": "This experiment run is marked invalid. It stays paused."})
    if dur.get("save_errors"):
        game.append({"kind": "save", "text": "A save failed. The game is paused until a save works."})
    elif r.get("paused"):
        game.append({"kind": "paused", "text": "The game is paused."})
    if r.get("pacing_to_brain") and not r.get("paused"):
        game.append({"kind": "pacing", "text": "The clock is waiting for a model to answer."})
    brains = r.get("brains") or {}
    return {"game": game,
            "worlds": {wid: {"name": wd.get("name", wid), "day": wd.get("day"), "brain": wd.get("brain", "instinct"),
                             "reasons": _world_reasons(wd, brains)}
                       for wid, wd in (r.get("worlds") or {}).items()}}


# the metrics a scorecard compares, and which way is better
SCORE_METRICS = (("era", max), ("discoveries", max), ("population", max), ("discoveries_per_100_decisions", max),
                 ("model_share_pct", max), ("step_success_pct", max), ("projects_done", max), ("latency_p50_ms", min))


def scorecard(rt) -> Dict[str, Any]:
    """Which model is building the better civilisation: one row per world, side by side, from what the game already
    records. Decisions are counted since the game last started (they're kept in memory), so discoveries per 100
    decisions counts the discoveries made in the same stretch."""
    from .brain.mind import CIVIC_STYLES
    from .sim.world import ERAS

    r = report(rt)
    rows = []
    for wid, wd in r["worlds"].items():
        w = rt.worlds[wid]
        bid = wd["brain"]
        br = r["brains"].get(bid, {})
        # the plan decisions adopted (a running count: the record deque keeps only the last 5000, which made the
        # ratio climb as a game went on); escalation is a rate, so the recent records serve
        recs = [x for x in rt.mind.decisions if x.get("world") == wid and x.get("style") not in CIVIC_STYLES]
        adopted = rt.mind.adopted.get(wid, 0)
        choices = [x["choice"] for x in recs if isinstance(x.get("choice"), dict)]
        since = getattr(w, "_scored_from", 0)
        found = sum(1 for v in w.first.values() if v.get("tick", 0) >= since)
        era = w.era()[0]
        civ = getattr(w, "civic", None) or {}
        rows.append({
            "world": wid, "name": w.name, "culture": w.culture, "brain": bid, "label": br.get("label", "instinct"),
            "model": br.get("model"), "day": wd["day"], "era": era, "era_name": ERAS[era][0],
            "population": wd["population"], "discoveries": wd["discoveries"], "discoveries_this_session": found,
            "decisions": adopted, "decision_outcomes": wd["decisions"],
            "discoveries_per_100_decisions": round(100 * found / adopted, 1) if adopted else None,
            "model_share_pct": wd["model_share_pct"] if bid != "instinct" else None,
            "step_success_pct": wd["step_success_pct"],
            "escalation_pct": _pct(sum(1 for c in choices if c.get("escalated")), len(choices)) if choices else None,
            "latency_p50_ms": br.get("latency_p50_ms"), "latency_p95_ms": br.get("latency_p95_ms"),
            "tok_s": br.get("tok_s"), "projects_done": len(civ.get("done", [])), "deaths": len(w.dead),
        })
    lead = {}
    for k, better in SCORE_METRICS:
        vals = [(row[k], row["world"]) for row in rows if row[k] is not None]
        if len(vals) >= 2 and len({v for v, _ in vals}) > 1:
            lead[k] = better(vals)[1]
    controlled = getattr(rt, "contract", "play") == "experiment"
    warning = "" if controlled else (
        "Play mode: not a controlled comparison. Instinct filler, focus, pacing and per-brain settings may "
        "differ; use a strict experiment for publishable model comparisons."
    )
    return {"rows": rows, "lead": lead, "controlled": controlled, "warning": warning,
            "note": "Decisions, escalations and latency count since the game last started; era, discoveries and "
                    "population are the whole run."}

