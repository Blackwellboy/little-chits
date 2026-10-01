"""Run an experiment: every seed x arm, resumable, with the protocol's interventions applied identically in each arm."""

from __future__ import annotations

import asyncio
import json
import math
import os
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..sim.agent import TICKS_PER_DAY
from . import assign, extract
from .spec import Arm, ExperimentSpec, SpecError


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)  # a run is either written whole or not at all (a killed batch resumes cleanly)


def start(spec: ExperimentSpec, out, commit: str = "unknown", started: str = "") -> Path:
    """Pre-register: write the manifest and the seal before any run (or check them, when resuming)."""
    out = Path(out)
    man = out / "manifest.json"
    if man.exists():
        old = json.loads(man.read_text())
        if old["fingerprint"] != spec.fingerprint():
            raise SpecError("this directory holds a different protocol: resume it with its own, or use a new --out")
        return out
    out.mkdir(parents=True, exist_ok=True)
    digest = assign.seal(spec, out)
    from . import treatment as T

    from ..brain import prompt as P

    _write_json(man, {"protocol": spec.to_dict(), "fingerprint": spec.fingerprint(), "commit": commit, "started": started,
                      "prompt_version": P.PROMPT_VERSION,
                      "treatments": {pid: T.coverage(p) for pid, p in spec.treatments.items()},
                      "python": platform.python_version(), "assignment_sha256": digest, "blind": spec.blind,
                      "runs": [{"seed": s, "labels": assign.run_order(spec, i)} for i, s in enumerate(spec.seeds)]})
    return out


def apply_intervention(w, iv) -> str:
    """The same exogenous shock, whatever the arm. Returns what happened, for the run's log."""
    kind = iv["kind"] if isinstance(iv, dict) else iv.kind
    days = float(iv["days"] if isinstance(iv, dict) else iv.days)
    params = (iv.get("params") if isinstance(iv, dict) else iv.params) or {}
    if kind in ("drought", "storm", "snow", "rain"):
        w.set_weather(kind, days)
        return f"{kind} for {days:g} days"
    if kind == "hard_winter":
        w.cold_until = w.tick + int(days * TICKS_PER_DAY)
        w.emit("hard_winter", "A hard winter sets in", 3)
        return f"hard winter for {days:g} days"
    if kind == "ore_shortage":  # every ore deposit within `radius` of the village is emptied
        from ..sim import terrain as T

        pts = [s.center() for s in w.structures.values()] or [w.spawn]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        r = float(params.get("radius", 40))
        n = 0
        for i, k in enumerate(w.res_kind):
            if k == T.R_ORE and w.res_amt[i] > 0 and math.hypot(i % w.w - cx, i // w.w - cy) <= r:
                w.res_amt[i] = 0
                w.dirty_res.add(i)
                n += 1
        w.emit("ore_shortage", f"The ore near the village gave out ({n} deposits)", 3)
        return f"ore shortage: {n} deposits within {r:g} tiles emptied"
    raise SpecError(f"unknown intervention {kind}")


def run_one(protocol: Dict[str, Any], out: str, seed: int, label: str, arm: Dict[str, Any]) -> Dict[str, Any]:
    """One sealed world: instinct synchronously, or a model under the strict lockstep experiment contract."""
    from ..brain.instinct import Instinct
    from ..sim.world import World

    spec = ExperimentSpec.from_dict(protocol)
    arm = Arm(**arm)
    rd = Path(out) / "runs" / f"{seed}_{label}"
    if (rd / "result.json").exists():
        return json.loads((rd / "result.json").read_text())
    rd.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    w = World("A", label, seed, arm.culture, spec.size, spec.population)
    w.flags.update(arm.flags)
    if arm.treatment:  # (kept apart from result.json, which the blind report reads: who was told names the arm)
        from . import treatment as T

        _write_json(rd / "treatment.json", T.apply(w, spec.treatments[arm.treatment], seed))
    founders = len(w.agents)
    if arm.brain != "instinct":
        return asyncio.run(_run_model_one(spec, arm, w, rd, founders, seed, t0))
    ins = Instinct()
    from .. import invariants as INV

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    by_day: Dict[int, List[Any]] = {}
    for iv in spec.interventions:
        by_day.setdefault(iv.day, []).append(iv)
    daily, log = [], []
    for t in range(TICKS_PER_DAY * spec.days):
        if t % TICKS_PER_DAY == 0:
            day = t // TICKS_PER_DAY + 1
            for iv in by_day.get(day, []):
                log.append({"day": day, "kind": iv.kind, "what": apply_intervention(w, iv)})
        w.step(hook)
        INV.enforce(w, spec.contract, arm.brain)  # every tick (F2): a run that broke a hard invariant isn't a result
        if (t + 1) % (TICKS_PER_DAY * spec.sample_every) == 0:
            daily.append(extract.row(w, founders))
    with open(rd / "daily.jsonl", "w") as f:
        for r in daily:
            f.write(json.dumps(r) + "\n")
    result = {"seed": seed, "label": label, "days": spec.days, "wall_s": round(time.monotonic() - t0, 1),
              "interventions": log, **extract.summary(w, daily, founders, blind=spec.blind)}
    _write_json(rd / "result.json", result)  # last: its presence means the run is complete
    return result



async def _run_model_one(spec: ExperimentSpec, arm: Arm, w, rd: Path, founders: int, seed: int,
                         t0: float) -> Dict[str, Any]:
    """A model arm under the same core contract as make experiment: strict, lockstep, seeded, no instinct filler."""
    from .. import invariants as INV
    from ..brain.mind import Mind
    from ..brain.llm import BrainConfig
    from ..tools.experiment import BRAIN_FAIL_STOP

    cfg = BrainConfig(**spec.brains[arm.brain])
    mind = Mind(None)
    mind.strict = True
    mind.repair = False
    brain = mind.upsert(dict(cfg.__dict__))
    mind.assign(w, cfg.id)
    brain.cooldown = False  # lockstep: wall-clock backoff would only add noise
    brain.seed_base = seed
    by_day: Dict[int, List[Any]] = {}
    for iv in spec.interventions:
        by_day.setdefault(iv.day, []).append(iv)
    daily, log = [], []
    try:
        for t in range(TICKS_PER_DAY * spec.days):
            while mind._tasks:
                await asyncio.wait(list(mind._tasks))
            if brain.stats.consecutive_fail >= BRAIN_FAIL_STOP:
                raise INV.InvariantBroken([{"kind": "brain_unavailable", "level": "hard", "tick": w.tick,
                                            "what": f"{brain.label}: {brain.stats.consecutive_fail} requests failed in a row"}])
            if t % TICKS_PER_DAY == 0:
                day = t // TICKS_PER_DAY + 1
                for iv in by_day.get(day, []):
                    log.append({"day": day, "kind": iv.kind, "what": apply_intervention(w, iv)})
            w.step(mind.hook)
            INV.enforce(w, spec.contract, cfg.id)
            if (t + 1) % (TICKS_PER_DAY * spec.sample_every) == 0:
                daily.append(extract.row(w, founders))
        while mind._tasks:  # record/finish the final tick's already-issued calls, like make experiment
            await asyncio.wait(list(mind._tasks))
    finally:
        await mind.close()
    with open(rd / "daily.jsonl", "w") as f:
        for row in daily:
            f.write(json.dumps(row) + "\n")
    st = brain.stats
    result = {"seed": seed, "label": w.name, "days": spec.days, "wall_s": round(time.monotonic() - t0, 1),
              "interventions": log,
              "compute": {"requests": st.requests, "failed_requests": st.failed, "tokens_in": st.tokens_in,
                          "tokens_out": st.tokens_out, "tokens": st.tokens_in + st.tokens_out},
              **extract.summary(w, daily, founders)}
    _write_json(rd / "result.json", result)
    return result

def pending(spec: ExperimentSpec, out) -> List[tuple]:
    names = assign.labels(spec)
    arms = {a.name: a for a in spec.arms}
    todo = []
    for i, seed in enumerate(spec.seeds):
        for label in assign.run_order(spec, i):
            if not (Path(out) / "runs" / f"{seed}_{label}" / "result.json").exists():
                todo.append((seed, label, arms[names[label]]))
    return todo


def run(spec: ExperimentSpec, out, jobs: int = 1, commit: str = "unknown", started: str = "",
        progress=None) -> Dict[str, Any]:
    for a in spec.arms:
        if a.brain != "instinct" and os.environ.get("CHITS_LAB_ALLOW_MODELS") != "1":
            raise SpecError("a model arm runs only with CHITS_LAB_ALLOW_MODELS=1 (the owner's go-ahead for the GPUs)")
    out = start(spec, out, commit, started)
    todo = pending(spec, out)
    protocol = spec.to_dict()
    done = 0
    if jobs <= 1:
        for seed, label, arm in todo:
            run_one(protocol, str(out), seed, label, arm.__dict__)
            done += 1
            if progress:
                progress(done, len(todo))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(run_one, protocol, str(out), s, l, a.__dict__) for s, l, a in todo]
            for f in futs:
                f.result()
                done += 1
                if progress:
                    progress(done, len(todo))
    return {"out": str(out), "ran": done, "total": len(spec.seeds) * len(spec.arms)}


def results(out) -> List[Dict[str, Any]]:
    """Every finished run's result, with its daily rows."""
    rows = []
    for rd in sorted((Path(out) / "runs").glob("*_*")):
        if (rd / "result.json").exists():
            r = json.loads((rd / "result.json").read_text())
            r["daily"] = [json.loads(line) for line in (rd / "daily.jsonl").read_text().splitlines() if line.strip()]
            rows.append(r)
    return rows
