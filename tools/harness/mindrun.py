"""Run a harness world with its chits driven through the game's Mind (brain/mind.py), by the scripted model
(tools/harness/scripted.py) or by a real OpenAI-compatible server, and watch the model path.

The instinct runs (run.py without ``--mind``) never build a prompt, parse a reply, repair a plan or escalate a choice,
so they are blind to everything that goes wrong there. Here every chit belongs to one brain, as in the game, and a
ModelProbe counts what the model path did: where each finished step came from, how the replies parsed, which plans
were adopted, went stale or failed, which model steps failed at once, and the failures that repeat.

    world, probe, mprobe, low = run_world(42, 20, mind="scripted")
    mprobe.report()

A scripted run is deterministic for a seed: replies take world ticks, not wall time (scripted.TickClock), and the
world waits for every request to reach that clock before its next tick. A run against a URL is not: the world moves on
at ``tick_seconds`` per tick and replies land when they land, as in the game.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter, deque
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from chits import diag
from chits.sim.actions import DONE, describe_step

TICKS_PER_SEC = 2.0  # the game's pace at 1x (brain/mind.py): a scripted reply of n ticks "took" n / 2 seconds
LOOP_AFTER = 3  # the same step failing for the same reason more than this many times in a row is a loop
EXAMPLES = 12  # failures kept whole for the autopsy
_NUM = re.compile(r"\d+(\.\d+)?")


def origin_of(step: Dict[str, Any], a) -> str:
    """Who planned a step, as diag.action_finished counts it."""
    if step.get("_reflex"):
        return "reflex"
    if step.get("_filler"):
        return "filler"
    return str(step.get("_origin") or a.plan_source or "unknown")


def signature(step: Dict[str, Any], result: str) -> str:
    """The verb, its object as the model wrote it (a null ``what`` shows as None) and the reason, numbers folded."""
    verb = str(step.get("do"))
    if "what" in step:
        obj = step["what"]
    else:
        obj = step.get("with") or step.get("target") or step.get("site") or step.get("at") or ""
    if isinstance(obj, list):
        obj = "+".join(map(str, obj))
    return f"{verb} {obj}".strip() + " | " + _NUM.sub("#", str(result))[:70]


class ModelProbe:
    """Watches the model path of one world. Attach before the run (``with``); it only reads."""

    def __init__(self, world, mind, loop_after: int = LOOP_AFTER, model=None) -> None:
        self.w, self.mind, self.loop_after, self.model = world, mind, loop_after, model
        self.decisions: Counter = Counter()  # "style:x", "parse:x", "outcome:x" -> n
        self.rejected_steps = 0
        self.escalation = Counter()  # requested / granted / denied:budget / denied:queue
        self.recs: Dict[str, Dict[str, Any]] = {}  # decision id -> what the autopsy needs about it
        self.model_steps: Counter = Counter()  # ok / failed / failed_at_once
        self.at_once_verb: Counter = Counter()
        self.at_once_reason: Counter = Counter()
        self.model_fails: Counter = Counter()  # signature of a failed model step -> n, over the whole run
        self.repairs: Counter = Counter()  # first step of a repaired plan: ok / failed
        self._first_seen: set = set()  # decision ids whose first step has finished
        self._streak: Dict[str, list] = {}  # agent id -> [signature, origin class, times in a row, its loop entry]
        self.loops: Dict[tuple, Dict[str, Any]] = {}  # (origin class, signature) -> episodes, longest, chits
        self.examples: deque = deque(maxlen=EXAMPLES)  # failed-at-once model steps, whole
        self.loop_examples: Dict[tuple, Dict[str, Any]] = {}
        self.reply_ticks: Counter = Counter()  # world ticks from asking a chit's mind to its answer -> how many (run loop)

    # ------------------------------------------------------------------ wiring
    def __enter__(self) -> "ModelProbe":
        self._prev_cb = self.mind.on_decision
        self.mind.on_decision = self._decision
        self._orig = diag.action_finished
        orig, me = self._orig, self

        def action_finished(world, a, step, result):
            orig(world, a, step, result)
            if world is me.w:
                me._finished(a, step, result)

        diag.action_finished = action_finished
        return self

    def __exit__(self, *exc) -> None:
        diag.action_finished = self._orig
        self.mind.on_decision = self._prev_cb

    # ------------------------------------------------------------------ decisions
    def _decision(self, rec: Dict[str, Any]) -> None:
        style = rec.get("style") or "full"
        self.decisions[f"style:{style}"] += 1
        self.decisions[f"parse:{rec.get('parse')}"] += 1
        self.decisions[f"outcome:{rec.get('outcome')}"] += 1
        self.rejected_steps += int(rec.get("rejected_steps") or 0)
        ch = rec.get("choice") if isinstance(rec.get("choice"), dict) else {}
        if ch.get("escalation_requested"):
            self.escalation["requested"] += 1
            self.escalation["granted" if ch.get("escalated") else f"denied:{ch.get('denial')}"] += 1
        if rec.get("outcome") == "adopted" and style not in ("vote", "trade-offer", "chief-project"):
            a = self.w.agents.get(rec.get("agent"))
            self.recs[rec["request_id"]] = {
                "style": style, "parse": rec.get("parse"), "choice": ch.get("executed") or ch.get("requested"),
                "plan": [describe_step(s) for s in (a.plan if a else [])],
                "reply": (self.model.texts.get(rec.get("response_hash") or "", "") if self.model else "")[:300],
                "repair_of": rec.get("repair_step") and f'{rec.get("repair_step")}: {rec.get("repair_reason")}'}

    # ------------------------------------------------------------------ steps
    def _finished(self, a, step, result) -> None:
        origin = origin_of(step, a)
        model = origin.startswith("model")
        cls = "model" if model else origin
        if result == DONE:
            self._streak.pop(a.id, None)
        if model:
            did = step.get("_decision_id")
            first = did is not None and did not in self._first_seen
            if first:
                self._first_seen.add(did)
                if origin == "model_repaired":
                    self.repairs["ok" if result == DONE else "failed"] += 1
            if result == DONE:
                self.model_steps["ok"] += 1
                return
            self.model_steps["failed"] += 1
            sig = signature(step, result)
            self.model_fails[sig] += 1
            started = step.get("_tick_started", self.w.tick)
            if self.w.tick - started <= 1:  # it could not run at all
                self.model_steps["failed_at_once"] += 1
                self.at_once_verb[str(step.get("do"))] += 1
                self.at_once_reason[f"{step.get('do')}: {_NUM.sub('#', str(result))[:70]}"] += 1
                if len(self.examples) < EXAMPLES:
                    self.examples.append(self._example(a, step, result, origin, sig))
        elif result == DONE:
            return
        else:
            sig = signature(step, result)
        s = self._streak.get(a.id)
        if s is None or s[0] != sig or s[1] != cls:
            s = self._streak[a.id] = [sig, cls, 0, None]
        s[2] += 1
        if s[2] == self.loop_after + 1:
            key = (cls, sig)
            L = self.loops.setdefault(key, {"origin": cls, "failure": sig, "episodes": 0, "longest": 0, "chits": set()})
            L["episodes"] += 1
            L["chits"].add(a.id)
            s[3] = L
            if model and key not in self.loop_examples:
                self.loop_examples[key] = self._example(a, step, result, origin, sig)
        if s[3] is not None:
            s[3]["longest"] = max(s[3]["longest"], s[2])

    def _example(self, a, step, result, origin, sig) -> Dict[str, Any]:
        rec = self.recs.get(step.get("_decision_id") or "", {})
        return {"day": self.w.tick // 240, "tick": self.w.tick, "chit": a.name, "source": origin,
                "decision": {k: rec.get(k) for k in ("style", "parse", "choice") if rec.get(k)},
                "plan": rec.get("plan", []), "step": describe_step(step), "result": str(result)[:120],
                "repair_of": rec.get("repair_of"), "reply": rec.get("reply", ""), "failure": sig}

    # ------------------------------------------------------------------ results
    def report(self, why: bool = True) -> Dict[str, Any]:
        d = diag.of(self.w)
        src = dict(sorted(d.step_sources.items()))
        total = sum(src.values()) or 1
        brains = {}
        for b in self.mind.brains.values():
            st = b.stats
            brains[b.id] = {"requests": st.requests, "ok": st.ok, "failed": st.failed, "parse_failed": st.parse_failed,
                            "repaired": st.repaired, "retries": st.retries, "skipped": st.skipped,
                            "last_error": st.last_error[:120]}
        loops = sorted(({**L, "chits": len(L["chits"])} for L in self.loops.values()),
                       key=lambda L: (-L["episodes"], -L["longest"], L["failure"]))
        out = {
            "steps_by_source": src,
            "steps_by_source_pct": {k: round(100.0 * n / total, 1) for k, n in src.items()},
            "plans": dict(sorted(d.plans.items())),
            "reply_ticks": {str(k): self.reply_ticks[k] for k in sorted(self.reply_ticks)},
            "brain": brains,
            "decisions": {k: self.decisions[k] for k in sorted(self.decisions)},
            "rejected_steps": self.rejected_steps,
            "escalation": dict(sorted(self.escalation.items())),
            "repairs": {"asked": self.decisions.get("style:repair", 0), "first_step_ok": self.repairs["ok"],
                        "first_step_failed": self.repairs["failed"]},
            "model_steps": {k: self.model_steps[k] for k in ("ok", "failed", "failed_at_once")},
            "failed_at_once_by_verb": dict(self.at_once_verb.most_common()),
            "failed_at_once_by_reason": self.at_once_reason.most_common(10),
            "model_failures": self.model_fails.most_common(10),
            "loops": loops[:20],
            "model_loops": sum(L["episodes"] for L in loops if L["origin"] == "model"),
            "diag_loops": dict(sorted(d.loops.items())),
        }
        if self.model is not None:
            out["planted"] = dict(sorted(self.model.planted.items()))
            out["answered"] = dict(sorted(self.model.answered.items()))
        if why:
            out["why"] = why_summary(self.w, self.mind)
        return out

    def autopsy_text(self) -> str:
        L: List[str] = []
        loops = [x for x in self.report(why=False)["loops"] if x["origin"] == "model"]
        if loops:
            L.append(f"=== model-path loops: the same model step failing for the same reason more than "
                     f"{self.loop_after} times in a row")
            for x in loops:
                L.append(f"    {x['episodes']} episodes, {x['chits']} chits, longest {x['longest']}: {x['failure']}")
                ex = self.loop_examples.get(("model", x["failure"]))
                if ex:
                    L += _example_lines(ex)
        if self.examples:
            L.append(f"=== model steps that failed at once (first {len(self.examples)})")
            for ex in self.examples:
                L += _example_lines(ex)
        return "\n".join(L)


def _example_lines(ex: Dict[str, Any]) -> List[str]:
    dec = ", ".join(f"{k} {v}" for k, v in ex["decision"].items())
    out = [f"    day {ex['day']} t{ex['tick']} {ex['chit']}: source {ex['source']}" + (f" ({dec})" if dec else ""),
           f"        plan: {' -> '.join(ex['plan']) or '?'}",
           f"        step: {ex['step']}  =>  {ex['result']}"]
    if ex.get("repair_of"):
        out.append(f"        repairing: {ex['repair_of']}")
    if ex.get("reply"):
        out.append(f"        reply: {ex['reply'][:200]}")
    return out


def why_summary(world, mind) -> List[str]:
    """/api/why for this world (diag.report, then diag.why_slow), with a stand-in for the runtime."""
    rt = SimpleNamespace(mode="single", speed=1, paused=False, tps=0.0, waiting_on_brain=False, recorder=None,
                         worlds={world.id: world}, mind=mind, contract="play")
    try:
        r = diag.why_slow(diag.report(rt))
    except Exception as e:  # (a report never breaks a run)
        return [f"(why failed: {type(e).__name__}: {e})"]
    return [x["text"] for wd in r["worlds"].values() for x in wd["reasons"]]


# ---------------------------------------------------------------------------------------------- the run
async def _settle(mind, clock, brain, limit: int = 1_000_000) -> None:
    """Let every request run until it waits on the clock (or behind one that does)."""
    for _ in range(limit):
        live = sum(1 for t in mind._tasks if not t.done())
        if live <= clock.waiting() + brain.sem.waiting():
            return
        await asyncio.sleep(0)
    raise RuntimeError("the mind's requests never settled")


def _pin_latency(brain, model) -> None:
    """A scripted reply's latency is its ticks at the 1x pace, not the wall time it took here (which would make
    Mind.lead and the speed rating depend on this machine)."""
    ms = model.plan_ticks / TICKS_PER_SEC * 1000
    brain.stats.latency_ms_avg = ms
    if brain.latencies and brain.latencies[-1] != ms:
        brain.latencies.clear()
        brain.latencies.append(ms)


async def _run(seed, days, size, chits, culture, mind_spec, style, bad_rate, bad_kinds, choice_ticks, plan_ticks,
               slots, loop_after, tick_seconds):
    import httpx

    from chits.brain.mind import Mind
    from chits.sim.world import World
    from probe import Probe
    from scripted import ScriptedModel, ScriptedTransport, TickClock

    scripted = mind_spec == "scripted"
    w = World("A", "A", seed, culture, size, chits)
    mind = Mind(None)
    brain = mind.upsert({"id": "scripted" if scripted else "model", "label": "scripted" if scripted else mind_spec,
                         "base_url": "http://scripted.invalid/v1" if scripted else mind_spec,
                         "model": "scripted" if scripted else "", "prompt_style": style, "max_concurrency": slots})
    model = clock = transport = None
    if scripted:
        model = ScriptedModel(seed, bad_rate, bad_kinds, choice_ticks, plan_ticks)
        clock = TickClock()
        transport = ScriptedTransport(model, clock)
        brain._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        brain.cooldown = False  # (LLMBrain's back-off is in wall time; the scripted model never fails a request)
    mind.assign(w, brain.id)
    p = Probe(w)
    mp = ModelProbe(w, mind, loop_after, model)
    mp.transport = transport
    low = len(w.agents)

    asked: Dict[str, int] = {}  # agent id -> the tick its mind was asked for a plan

    def hook(world, a):
        before, was = a.plan_id, a.thinking
        mind.hook(world, a)
        p.seen[a.id] = a
        if a.plan_id != before:
            p.note_plan(a)
        if a.thinking and not was:
            asked[a.id] = world.tick

    try:
        with p, mp:
            for _ in range(240 * days):
                w.step(hook)
                p.after_tick()
                low = min(low, len(w.agents))
                if scripted:
                    clock.advance()
                    await _settle(mind, clock, brain)
                    _pin_latency(brain, model)
                else:
                    await asyncio.sleep(tick_seconds)
                for aid, t0 in list(asked.items()):
                    a = w.agents.get(aid)
                    if a is None or not a.thinking:  # its reply came back (or it died waiting)
                        del asked[aid]
                        if a is not None:
                            mp.reply_ticks[w.tick - t0] += 1
            report = mp.report()
    finally:
        await mind.close()
    return w, p, mp, low, report


def run_world(seed: int, days: int, size: int = 128, chits: int = 18, culture: str = "direct",
              mind: str = "scripted", style: str = "cascade", bad_rate: float = 0.15, bad_kinds=None,
              choice_ticks: int = 1, plan_ticks: int = 8, slots: int = 8, loop_after: int = LOOP_AFTER,
              tick_seconds: float = 0.5):
    """One world with every chit on one brain: ``mind`` is "scripted" or an OpenAI-compatible base URL.
    Returns (world, Probe, ModelProbe, lowest population, the ModelProbe's report)."""
    if mind != "scripted" and not re.match(r"^https?://", mind):
        raise ValueError(f"--mind takes 'scripted' or a server URL such as http://127.0.0.1:18191/v1, not {mind!r}")
    return asyncio.run(_run(seed, days, size, chits, culture, mind, style, bad_rate, bad_kinds, choice_ticks,
                            plan_ticks, slots, loop_after, tick_seconds))
