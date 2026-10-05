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
from ..sim.world import scheme_now
from . import assign, extract
from .spec import Arm, ExperimentSpec, SpecError


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)  # a run is either written whole or not at all (a killed batch resumes cleanly)


def start(spec: ExperimentSpec, out, commit: str = "unknown", started: str = "", retry: bool = False) -> Path:
    """Pre-register: write the manifest and the seal before any run (or check them, when resuming)."""
    out = Path(out)
    man = out / "manifest.json"
    if man.exists():
        old = json.loads(man.read_text())
        if old["fingerprint"] != spec.fingerprint():
            raise SpecError("this directory holds a different protocol: resume it with its own, or use a new --out")
        if old.get("rng_scheme", 2) != scheme_now():  # (manifests from before scheme 3 have none: they ran on 2)
            raise SpecError(f"this directory's runs used random-number scheme {old.get('rng_scheme', 2)} and this build "
                            f"makes worlds with {scheme_now()}: its remaining runs would not be comparable")
        migrate_legacy(out)  # (raw records from before invalid runs were kept blind)
        if pending(spec, out, retry=retry):
            check_servers(spec)  # (a resumed batch checks its servers again)
        return out
    servers = check_servers(spec)  # (before anything is written: a wrong server is not an experiment)
    out.mkdir(parents=True, exist_ok=True)
    digest = assign.seal(spec, out)
    from . import treatment as T

    from ..brain import prompt as P
    from ..tools.experiment import SAMPLING

    _write_json(man, {"protocol": spec.to_dict(), "fingerprint": spec.fingerprint(), "commit": commit, "started": started,
                      "prompt_version": P.PROMPT_VERSION, "rng_scheme": scheme_now(),
                      "treatments": {pid: T.coverage(p) for pid, p in spec.treatments.items()},
                      "python": platform.python_version(), "assignment_sha256": digest, "blind": spec.blind,
                      # model arms: every call of a tick answered before the next, each request seeded from the run's
                      # seed and its prompt, and this sampling unless a brain's extra_body sets its own
                      "lockstep": True, "request_seeds": True, "sampling": dict(SAMPLING), "servers": servers,
                      "model_only": spec.model_only,
                      **({"model_only_note": MODEL_ONLY_NOTE} if spec.model_only else {}),
                      "runs": [{"seed": s, "labels": assign.run_order(spec, i),
                                **({"card_swapped": spec.swapped(i)} if spec.card_swap else {})}
                               for i, s in enumerate(spec.seeds)]})
    return out


MODEL_ONLY_NOTE = ("diagnostic run, not a comparison: every arm ran without the body's reflexes, and model arms with "
                   "the full prompt and no instinct plans")


def check_servers(spec: ExperimentSpec) -> Dict[str, List[str]]:
    """Ask every server a model arm will use (card swaps included) what it serves. A server that doesn't answer, or
    doesn't serve the model a brain names, stops the experiment before it starts: a swapped port would otherwise
    measure the wrong model under the right name. Returns base URL -> the models it lists, for the manifest."""
    from ..brain.llm import BrainConfig, LLMBrain

    want: Dict[str, set] = {}
    cfgs: Dict[str, Dict[str, Any]] = {}
    for a in spec.arms:
        if a.brain == "instinct":
            continue
        for i in range(min(2, len(spec.seeds))):
            cfg = spec.brain_for(a.brain, i)
            cfgs[cfg["base_url"]] = cfg
            want.setdefault(cfg["base_url"], set()).add(cfg.get("model") or "")
    if not want:
        return {}

    async def ask() -> Dict[str, List[str]]:
        out = {}
        for url, cfg in cfgs.items():
            b = LLMBrain(BrainConfig(**cfg))
            try:
                out[url] = sorted(await b.list_models())
            except Exception as e:
                raise SpecError(f"the model server at {url} didn't answer: {e}") from None
            finally:
                await b.close()
        return out

    served = asyncio.run(ask())
    for url, models in want.items():
        for m in sorted(models - {""}):
            # (llama.cpp may list the file's whole path, or the --alias it was given)
            if not any(x == m or x.endswith("/" + m) for x in served[url]):
                raise SpecError(f"the server at {url} serves {', '.join(served[url]) or 'nothing'}, not {m}")
    return served


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
    """One sealed world: instinct synchronously, or a model under the strict lockstep experiment contract. A hard
    invariant break ends only this run: it is written to invalid.json and returned as {"invalid": True, ...}."""
    from .. import invariants as INV

    spec = ExperimentSpec.from_dict(protocol)
    arm = Arm(**arm)
    rd = Path(out) / "runs" / f"{seed}_{label}"
    if (rd / "result.json").exists():
        return json.loads((rd / "result.json").read_text())
    rd.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        result = _run_one(spec, arm, rd, seed, label, t0)
    except INV.InvariantBroken as e:
        # this run's outcome, not the batch's end: recorded, and the other runs carry on
        return _record_invalid(spec, rd, seed, label, arm, e.broken, t0)
    tries = attempts(rd)
    if tries:
        result["invalid_attempts"] = tries
        _write_json(rd / "result.json", result)
    return result


LAST_CALLS = 5  # an invalid run keeps its last model calls (from its tape), for working out what went wrong


_PLAIN_WORDS = {"the", "and", "arm", "model", "models", "server", "brain", "instruct", "chat", "base", "http", "https"}


def identities(spec: ExperimentSpec, arm: Arm) -> List[str]:
    """Every string that would tell which arm a run belongs to, and its common spellings: the arm's name; its
    brain's id; its label, and each word of it; its model file, without its extension too, and the name before the
    first dash ("gemma" of gemma-4-12b-it.gguf); every server it may use (card swap included), with and without the
    scheme and trailing slash, and its host:port. Matched in any case (redact). Longest first, so a URL goes before
    its host and a label before its words."""
    out = {arm.name, arm.brain} - {"instinct", ""}
    cfg = spec.brains.get(arm.brain) or {}
    out |= {str(cfg.get(k) or "") for k in ("id", "label")}
    out |= {w for w in str(cfg.get("label") or "").split() if len(w) >= 3 and any(c.isalpha() for c in w)}
    model = str(cfg.get("model") or "")
    if model:
        stem = model.rsplit("/", 1)[-1]
        stem = stem.rsplit(".", 1)[0] if "." in stem and stem.rsplit(".", 1)[1].isalpha() else stem
        out |= {model, stem}
        head = stem.split("-", 1)[0]
        if len(head) >= 3 and any(c.isalpha() for c in head):
            out.add(head)
    for u in (cfg.get("base_url") or "", spec.card_swap.get(arm.brain, "")):
        if u:
            bare = u.split("//", 1)[-1]
            out |= {u, u.rstrip("/"), bare, bare.rstrip("/"), bare.split("/", 1)[0]}
    return sorted((s for s in out if s.strip() and s.lower() not in _PLAIN_WORDS), key=len, reverse=True)


def blind_names(spec: ExperimentSpec) -> Dict[str, str]:
    """Every arm's identities (lower-cased) -> "arm <its label>". A blind record redacts all of them, not only its own
    arm's: a run's text can name another arm's model too. A string two arms share names neither: "an arm"."""
    from . import assign

    out: Dict[str, str] = {}
    for label, name in assign.labels(spec).items():
        arm = next(a for a in spec.arms if a.name == name)
        for s in identities(spec, arm):
            k = s.lower()
            out[k] = "an arm" if k in out and out[k] != f"arm {label}" else f"arm {label}"
    return out


def redact(obj: Any, names: Dict[str, str]) -> Any:
    """`obj` with every identity in `names` (lower-cased identity -> what to say instead) replaced in every string
    inside it: whole words only, in any case (a server may lower-case a model's name, a client a host's), and a URL
    with any trailing slash."""
    import re

    if not names:
        return obj
    keys = sorted(names, key=len, reverse=True)  # (a URL before its host, a label before its words)
    pat = re.compile("|".join(f"(?<![A-Za-z0-9_]){re.escape(n)}/?(?![A-Za-z0-9_])" for n in keys), re.IGNORECASE)

    def to(m):
        return names[m.group(0).lower().rstrip("/") if m.group(0).lower() not in names else m.group(0).lower()]

    def go(x):
        if isinstance(x, str):
            return pat.sub(to, x)
        if isinstance(x, dict):
            return {k: go(v) for k, v in x.items()}
        if isinstance(x, list):
            return [go(v) for v in x]
        return x

    return go(obj)


def _record_invalid(spec: ExperimentSpec, rd: Path, seed: int, label: str, arm: Arm, broken: List[Dict[str, Any]],
                    t0: float) -> Dict[str, Any]:
    """Why this run isn't a result, twice. invalid-sealed.json is the raw record (the arm, its brain, every break
    and its last model calls, word for word): like server.json, only an unblinded report reads it. invalid.json is
    what the blind report and the command line read: the same, with every arm's identities (names, brains' ids,
    labels and their words, models, servers; any case) replaced by that arm's blind label (blind_names). A brain_unavailable break names the model that
    stopped answering, and the first real study's report would have printed it (Codex on #122). Every break is
    kept, however many there were."""
    first = broken[0] if broken else {"kind": "unknown", "what": "", "tick": 0}
    last, n = [], 0
    tape = rd / "tape.jsonl"
    if tape.exists():
        lines = [x for x in tape.read_text().splitlines() if x.strip()]
        n = len(lines)
        for line in lines[-LAST_CALLS:]:
            e = json.loads(line)
            reply = e.get("reply") or {}
            last.append({"n": e.get("n"), "key": (e.get("key") or "")[:16], "error": e.get("error"),
                         "text": (reply.get("text") or "")[:400] or None, "finish_reason": reply.get("finish_reason"),
                         "latency_ms": reply.get("latency_ms")})
    by_kind: Dict[str, int] = {}
    for b in broken:
        by_kind[b.get("kind", "?")] = by_kind.get(b.get("kind", "?"), 0) + 1
    raw = {"seed": seed, "label": label, "arm": arm.name, "brain": arm.brain, "kind": first.get("kind"),
           "what": first.get("what"), "tick": first.get("tick"), "day": int(first.get("tick") or 0) // TICKS_PER_DAY + 1,
           "breaks": len(broken), "by_kind": by_kind, "broken": list(broken), "wall_s": round(time.monotonic() - t0, 1),
           "tape_calls": n, "last_calls": last}
    _write_json(rd / "invalid-sealed.json", raw)  # (first: invalid.json is what marks the run as done)
    blind = redact({k: v for k, v in raw.items() if k not in ("arm", "brain")}, blind_names(spec))
    _write_json(rd / "invalid.json", blind)
    return {"invalid": True, **blind}


def attempts(rd: Path) -> int:
    """How many earlier attempts at this run were invalid (kept as invalid-attempt-N.json by a retry)."""
    return len(list(Path(rd).glob("invalid-attempt-*.json")))


def retry_invalid(rd: Path) -> None:
    """Set an invalid run aside for a declared retry: its record and tape stay, numbered, beside the new attempt."""
    k = attempts(rd) + 1
    os.replace(rd / "invalid.json", rd / f"invalid-attempt-{k}.json")
    if (rd / "invalid-sealed.json").exists():
        os.replace(rd / "invalid-sealed.json", rd / f"invalid-sealed-attempt-{k}.json")
    if (rd / "tape.jsonl").exists():
        os.replace(rd / "tape.jsonl", rd / f"tape-attempt-{k}.jsonl")


def _run_one(spec: ExperimentSpec, arm: Arm, rd: Path, seed: int, label: str, t0: float) -> Dict[str, Any]:
    from ..brain.instinct import Instinct
    from ..sim.world import World

    w = World("A", label, seed, arm.culture, spec.size, spec.population)
    w.flags.update(arm.flags)
    w.model_only = spec.model_only  # (a diagnostic: the body's reflexes off, sim/actions.py)
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
    chit_ticks = 0
    for t in range(TICKS_PER_DAY * spec.days):
        if t % TICKS_PER_DAY == 0:
            day = t // TICKS_PER_DAY + 1
            for iv in by_day.get(day, []):
                log.append({"day": day, "kind": iv.kind, "what": apply_intervention(w, iv)})
        chit_ticks += len(w.agents)
        w.step(hook)
        INV.enforce(w, spec.contract, arm.brain)  # every tick (F2): a run that broke a hard invariant isn't a result
        if (t + 1) % (TICKS_PER_DAY * spec.sample_every) == 0:
            daily.append(extract.row(w, founders))
    with open(rd / "daily.jsonl", "w") as f:
        for r in daily:
            f.write(json.dumps(r) + "\n")
    summ = extract.summary(w, daily, founders, blind=spec.blind)
    summ["final"].update(opportunities(w, chit_ticks, 0))
    result = {"seed": seed, "label": label, "days": spec.days, "wall_s": round(time.monotonic() - t0, 1),
              "interventions": log, **summ, **_model_only(spec, w)}
    _write_json(rd / "result.json", result)  # last: its presence means the run is complete
    return result


def opportunities(w, chit_ticks: int, requests: int, wait_s: float = 0.0) -> Dict[str, Any]:
    """How much thinking a world's chits got, per chit-day (a chit alive for one day = 1 chit-day): requests to its
    model; the share of model-brained chit time spent waiting for an answer (near 0 in lockstep, where the world
    waits instead); the wall seconds the world stood waiting for its model's answers (the lockstep wait: a cost, not
    a world fact); and the share of finished steps that came from the model's plans (the rest are reflexes).
    Reported, never equalised: an equal budget would change behaviour and needs its own pre-registered design
    (research item 43)."""
    from .. import diag

    d = diag.of(w)
    chit_days = chit_ticks / TICKS_PER_DAY
    steps = sum(d.outcomes.values())
    model_steps = d.outcomes.get(("model", "ok"), 0) + d.outcomes.get(("model", "fail"), 0)
    return {"requests_per_chit_day": round(requests / chit_days, 3) if chit_days else 0.0,
            "waiting_share": round(d.waiting_ticks / d.model_ticks, 3) if d.model_ticks else 0.0,
            "wait_seconds_per_chit_day": round(wait_s / chit_days, 4) if chit_days else 0.0,
            "model_step_share": round(model_steps / steps, 3) if steps else 0.0}



async def _run_model_one(spec: ExperimentSpec, arm: Arm, w, rd: Path, founders: int, seed: int,
                         t0: float) -> Dict[str, Any]:
    """A model arm under the same core contract as make experiment: strict, lockstep, seeded, no instinct filler."""
    from .. import invariants as INV
    from ..brain.mind import Mind
    from ..brain.llm import BrainConfig
    from ..brain.tape import BrainTape
    from ..tools.experiment import BRAIN_FAIL_STOP, SAMPLING

    raw = spec.brain_for(arm.brain, spec.seeds.index(seed))  # (its other card's server on a swapped seed)
    # the same explicit sampling as make experiment, so two servers' own defaults don't become a difference
    raw["extra_body"] = {**SAMPLING, **(raw.get("extra_body") or {})}
    cfg = BrainConfig(**raw)
    # which server answered is kept apart from result.json, like a treatment: the blind report never reads it
    _write_json(rd / "server.json", {"brain": cfg.id, "base_url": cfg.base_url, "model": cfg.model,
                                     "card_swapped": spec.swapped(spec.seeds.index(seed)),
                                     "extra_body": cfg.extra_body})
    mind = Mind(None)
    mind.strict = True
    mind.repair = False
    mind.model_only = spec.model_only
    brain = mind.upsert(dict(cfg.__dict__))
    mind.assign(w, cfg.id)
    brain.cooldown = False  # lockstep: wall-clock backoff would only add noise
    brain.seed_base = seed
    brain.tape = BrainTape(rd / "tape.jsonl", "record")  # every call and its answer: the run can be replayed (item 39)
    by_day: Dict[int, List[Any]] = {}
    for iv in spec.interventions:
        by_day.setdefault(iv.day, []).append(iv)
    daily, log = [], []
    chit_ticks, wait_s = 0, 0.0
    try:
        for t in range(TICKS_PER_DAY * spec.days):
            waited = time.monotonic()
            while mind._tasks:
                await asyncio.wait(list(mind._tasks))
            wait_s += time.monotonic() - waited
            if brain.stats.consecutive_fail >= BRAIN_FAIL_STOP:
                raise INV.InvariantBroken([{"kind": "brain_unavailable", "level": "hard", "tick": w.tick,
                                            "what": f"{brain.label}: {brain.stats.consecutive_fail} requests failed in a row"}])
            if t % TICKS_PER_DAY == 0:
                day = t // TICKS_PER_DAY + 1
                for iv in by_day.get(day, []):
                    log.append({"day": day, "kind": iv.kind, "what": apply_intervention(w, iv)})
            chit_ticks += len(w.agents)
            w.step(mind.hook)
            INV.enforce(w, spec.contract, cfg.id)
            if (t + 1) % (TICKS_PER_DAY * spec.sample_every) == 0:
                daily.append(extract.row(w, founders))
        waited = time.monotonic()
        while mind._tasks:  # record/finish the final tick's already-issued calls, like make experiment
            await asyncio.wait(list(mind._tasks))
        wait_s += time.monotonic() - waited
    finally:
        await mind.close()
    with open(rd / "daily.jsonl", "w") as f:
        for row in daily:
            f.write(json.dumps(row) + "\n")
    st = brain.stats
    summ = extract.summary(w, daily, founders, blind=spec.blind)
    summ["final"].update(opportunities(w, chit_ticks, st.requests, wait_s))
    result = {"seed": seed, "label": w.name, "days": spec.days, "wall_s": round(time.monotonic() - t0, 1),
              "interventions": log,
              "compute": {"requests": st.requests, "failed_requests": st.failed, "tokens_in": st.tokens_in,
                          "tokens_out": st.tokens_out, "tokens": st.tokens_in + st.tokens_out,
                          "chit_days": round(chit_ticks / TICKS_PER_DAY, 2), "tape_calls": brain.tape.recorded},
              **summ, **_model_only(spec, w)}
    _write_json(rd / "result.json", result)
    return result


def _model_only(spec: ExperimentSpec, w) -> Dict[str, Any]:
    """A model-only run's own record: the reflexes were off, and what they would have done (diag.reflex_would)."""
    if not spec.model_only:
        return {}
    from .. import diag

    return {"model_only": {"reflexes": False, "reflex_would": diag.reflex_would_summary(w)}}


def pending(spec: ExperimentSpec, out, retry: bool = False) -> List[tuple]:
    """Runs still to do. An invalid run counts as done unless `retry`: rerunning only the runs that broke, until they
    don't, would keep the lucky draws (a model whose server falls over on hard seeds would end up measured on the
    easy ones). A retry is for a cause outside the experiment, such as a server that went down, and is declared."""
    names = assign.labels(spec)
    arms = {a.name: a for a in spec.arms}
    todo = []
    for i, seed in enumerate(spec.seeds):
        for label in assign.run_order(spec, i):
            rd = Path(out) / "runs" / f"{seed}_{label}"
            if not (rd / "result.json").exists() and (retry or not (rd / "invalid.json").exists()):
                todo.append((seed, label, arms[names[label]]))
    return todo


def migrate_legacy(out) -> List[str]:
    """Records written before invalid runs were kept blind: one raw invalid.json (or invalid-attempt-N.json) that
    names the arm, its brain and maybe its model. Each is moved to its sealed name (invalid-sealed.json,
    invalid-sealed-attempt-N.json) and a redacted copy written in its place, both marked "migrated". Runs on every
    blind read (analyze, the CLI's listing) and on resume, before anything else reads them. Returns what it moved."""
    out = Path(out)
    man = out / "manifest.json"
    if not man.exists():
        return []
    spec = None
    moved = []
    for p in sorted((out / "runs").glob("*_*/invalid*.json")):
        if p.name.startswith("invalid-sealed"):
            continue
        sealed = p.with_name(p.name.replace("invalid", "invalid-sealed", 1))
        try:
            raw = json.loads(p.read_text())
        except ValueError:
            continue
        if sealed.exists() or not ({"arm", "brain"} & set(raw)):
            continue
        if spec is None:
            spec = ExperimentSpec.from_dict(json.loads(man.read_text())["protocol"])
        label = str(raw.get("label") or p.parent.name.split("_", 1)[-1])
        names = blind_names(spec)
        # (and the record's own arm, should the protocol no longer name it)
        own = Arm(name=str(raw.get("arm") or ""), brain=str(raw.get("brain") or "instinct"))
        for s in identities(spec, own):
            names.setdefault(s.lower(), f"arm {label}")
        broken = raw.get("broken") or []
        by_kind: Dict[str, int] = {}
        for b in broken:
            by_kind[b.get("kind", "?")] = by_kind.get(b.get("kind", "?"), 0) + 1
        when = time.strftime("%Y-%m-%dT%H:%M:%S")
        raw = {"breaks": len(broken), "by_kind": by_kind, **raw,
               "migrated": {"at": when, "from": p.name, "note": "a record from before invalid runs were kept blind; "
                                                                 "it kept at most 20 breaks"}}
        _write_json(sealed, raw)
        blind = redact({k: v for k, v in raw.items() if k not in ("arm", "brain")}, names)
        _write_json(p, blind)
        moved.append(str(p.relative_to(out)))
    return moved


def invalid(out, sealed: bool = False) -> List[Dict[str, Any]]:
    """Every run that broke a hard invariant, in seed/label order: its blind record (invalid.json), or with `sealed`
    the raw one (invalid-sealed.json, for an unblinded report only; the blind record where none was kept). A legacy
    raw record is migrated first, so a blind read never sees it."""
    migrate_legacy(out)
    rows = []
    for p in sorted((Path(out) / "runs").glob("*_*/invalid.json")):
        s = p.with_name("invalid-sealed.json")
        rows.append(json.loads((s if sealed and s.exists() else p).read_text()))
    return rows


def run(spec: ExperimentSpec, out, jobs: int = 1, commit: str = "unknown", started: str = "",
        progress=None, retry_invalid_runs: bool = False) -> Dict[str, Any]:
    """Every pending run. Returns how many ran, and how many runs of the experiment are invalid (any, now)."""
    for a in spec.arms:
        if a.brain != "instinct" and os.environ.get("CHITS_LAB_ALLOW_MODELS") != "1":
            raise SpecError("a model arm runs only with CHITS_LAB_ALLOW_MODELS=1 (the owner's go-ahead for the GPUs)")
    out = start(spec, out, commit, started, retry=retry_invalid_runs)
    todo = pending(spec, out, retry=retry_invalid_runs)
    for seed, label, _ in todo:  # (a declared retry: the invalid attempt is kept, numbered, beside the new one)
        rd = Path(out) / "runs" / f"{seed}_{label}"
        if (rd / "invalid.json").exists():
            retry_invalid(rd)
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
    return {"out": str(out), "ran": done, "total": len(spec.seeds) * len(spec.arms), "invalid": len(invalid(out))}


def results(out) -> List[Dict[str, Any]]:
    """Every finished run's result, with its daily rows."""
    rows = []
    for rd in sorted((Path(out) / "runs").glob("*_*")):
        if (rd / "result.json").exists():
            r = json.loads((rd / "result.json").read_text())
            r["daily"] = [json.loads(line) for line in (rd / "daily.jsonl").read_text().splitlines() if line.strip()]
            rows.append(r)
    return rows
