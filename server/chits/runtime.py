"""Runs the twin worlds forever (browser or no browser), persists them, and fans out frames."""

from __future__ import annotations

import asyncio
import json
import shutil
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import theme, views
from .brain.mind import INSTINCT, Mind
from .recorder import Recorder
from .sim.agent import TICKS_PER_DAY
from .sim.world import CULTURE_FLAGS, ERAS, World
from .store import Store

log = logging.getLogger("chits.runtime")

# ticks per second at each speed; a day is 240 ticks, so 1x = 2 minutes per in-game day
SPEEDS = {0: 0, 1: 2, 2: 4, 5: 10, 10: 20, 25: 50, 100: 400}
MIN_SIZE, MAX_SIZE = 64, 512


def _pace_default() -> bool:
    """Play games run at full speed (instinct covers a chit while its model thinks); CHITS_PACE=1 slows them instead."""
    return os.environ.get("CHITS_PACE", "0") == "1"


# How a game is set up. Every world in a match starts from the same seed.
MODES: Dict[str, Dict[str, Any]] = {
    # two worlds, identical in every way: the model is the only difference
    "versus": {"worlds": ["A", "B"], "culture": {"A": "direct", "B": "direct"}},
    # one world, one model: just watch it grow
    "single": {"worlds": ["A"], "culture": {"A": "direct"}},
    # the culture experiment: A can talk, teach and write; B can only watch and leave marks
    "culture": {"worlds": ["A", "B"], "culture": {"A": "direct", "B": "stigmergy"}},
    # Age of Chitpires (T34): two talking civilisations that can find each other by boat. A play mode, not a clean experiment
    "rivals": {"worlds": ["A", "B"], "culture": {"A": "direct", "B": "direct"}, "contact": True},
}


def normalize_mode(m: Optional[str]) -> str:
    m = (m or "").strip().lower()
    m = {"minds": "versus", "vs": "versus", "twin": "culture", "one": "single"}.get(m, m)
    return m if m in MODES else "versus"


CONTRACTS = ("play", "experiment")
_COMMIT: Optional[str] = None


def source_commit() -> str:
    global _COMMIT
    if _COMMIT is None:
        try:
            import subprocess

            _COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                                     capture_output=True, text=True, timeout=3).stdout.strip() or "unknown"
        except Exception:
            _COMMIT = "unknown"
    return _COMMIT


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def legacy_brains_warning(brains_path: Path, repo_root: Optional[Path] = None) -> str:
    """Explain a legacy root brains.local.json without ever treating it as live configuration."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    legacy = root / "brains.local.json"
    if legacy.exists() and legacy.resolve() != brains_path.resolve():
        return f"ignoring legacy {legacy}; live brain config is {brains_path} (or set CHITS_BRAINS explicitly)"
    return ""


class Runtime:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or os.environ.get("CHITS_DATA_DIR", "data")).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        theme.load(self.data_dir)  # (before any world is made or named)
        self.store = Store(self.data_dir / "chits.sqlite")
        brains_path = Path(os.environ.get("CHITS_BRAINS", self.data_dir / "brains.json")).resolve()
        self.brains_path = brains_path
        warning = legacy_brains_warning(brains_path)
        if warning and not os.environ.get("CHITS_BRAINS"):
            log.warning(warning)
        self.first_run = not brains_path.exists()
        self.autodetected: List[Dict[str, Any]] = []
        self.mind = Mind(brains_path)
        preset = os.environ.get("CHITS_BRAINS_PRESET", "").strip()
        if preset and Path(preset).exists():
            self.mind.merge_preset(Path(preset))  # e.g. configs/dual-gpu.json: 5090 -> A, 3090 -> B
        self.mode = normalize_mode(self.store.get_meta("mode") or os.environ.get("CHITS_MODE")
                                   or ("single" if os.environ.get("CHITS_WORLDS") == "single" else "")
                                   or os.environ.get("CHITS_TWIN") or "versus")
        self._env_brain()
        self.contract = self.store.get_meta("contract") or "play"
        if self.contract not in CONTRACTS:
            self.contract = "play"
        self.run_id = self.store.get_meta("run_id") or uuid.uuid4().hex
        self.contact = (self.store.get_meta("contact") or os.environ.get("CHITS_CONTACT", "0")) in ("1", "true")
        self.mind.strict = self.contract == "experiment"
        self.mind.on_decision = self.store.save_decision
        self.worlds: Dict[str, World] = {}
        self.forks: Dict[str, Dict[str, Any]] = {}  # 🔀 what-if copies stepping alongside (self.fork); in memory only
        self._fork_seq = 0
        self.speed = _env_int("CHITS_SPEED", 1)
        self.paused = False
        self.pace_to_brain = _pace_default() or self.contract == "experiment"
        self.clients: Dict[Any, asyncio.Queue] = {}
        self.gen = 0  # stream generation: bumps on reset/restore/epoch fork so clients drop stale messages
        self._pending_events: Dict[str, List[Any]] = {}
        self._last_save_day: Dict[str, int] = {}
        self.save_errors: Dict[str, str] = {}  # F19: a failed durable checkpoint freezes the sim until an explicit retry
        self.invalid_reason = ""  # experiment runs stay invalid once durability was lost, even if a later retry succeeds
        self._resetting = False  # while a new match is built (in a worker thread), the loop doesn't step
        self._recorded_day: Optional[int] = None  # the last day handed to the recorder
        self.recorder = Recorder(self)
        self._task: Optional[asyncio.Task] = None
        self._bcast: Optional[asyncio.Task] = None
        self.tps = 0.0
        self.waiting_on_brain = False
        self.load_or_create()
        # A brand-new world gets a durable tick-0 checkpoint before it starts moving. Restored worlds are already
        # durable at the tick stored in SQLite. If this first write fails the Runtime still comes up, but paused.
        for w in self.worlds.values():
            if getattr(w, "_durable_tick", -1) < 0:
                try:
                    self._checkpoint(w)
                except Exception:
                    log.exception("initial checkpoint failed for %s; simulation is paused", w.id)
        self.record_code_stretch()

    # -------------------------------------------------------------- setup
    def _env_brain(self) -> None:
        """CHITS_MODEL_URL=http://host:port/v1 [CHITS_MODEL_NAME=...] drops a model straight in."""
        url = os.environ.get("CHITS_MODEL_URL", "").strip()
        if not url:
            return
        cfg = {"id": "env", "label": os.environ.get("CHITS_MODEL_LABEL", "") or "", "base_url": url,
               "model": os.environ.get("CHITS_MODEL_NAME", ""), "api_key": os.environ.get("CHITS_MODEL_KEY", ""),
               "max_concurrency": _env_int("CHITS_MODEL_CONCURRENCY", 6), "enabled": True}
        self.mind.upsert(cfg)
        for wid in ("A", "B"):
            self.mind.world_brain.setdefault(wid, "env")
        self.mind.world_brain.update({"A": "env", "B": "env"})

    def load_or_create(self) -> None:
        for wid in MODES[self.mode]["worlds"]:
            try:
                snap = self.store.load_world(wid)
                if snap:
                    w = World.from_dict(snap)
                    self._adopt(w)
                    if self.store.has_future_events(w):
                        if self.contract == "experiment":
                            raise RuntimeError("legacy events extend beyond the saved checkpoint")
                        w.fork_epoch("recovered checkpoint; later legacy events retained in the previous timeline")
                        self.store.save_world(w.to_dict())
                    self._attach(w)
                    log.info("resumed world %s at tick %s", wid, w.tick)
                    continue
            except Exception as e:
                if self.contract == "experiment":
                    raise RuntimeError(f"could not restore world {wid} of an experiment run: {e}") from e
                log.warning("could not restore %s (%s); setting it aside and starting fresh", wid, e)
                self.store.quarantine_world(wid, f"{type(e).__name__}: {e}")
                w = self._create(wid)
                w.emit("notice", f"An unreadable save of {w.name} was set aside; a fresh world was started", 4)
                continue
            self._create(wid)

    def _adopt(self, w: World) -> None:
        """A world just read from a checkpoint or a save point: the events it carries are stored under the timeline
        they happened in (gaps filled, nothing twice), and only what comes after them is new. Otherwise the first
        checkpoint after a fork copied the snapshot's last 1500 events into the new timeline, and the chronicle told
        them twice."""
        self.store.append_events(w, list(w.events))
        w._stored_seq = w.seq
        w._durable_tick = w.tick

    def _create(self, wid: str, seed: Optional[int] = None, chits: Optional[int] = None,
                size: Optional[int] = None) -> World:
        seed = seed if seed is not None else _env_int("CHITS_SEED", 1234)
        n = chits if chits is not None else _env_int("CHITS_PER_WORLD", 18)
        size = max(MIN_SIZE, min(MAX_SIZE, size or _env_int("CHITS_WORLD_SIZE", 192)))
        # every world in a match is built from the same seed: same island, same chits, same rules,
        # so the only thing that differs is the mind (or, in "culture" mode, one recorded law)
        culture = MODES[self.mode]["culture"][wid]
        label = {"direct": "Direct culture", "stigmergy": "Stigmergy only"}[culture]
        w = World(wid, theme.world_name(wid), seed, culture, size, n, label=label)
        self._attach(w)
        return w

    def _attach(self, w: World) -> None:
        self.worlds[w.id] = w
        w._scored_from = w.tick  # the scorecard's decisions are kept in memory from here (diag.scorecard)
        if not hasattr(w, "_durable_tick"):
            w._durable_tick = -1
        w.incident_sink = self._incident_from
        self._pending_events[w.id] = []
        w._pending_actions = []
        w.on_action_outcome = w._pending_actions.append
        w.listeners = [lambda ev, wid=w.id: self._pending_events[wid].append(ev),
                       lambda ev, wid=w.id: self.recorder.on_event(wid, ev)]  # 🎞 big moments, filmed live
        brain = self.mind.world_brain.get(w.id, INSTINCT)
        if brain != INSTINCT and brain not in self.mind.brains and self.contract != "experiment":
            brain = INSTINCT
        for a in w.agents.values():
            if a.brain == INSTINCT or (a.brain not in self.mind.brains and self.contract != "experiment"):
                a.brain = brain

    def reset(self, seed: Optional[int] = None, chits: Optional[int] = None, size: Optional[int] = None,
              mode: Optional[str] = None, brains: Optional[Dict[str, str]] = None,
              contract: Optional[str] = None, contact: Optional[bool] = None) -> None:
        """Start a new match (see _reset). The loop stops stepping meanwhile: it used to keep stepping the old
        worlds, so the new A and B started ticks apart and old decisions landed in the new run's records."""
        self._check_reset(mode, contract, contact)  # a rejected reset leaves the running match untouched
        self._resetting = True
        try:
            self.mind.new_match()
            self._reset(seed, chits, size, mode, brains, contract, contact)
        finally:
            self._resetting = False

    def _check_reset(self, mode: Optional[str], contract: Optional[str], contact: Optional[bool]) -> None:
        contract = contract or self.contract
        if contract not in CONTRACTS:
            raise ValueError(f"contract must be one of {', '.join(CONTRACTS)}")
        new_contact = self.contact if contact is None else bool(contact)
        if normalize_mode(mode or self.mode) == "rivals":
            new_contact = True
        if contract == "experiment" and new_contact:
            raise ValueError("contact between islands is not allowed in an experiment run")

    def _reset(self, seed: Optional[int] = None, chits: Optional[int] = None, size: Optional[int] = None,
               mode: Optional[str] = None, brains: Optional[Dict[str, str]] = None,
               contract: Optional[str] = None, contact: Optional[bool] = None) -> None:
        """Start a new match. `mode` picks the worlds (see MODES); `brains` maps world id -> brain id;
        `contract` is "play" (resilient) or "experiment" (strict); `contact` allows boats between islands."""
        contract = contract or self.contract
        if contract not in CONTRACTS:
            raise ValueError(f"contract must be one of {', '.join(CONTRACTS)}")
        new_contact = self.contact if contact is None else bool(contact)
        if normalize_mode(mode or self.mode) == "rivals":
            new_contact = True  # the whole point of rivals mode
        if contract == "experiment" and new_contact:
            raise ValueError("contact between islands is not allowed in an experiment run")
        self.store.wipe()
        self.save_errors = {}
        self.invalid_reason = ""
        self.paused = False
        self.forks = {}  # a new match: the old one's what-ifs go with it
        stories = self.data_dir / "stories"
        if stories.exists():  # the Weeks panel and story pages served old games' pages with the same numbers
            dest = self.data_dir / "runs" / self.run_id / "stories"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(stories), str(dest))
        self.contact = new_contact
        self.mind.strict = contract == "experiment"
        if contract == "experiment":
            self.pace_to_brain = True
        elif self.contract == "experiment":
            self.pace_to_brain = _pace_default()  # leaving an experiment: back to the normal default
        self.contract = contract
        self.run_id = uuid.uuid4().hex
        self.gen += 1
        self.recorder.new_run()
        for k, v in (("contract", contract), ("run_id", self.run_id), ("contact", "1" if new_contact else "0"),
                     ("sandbox_modified", "0"), ("sandbox_reasons", "[]")):
            self.store.set_meta(k, v)
        if mode:
            self.mode = normalize_mode(mode)
            self.store.set_meta("mode", self.mode)
        for wid in list(self.worlds):
            if wid not in MODES[self.mode]["worlds"]:
                del self.worlds[wid]
                self._pending_events.pop(wid, None)
        for wid, bid in (brains or {}).items():
            if wid in MODES[self.mode]["worlds"] and (bid == INSTINCT or bid in self.mind.brains):
                self.mind.world_brain[wid] = bid
        self.mind.save()
        for wid in MODES[self.mode]["worlds"]:
            self._create(wid, seed, chits, size)
        self.save_all()  # tick 0 is an explicit durability boundary for every new match
        self.write_manifest(chits)
        self._broadcast_snapshots()

    # -------------------------------------------------------------- run contract
    def mark_sandbox(self, reason: str) -> None:
        """Someone reached into the world from outside (god mode, a rewind...). Permanent for this run."""
        if self.contract == "experiment":
            raise PermissionError("not allowed in an experiment run")
        reasons = json.loads(self.store.get_meta("sandbox_reasons") or "[]")
        reasons.append(reason)
        self.store.set_meta("sandbox_modified", "1")
        self.store.set_meta("sandbox_reasons", json.dumps(reasons[-50:]))
        self.write_manifest()

    def record_code_stretch(self) -> List[Dict[str, Any]]:
        """Which code ran which days: whenever the game starts on a different commit than last time, note the commit
        and each world's day. (The live islands got upgrades mid-run; a comparison should know where each began.)"""
        try:
            stretches = json.loads(self.store.get_meta("code_stretches") or "[]")
        except ValueError:
            stretches = []
        commit = source_commit()
        if not stretches or stretches[-1].get("commit") != commit:
            stretches.append({"commit": commit, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                              "day": {wid: w.day + 1 for wid, w in self.worlds.items()}})
            self.store.set_meta("code_stretches", json.dumps(stretches[-200:]))
        return stretches

    def manifest(self, chits: Optional[int] = None) -> Dict[str, Any]:
        from .brain import prompt as P
        from .sim.world import RNG_SCHEME

        worlds = {}
        first = next(iter(self.worlds.values()), None)
        for wid, w in self.worlds.items():
            bid = self.mind.world_brain.get(wid, INSTINCT)
            b = self.mind.brains.get(bid)
            brain: Any = "instinct"
            if b:
                c = b.cfg
                brain = {"id": c.id, "base_url": c.base_url, "model": c.model or b.stats.resolved_model,
                         "temperature": c.temperature, "max_tokens": c.max_tokens, "max_concurrency": c.max_concurrency,
                         "json_mode": c.json_mode, "disable_thinking": c.disable_thinking,
                         "prompt_style": c.prompt_style, "escalate_below": c.escalate_below,
                         "escalate_share": c.escalate_share, "focus": getattr(c, "focus", None),
                         "extra_body": {k: v for k, v in (c.extra_body or {}).items()
                                        if not any(s in k.lower() for s in ("key", "token", "secret", "auth"))}}
            worlds[wid] = {"culture": w.culture, "flags": dict(w.flags), "brain": brain, "uuid": w.uuid, "epoch": w.epoch}
        return {"run_id": self.run_id, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "contract": self.contract,
                "mode": self.mode, "seed": first.seed if first else None, "size": first.w if first else None,
                "chits": chits if chits is not None else (len(first.agents) if first else None),
                "worlds": worlds, "prompt_version": P.PROMPT_VERSION, "rng_scheme": RNG_SCHEME,
                "source_commit": source_commit(),
                "code_stretches": json.loads(self.store.get_meta("code_stretches") or "[]"),
                "pacing": self.pace_to_brain, "contact": self.contact,
                "first_contact_tick": int(self.store.get_meta("first_contact_tick") or 0) or None,
                "valid": not bool(self.invalid_reason), "invalid_reason": self.invalid_reason or None,
                "experiment_ended": json.loads(self.store.get_meta("experiment_ended") or "null"),
                "durable_tick": {wid: getattr(w, "_durable_tick", -1) for wid, w in self.worlds.items()},
                "sandbox_modified": self.store.get_meta("sandbox_modified") == "1",
                "sandbox_reasons": json.loads(self.store.get_meta("sandbox_reasons") or "[]")}

    def write_manifest(self, chits: Optional[int] = None) -> Dict[str, Any]:
        m = self.manifest(chits)
        old = self.data_dir / "runs" / self.run_id / "manifest.json"
        if old.exists() and chits is None:
            try:
                m["created"] = json.loads(old.read_text()).get("created", m["created"])
                m["chits"] = json.loads(old.read_text()).get("chits", m["chits"])
            except ValueError:
                pass
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(json.dumps(m, indent=2))
        return m

    async def autodetect(self) -> List[Dict[str, Any]]:
        """Plug and play: on a first run with no model configured, look for model servers on this machine.
        Two or more found -> model vs model (World A on the first, World B on the second, same island).
        One found -> a single world driven by it. None -> both worlds idle on instinct until a model is added.
        CHITS_AUTODETECT=0 turns this off."""
        if os.environ.get("CHITS_AUTODETECT") == "0" or os.environ.get("CHITS_MODEL_URL") or not self.first_run:
            return []
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("CHITS_SCAN_PORTS"):
            return []  # never let a test run grab the real GPUs on this machine
        if any(b != INSTINCT for b in self.mind.world_brain.values()):
            return []
        from .brain.llm import scan_local

        try:
            found = await scan_local()
        except Exception as e:  # never block startup on a scan
            log.warning("model scan failed: %s", e)
            return []
        added: List[Dict[str, Any]] = []
        for f in found[:2]:
            port = f["base_url"].rsplit(":", 1)[-1].split("/")[0]
            cfg = {"id": f"auto{port}", "label": f"{f['models'][0]} :{port}", "base_url": f["base_url"],
                   "model": f["models"][0], "max_concurrency": f["suggested"]["max_concurrency"], "enabled": True}
            self.mind.upsert(cfg)
            added.append(cfg)
        self.autodetected = added
        if len(added) >= 2:
            self.reset(mode="versus", brains={"A": added[0]["id"], "B": added[1]["id"]})
        elif added:
            self.reset(mode="single", brains={"A": added[0]["id"]})
        if added:
            log.info("found model server(s): %s -> %s mode", ", ".join(c["base_url"] for c in added), self.mode)
        else:
            log.info("no local model server found; open ⚙ Brains (🔍 Scan) once one is running")
        self.mind.save()
        return added

    # -------------------------------------------------------------- loop
    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        self._bcast = asyncio.create_task(self._broadcast_loop())
        self.recorder.watch()

    async def stop(self) -> None:
        for t in (self._task, self._bcast):
            if t:
                t.cancel()
        self.recorder.stop()
        self.save_all()
        await self.mind.close()

    def _brain_backlog(self) -> bool:
        """True when too many model-driven chits are idle waiting for a reply."""
        waiting = total = 0
        for w in self.worlds.values():
            for a in w.agents.values():
                if a.brain != INSTINCT:
                    total += 1
                    if a.thinking and (not a.plan or a.plan[0].get("_filler")):
                        waiting += 1
        return total > 0 and waiting / total > 0.3

    async def _loop(self) -> None:
        acc = 0.0
        last = time.perf_counter()
        count = 0
        t_rate = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt = now - last
            last = now
            rate = 0 if self.paused else SPEEDS.get(self.speed, 2)
            self.mind.speed_scale = max(1.0, rate / 2)  # a plan's age limit stretches with the game's speed
            # "waiting" only when pacing really holds the world back: at 1x it already runs at the pace cap
            self.waiting_on_brain = self.pace_to_brain and rate > 2 and self._brain_backlog()
            if self.waiting_on_brain:
                rate = min(rate, 2)  # let the models catch up instead of letting instinct take over
            acc = min(acc + dt * rate, 60)
            steps = 0
            t0 = time.perf_counter()
            while acc >= 1.0 and not self._resetting and not self.paused and time.perf_counter() - t0 < 0.05:
                self.step_worlds()
                for w in self.worlds.values():
                    self._maybe_save(w)
                self._maybe_record()
                acc -= 1.0
                steps += 1
            count += steps
            if now - t_rate > 1.0:
                self.tps = count / (now - t_rate)
                count = 0
                t_rate = now
            if steps == 0 and not self.paused:
                acc = min(acc, 2.0)
            await asyncio.sleep(0.005 if steps else 0.02)

    # -------------------------------------------------------------- chronicle (T12)
    def names(self, w: World) -> Dict[str, str]:
        return {a.id: a.name for a in list(w.agents.values()) + list(w.dead.values())}

    def day_facts(self, w: World, day: int) -> Dict[str, Any]:
        from .story import chronicle as C

        evs = self.store.events(w.id, since_tick=(day - 1) * TICKS_PER_DAY, until_tick=day * TICKS_PER_DAY,
                                min_importance=1, limit=20000, epoch=w.timeline())
        hist = {h.get("day"): h for h in w.history}
        stats = hist.get(day + 1) or hist.get(day) or w.stats()
        meta = {**views.world_meta(w), "brain": self.brain_summary().get(w.id, {}).get("label", "")}
        return C.daily_facts(meta, day, evs, stats, self.names(w))

    def narrator_brain(self, w: World):
        """Who tells the story: the shared narrator if one is set (fair in model vs model: the better *writer*
        doesn't make its world look better), else the world's own model, else nobody (template only)."""
        n = self.mind.brains.get(self.mind.narrator) if self.mind.narrator else None
        if n and n.healthy():
            return n
        b = self.mind.brains.get(self.mind.world_brain.get(w.id, INSTINCT))
        return b if b and b.healthy() else None

    def write_saga(self, w: World, week: int) -> Path:
        """A weekly story from that week's facts and top moments. Template now; narrated in the background."""
        from .story import chronicle as C
        from .story.moments import find_moments

        self._flush_events(w)
        first_day = (week - 1) * 7 + 1
        days = [self.day_facts(w, d) for d in range(first_day, first_day + 7)]
        evs = self.store.events(w.id, since_tick=(first_day - 1) * TICKS_PER_DAY, until_tick=(first_day + 6) * TICKS_PER_DAY,
                                min_importance=1, limit=50000, epoch=w.timeline())
        top = find_moments(evs, self.names(w))[:10]
        lines = [f"# {w.name} — Week {week}", "", f"Days {first_day}–{first_day + 6}.", "", "## The week's moments", ""]
        lines += [f"- Day {m.tick // TICKS_PER_DAY + 1}: {m.text} " + " ".join(f"(#{s})" for s in m.seqs[:2]) for m in top] or ["- A quiet week."]
        pop = [d["stats"].get("population") for d in days if d.get("stats")]
        lines += ["", "## Numbers", "", f"- Population: {pop[0] if pop else '?'} → {pop[-1] if pop else '?'}"]
        path = self.data_dir / "stories" / w.id / f"week-{week:02d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        base = "\n".join(lines) + "\n"
        path.write_text(base)
        brain = self.narrator_brain(w)
        if brain is not None:
            facts = {"world": w.id, "world_name": w.name, "day": first_day, "counts": {}, "stats": days[-1]["stats"] if days else {},
                     "agents": sorted({a for d in days for a in d["agents"]}),
                     "events": [e for d in days for e in d["events"]][:60],
                     "moments": [m.__dict__ for m in top]}
            known = set(self.names(w).values())

            run = self.run_id

            async def tell():
                text = await C.narrate(brain, facts, known)
                if text and self.run_id == run:
                    path.write_text(base + f"\n## The week, told\n\n{text}\n")

            try:
                asyncio.get_running_loop().create_task(tell())
            except RuntimeError:
                pass
        return path

    def write_chronicle(self, w: World, day: int) -> Path:
        from .story import chronicle as C

        self._flush_events(w)
        facts = self.day_facts(w, day)
        path = C.write_day(self.data_dir, facts)
        brain = self.narrator_brain(w)
        if brain is not None:
            known = set(self.names(w).values())

            run = self.run_id

            async def tell():
                text = await C.narrate(brain, facts, known)
                if text and self.run_id == run:
                    C.write_day(self.data_dir, facts, text)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(tell())
            except RuntimeError:
                pass
        return path

    def _maybe_record(self) -> None:
        """Hand a finished day to the recorder once every world has written that day's chronicle page (at tick
        day*240+10). Worlds can be ticks apart, so this waits for the slowest."""
        if not self.worlds:
            return
        done = min((w.tick - 10) // TICKS_PER_DAY for w in self.worlds.values())
        if self._recorded_day is None or done < self._recorded_day:  # (re)started, or a new match
            self._recorded_day = done
            return
        if done > self._recorded_day:
            self._recorded_day = done
            if done >= 1:
                try:
                    self.recorder.day_ended(done)
                except Exception as e:
                    log.warning("recording failed: %s", e)

    def _maybe_save(self, w: World) -> None:
        day = w.tick // TICKS_PER_DAY
        if w.tick % TICKS_PER_DAY == 10 and day >= 1:
            try:
                self.write_chronicle(w, day)  # yesterday's page
                if day % 7 == 0:
                    self.write_saga(w, day // 7)
            except Exception as e:
                log.warning("chronicle failed: %s", e)
        if w.tick % 10 == 0 and w.id == next(iter(self.worlds)):
            self.recorder.watch()
        evs = self._pending_events.get(w.id)
        if w.tick % 60 == 0 and evs is not None:
            try:
                self._flush_events(w)
            except Exception:
                log.exception("checkpoint failed for %s; simulation paused until an explicit save retry succeeds", w.id)
        if self._last_save_day.get(w.id) != day and w.tick % TICKS_PER_DAY == 5:
            self._last_save_day[w.id] = day
            try:
                self._checkpoint(w)
            except Exception as e:
                log.warning("save failed; simulation paused until an explicit save retry succeeds: %s", e)
            if w.id == next(iter(self.worlds)):  # once per day for the whole game
                try:
                    from . import diag

                    with open(self.data_dir / "diagnostics.log", "a") as f:
                        f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} · day {day} =====\n")
                        f.write(diag.text(diag.report(self)))
                except Exception as e:
                    log.warning("diagnostics log failed: %s", e)

    def _checkpoint_failed(self, w: World, exc: Exception) -> None:
        """A world in memory is not authoritative once its state could not be committed. Freeze every world so the
        gap cannot grow. Play may be retried explicitly with /api/save; an experiment is permanently invalid."""
        msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        self.save_errors[w.id] = msg
        self.paused = True
        if self.contract == "experiment" and not self.invalid_reason:
            self.invalid_reason = f"durability failure in World {w.id} at tick {w.tick}: {msg}"
            try:  # the SQLite write may have failed while the run folder is still writable
                self.write_manifest()
            except Exception as manifest_error:
                log.error("could not write invalid experiment manifest: %s", manifest_error)
        log.error("durability failure for %s at tick %s (last durable %s): %s",
                  w.id, w.tick, getattr(w, "_durable_tick", -1), msg)

    def _checkpoint(self, w: World) -> None:
        """Commit one authoritative boundary: snapshot + its events/outcomes + active pointer in one transaction.
        On success this exact tick is durable. On failure no in-memory tick after it is allowed to run."""
        stored = getattr(w, "_stored_seq", 0)
        new = [e for e in w.events if e.seq > stored]
        actions = getattr(w, "_pending_actions", [])
        try:
            self.store.save_world(w.to_dict(), events=new, outcomes=actions)
        except Exception as e:
            self._checkpoint_failed(w, e)
            raise
        if new:
            w._stored_seq = new[-1].seq
        actions.clear()
        w._durable_tick = w.tick
        self.save_errors.pop(w.id, None)

    def _flush_events(self, w: World) -> None:
        # A durable event must never get ahead of the state that produced it.
        self._checkpoint(w)

    def save_all(self) -> None:
        for w in self.worlds.values():
            self._checkpoint(w)

    # -------------------------------------------------------------- frames
    def control_state(self) -> Dict[str, Any]:
        return {"speed": self.speed, "paused": self.paused, "tps": round(self.tps, 1),
                "pace_to_brain": self.pace_to_brain, "waiting_on_brain": self.waiting_on_brain,
                "speeds": list(SPEEDS), "contract": self.contract, "mode": self.mode, "contact": self.contact,
                "sandbox_modified": self.store.get_meta("sandbox_modified") == "1",
                "durable_tick": {wid: getattr(w, "_durable_tick", -1) for wid, w in self.worlds.items()},
                "save_errors": dict(self.save_errors), "invalid_reason": self.invalid_reason}

    def brain_summary(self) -> Dict[str, Any]:
        out = {}
        for wid, w in self.worlds.items():
            bid = self.mind.world_brain.get(wid, INSTINCT)
            b = self.mind.brains.get(bid)
            thinking = sum(1 for a in w.agents.values() if a.thinking)
            out[wid] = {"id": bid, "label": b.label if b else "Instinct (no model)", "thinking": thinking,
                        "healthy": b.healthy() if b else True,
                        "tok_s": round(b.throughput(), 1) if b else 0,
                        "tok_s_request": round(b.stats.tok_per_s, 1) if b else 0,
                        "in_flight": b.stats.in_flight if b else 0, "queued": b.stats.queued if b else 0,
                        "slots": b.cfg.max_concurrency if b else 0,
                        "latency_ms": round(b.stats.latency_ms_avg) if b else 0}
        return out

    def frame(self, w: World) -> Dict[str, Any]:
        W = w.w
        res = [[i, w.res_kind[i], min(255, int(w.res_amt[i]))] for i in w.dirty_res]
        w.dirty_res.clear()
        structs = [views.structure_view(w.structures[s], w) for s in w.dirty_struct if s in w.structures]
        w.dirty_struct.clear()
        removed = list(w.removed_struct)
        w.removed_struct.clear()
        paths = [[i, 2 if i in w.roads else (1 if w.traffic[i] > 30 else 0)] for i in w.dirty_roads]
        w.dirty_roads.clear()
        evs = self._pending_events.get(w.id, [])
        sent = [e.to_dict() for e in evs[-40:]]
        self._pending_events[w.id] = []
        tabs = None
        if any(e.kind == "tablet" for e in evs):
            tabs = [{"id": t.id, "x": t.x, "y": t.y} for t in w.tablets.values() if not t.in_structure]
        return {
            "type": "frame", "world": w.id, "clock": w.clock(),
            "agents": [views.agent_brief(w, a) for a in w.agents.values()],
            "res": res, "structures": structs, "removed": removed, "paths": paths, "events": sent,
            "tablets": tabs, "stats": w.stats() if w.tick % 20 == 0 else None,
            "signs": self._signs_once(w), "ground": self._ground_once(w),
            "animals": views.animals_compact(w) if w.tick % 4 == 0 or not w.animals else None,
        }

    FAIR_EVERY, FAIR_DAYS, FAIR_READY = 30, 3, 5  # a trade fair for 3 days each month; boats get built 5 days ahead

    def fair(self) -> Tuple[int, int]:
        """A versus game's islands never meet, except at a trade fair: FAIR_DAYS every FAIR_EVERY days, from day
        FAIR_EVERY, when boats can cross. Play games only (an experiment keeps its worlds apart). Returns (days of the
        fair left, days until the next one); (0, 0) where there are no fairs."""
        if self.contact or self.mode != "versus" or self.contract == "experiment" or len(self.worlds) < 2:
            return 0, 0
        day = next(iter(self.worlds.values())).day
        k = day % self.FAIR_EVERY
        if day >= self.FAIR_EVERY and k < self.FAIR_DAYS:
            return self.FAIR_DAYS - k, 0
        return 0, self.FAIR_EVERY - k

    def step_worlds(self, n: int = 1) -> None:
        """Step every world, then land any boats that are due on the other island (T30)."""
        for _ in range(n):
            left, until = self.fair()
            for w in list(self.worlds.values()):
                w.contact = (self.contact or left > 0) and len(self.worlds) >= 2
                w.fair_days = left
                w.fair_soon = 0 < until <= self.FAIR_READY
                w.step(self.mind.hook)
                if w.tick % 24 == 0:
                    self.record_keyframe(w)
            for fk in list(self.forks.values()):  # what-ifs step alongside; they never meet the real islands
                fk["world"].contact = False
                fk["world"].step(self.mind.hook)
            if self.worlds and next(iter(self.worlds.values())).tick % 240 == 0:
                self.relations_daily()
                if self.contract != "experiment":  # an experiment measures the world as it is, dying out included
                    from .sim import storyteller
                    for w in list(self.worlds.values()) + [fk["world"] for fk in self.forks.values()]:
                        if w.day % w.WANDER_EVERY_DAYS == 0:
                            w.welcome_wanderer()
                        storyteller.daily(w)  # (a what-if gets the same days as the world it came from)
                self._fair_news()
            if len(self.worlds) >= 2 and (self.contact or left > 0 or any(w.outbox for w in self.worlds.values())):
                self._deliver_boats()  # (boats still at sea when a fair ends still land)

    # -------------------------------------------------------------- 🔀 what-if forks
    MAX_FORKS = 2

    def fork(self, wid: str, brain: str = "instinct", culture: Optional[str] = None) -> Dict[str, Any]:
        """A copy of world `wid` as it is now, stepping alongside it with another mind (instinct by default: no model
        is asked) or another culture, so the two can be compared as they drift apart. Play games only (an experiment
        is left alone), at most MAX_FORKS, kept in memory (a restart ends them). A fork never meets the real islands:
        no boats, no fairs, no relations, and nothing it does is recorded as the real world's."""
        if self.contract == "experiment":
            raise ValueError("what-if forks are for play games, not experiments")
        w = self.worlds.get(wid)
        if w is None:
            raise KeyError(wid)
        if len(self.forks) >= self.MAX_FORKS:
            raise ValueError(f"at most {self.MAX_FORKS} what-ifs at a time: end one first")
        if brain != "instinct":  # a model fork would share the real match's model servers, and record decisions
            raise ValueError("a what-if runs on instinct")
        if culture is not None and culture not in CULTURE_FLAGS:
            raise ValueError(f"culture must be one of {', '.join(CULTURE_FLAGS)}")
        self._fork_seq += 1
        f = World.from_dict(json.loads(json.dumps(w.to_dict(), default=str)))
        f.id = f"{wid}~{self._fork_seq}"
        f.name = f"{w.name} (what if #{self._fork_seq})"
        f.uuid, f.epoch = uuid.uuid4().hex, uuid.uuid4().hex
        if culture is not None:
            f.culture, f.flags = culture, dict(CULTURE_FLAGS[culture])
        f.contact, f.incident_sink, f.listeners = False, None, []
        f.is_fork = True  # (a trader in the copy doesn't sail off: there is nowhere to go)
        for a in f.agents.values():
            a.brain = brain
        self.forks[f.id] = {"world": f, "of": wid, "from_day": w.day + 1, "brain": brain, "culture": f.culture}
        return self.fork_view(f.id)

    def end_fork(self, fid: str) -> bool:
        return self.forks.pop(fid, None) is not None

    def fork_view(self, fid: str) -> Dict[str, Any]:
        """A what-if beside the world it came from: how far each has come, and what only one of them knows."""
        from .sim.items import DESIGNS

        fk = self.forks[fid]
        f, w = fk["world"], self.worlds.get(fk["of"])

        def side(x: World):
            known = {k for a in x.agents.values() for k in a.knows}
            return {"day": x.day + 1, "population": len(x.agents), "deaths": len(x.dead), "discoveries": len(x.first),
                    "era": ERAS[x.era()[0]][0], "known": len(known)}, known

        def names(keys):
            out = []
            for k in sorted(keys):
                kind, key = k.split(":", 1) if ":" in k else ("", k)
                out.append(DESIGNS[key].name if kind == "design" and key in DESIGNS else f.item_name(key))
            return out[:12]

        fs, fknow = side(f)
        ws, wknow = side(w) if w is not None else ({}, set())
        return {"id": fid, "of": fk["of"], "name": f.name, "from_day": fk["from_day"], "brain": fk["brain"],
                "culture": fk["culture"], "fork": fs, "original": ws,
                "only_fork_knows": names(fknow - wknow), "only_original_knows": names(wknow - fknow)}

    def _fair_news(self) -> None:
        left, until = self.fair()
        ws = list(self.worlds.values())
        if left == self.FAIR_DAYS:
            for w in ws:
                other = next(o for o in ws if o is not w)
                w.emit("fair", f"The trade fair is on: for {self.FAIR_DAYS} days boats can cross to {other.name}", 4)
        elif left == 0 and until == self.FAIR_EVERY - self.FAIR_DAYS and ws[0].day > self.FAIR_EVERY:
            for w in ws:
                w.emit("fair", "The trade fair is over: the sea closes again", 2)

    # -------------------------------------------------------------- rivals: relations between the islands (T34)
    STATES_IMPORTANCE = {"war": 5, "peace": 5, "tension": 3}
    DELTA = {"theft": 10, "fight": 15, "trade": -5, "gift": -8}

    def _incident_from(self, w: World, other_id: str, kind: str) -> None:
        other = self.worlds.get(other_id)
        if other is not None and other is not w:
            self.record_incident(w, other, kind)

    def _met(self, wa: World, wb: World) -> None:
        for x, y in ((wa, wb), (wb, wa)):
            rel = x.relation(y.id)
            if not rel["met"]:
                rel["met"] = True
                if rel["state"] == "unknown":
                    rel["state"] = "peace"
                x.emit("contact", f"{x.name} has met the people of {y.name}!", 5, other=y.id)

    def record_incident(self, wa: World, wb: World, kind: str) -> None:
        """Something happened between the islands. Both sides remember it the same way."""
        self._met(wa, wb)
        d = self.DELTA.get(kind, 0)
        for x, y in ((wa, wb), (wb, wa)):
            rel = x.relation(y.id)
            rel["hostility"] = max(0.0, min(100.0, rel["hostility"] + d))
            if kind in ("trade", "gift"):
                rel[kind + "s"] = rel.get(kind + "s", 0) + 1
            if kind in ("theft", "fight", "raid"):
                rel["raids"] = rel.get("raids", 0) + (1 if kind == "raid" else 0)
            self._update_state(x, y, rel)

    def _update_state(self, x: World, y: World, rel: Dict[str, Any]) -> None:
        h, old = rel["hostility"], rel["state"]
        if h >= 60 or (old == "war" and h >= 40):
            new = "war"
        elif h >= 25 or (old in ("tension", "war") and h >= 15):
            new = "tension"
        else:
            new = "peace" if rel["met"] else "unknown"
        if new != old:
            rel["state"] = new
            text = {"war": f"{x.name} and {y.name} are at war", "tension": f"Tension grows between {x.name} and {y.name}",
                    "peace": f"{x.name} and {y.name} are at peace"}.get(new)
            if text:
                x.emit(new, text, self.STATES_IMPORTANCE.get(new, 3), other=y.id, hostility=round(h))

    def relations_daily(self) -> None:
        ws = list(self.worlds.values())
        for x in ws:
            for oid, rel in x.relations.items():
                if rel["hostility"] > 0:
                    rel["hostility"] = max(0.0, rel["hostility"] - 1)
                    y = self.worlds.get(oid)
                    if y is not None:
                        self._update_state(x, y, rel)

    HOT_DAYS = 60

    def record_keyframe(self, w: World) -> None:
        """A compact picture for replays (T33): every chit's place and activity, and the buildings once a day."""
        data = {"t": w.tick, "a": [[a.id, a.x, a.y, a.activity] for a in w.agents.values()],
                "s": [views.structure_view(s, w) for s in w.structures.values()] if w.tick % 240 == 0 else None}
        try:
            self.store.save_keyframe(w.id, w.tick, data, w.uuid, w.epoch)
            if w.tick % 240 == 0 and w.tick > self.HOT_DAYS * 240:
                self.store.thin_keyframes(w.id, w.tick - self.HOT_DAYS * 240)
        except Exception as e:  # replays are a nicety: never let them stop the world
            log.warning("keyframe failed: %s", e)

    def _deliver_boats(self) -> None:
        ids = list(self.worlds)
        for w in list(self.worlds.values()):
            due = [o for o in w.outbox if o["arrive_tick"] <= w.tick]
            if not due:
                continue
            w.outbox = [o for o in w.outbox if o["arrive_tick"] > w.tick]
            dest = self.worlds[next(i for i in ids if i != w.id)]
            for o in due:
                a = dest.arrive(o["agent"], w.id, w.name, o.get("inventions"))
                self._met(w, dest)
                if a.stats.get("stole_abroad") and not a.origin:
                    # home again with stolen goods
                    dest.emit("raid", f"{a.name} came home from {w.name} with stolen goods", 4, a.id, a.x, a.y, other=w.id)
                    self.record_incident(dest, w, "raid")
                    a.stats["stole_abroad"] = 0
                if a.brain != INSTINCT and a.brain not in self.mind.brains:
                    if self.contract == "experiment":
                        a.plan_source = "brain_unavailable"  # never switch its policy: it waits, like any strict chit
                    else:
                        a.brain = self.mind.world_brain.get(dest.id, INSTINCT)
                if not self.store.get_meta("first_contact_tick"):
                    self.store.set_meta("first_contact_tick", str(dest.tick))
                    self.write_manifest()

    def _ground_once(self, w: World):
        sig = (len(w.ground), sum(n for p in w.ground.values() for k, n in p.items() if k != "_t"))
        last = getattr(self, "_ground_sig", {})
        self._ground_sig = last
        if last.get(w.id) == sig:
            return None
        last[w.id] = sig
        return views.ground_view(w)

    # -------------------------------------------------------------- god mode and save points (T28)
    GOD_ACTS = ("drop", "meteor", "bless", "smite", "feast", "plague", "storm", "drought", "snow")

    def god(self, wid: str, action: str, x: Optional[int], y: Optional[int], item: Optional[str] = None,
            qty: Optional[int] = None) -> str:
        """Reach into the world. Raises ValueError (bad request) or PermissionError (experiment run)."""
        from .sim.items import ITEMS

        w = self.worlds.get(wid)
        if w is None:
            raise KeyError(wid)
        if action not in self.GOD_ACTS:
            raise ValueError(f"unknown action; try one of {', '.join(self.GOD_ACTS)}")
        needs_xy = action not in ("plague", "storm", "drought", "snow")
        if needs_xy and (x is None or y is None or not w.inb(int(x), int(y))):
            raise ValueError("x,y must be a tile on the map")
        if action == "drop" and (not item or item not in ITEMS):
            raise ValueError(f"unknown item {item!r}")
        if action in ("storm", "drought", "snow") and not hasattr(w, "set_weather"):
            raise ValueError("this world has no weather")
        self.mark_sandbox(f"god:{action}")  # PermissionError in an experiment
        x, y = (int(x), int(y)) if needs_xy else (0, 0)
        n = max(1, min(99, int(qty or 1)))
        near = lambda r: [a for a in w.agents.values() if max(abs(a.x - x), abs(a.y - y)) <= r]  # noqa: E731
        near_s = lambda r: [s for s in w.structures.values() if s.dist(x, y) <= r]  # noqa: E731
        if action == "drop":
            w.put_ground(x, y, item, n)
            text = f"A {ITEMS[item].name} appeared out of nowhere at ({x},{y})!" if n == 1 else \
                f"{n} {ITEMS[item].name} appeared out of nowhere at ({x},{y})!"
        elif action == "meteor":
            w.put_ground(x, y, "meteorite", 1)
            for s in near_s(1):
                s.durability = max(0.0, s.durability - 50)
                w.dirty_struct.add(s.id)
            text = f"A meteor crashed down at ({x},{y})!"
        elif action == "bless":
            for a in near(8):
                a.hunger = a.warmth = a.health = 100.0
            text = f"A warm light blessed the chits near ({x},{y})"
        elif action == "smite":
            for a in near(1):
                a.health = max(5.0, a.health - 30) if a.health > 5 else a.health
            for s in near_s(1):
                s.durability = max(0.0, s.durability - 40)
                if s.design == "campfire" and s.functional:
                    s.fuel = max(s.fuel, 60.0)
                w.dirty_struct.add(s.id)
            text = f"Lightning struck at ({x},{y})!"
        elif action == "feast":
            w.put_ground(x, y, "bread", 30)
            text = f"A feast of bread appeared at ({x},{y})!"
        elif action == "plague":
            ags = sorted(w.agents.values(), key=lambda a: a.id)
            for a in w.rng_for("god").sample(ags, max(1, len(ags) // 5)) if ags else []:
                a.health = max(5.0, a.health - 30) if a.health > 5 else a.health
            text = f"A sickness spreads through {w.name}"
        else:
            w.set_weather(action, 1.0)
            text = {"storm": "The sky split open: a great storm", "drought": "The rains stopped: a drought",
                    "snow": "Snow fell out of season"}[action]
        w.emit("miracle", text, 5, None, x if needs_xy else None, y if needs_xy else None, action=action, item=item)
        return text

    def save_point(self, name: str) -> Dict[str, Any]:
        name = (name or "").strip()[:60] or time.strftime("save %H:%M")
        tick = max((w.tick for w in self.worlds.values()), default=0)
        sid = self.store.save_point(name, tick, {wid: w.to_dict() for wid, w in self.worlds.items()})
        return {"id": sid, "name": name, "tick": tick}

    def restore_point(self, sid: int) -> bool:
        sp = self.store.load_save_point(sid)
        if not sp:
            return False
        self.mark_sandbox(f"restored save point {sp['name']}")  # PermissionError in an experiment
        for wid, d in sp["worlds"].items():
            self._flush_events(self.worlds[wid]) if wid in self.worlds else None
            w = World.from_dict(d)
            self._adopt(w)
            w.fork_epoch(f"restored save point {sp['name']}")
            self._attach(w)
        self.gen += 1
        self.save_all()
        self._broadcast_snapshots()
        return True

    @staticmethod
    def _signs_once(w: World):
        if not w.signs_dirty:
            return None
        w.signs_dirty = False
        return list(w.signs.values())

    def _broadcast_snapshots(self) -> None:
        for q in self.clients.values():
            self.enqueue_hello(q, resync=True)

    # -------------------------------------------------------------- client stream (F4)
    QUEUE_MAX = 256

    def new_client_queue(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_MAX)
        q._chits_seq = 0  # type: ignore[attr-defined]
        return q

    def _push_raw(self, q: asyncio.Queue, body: str) -> bool:
        """Stamp gen+seq onto an already-serialised message. Returns False if the queue overflowed."""
        if q.full():
            self._resync(q)
            return False
        seq = getattr(q, "_chits_seq", 0) + 1
        q._chits_seq = seq  # type: ignore[attr-defined]
        q.put_nowait(f'{{"gen":{self.gen},"seq":{seq},' + body[1:])
        return True

    def push(self, q: asyncio.Queue, msg: Dict[str, Any]) -> None:
        self._push_raw(q, json.dumps(msg, separators=(",", ":"), default=str))

    def _resync(self, q: asyncio.Queue) -> None:
        """A client fell behind: throw its backlog away and start it again from a consistent picture."""
        while not q.empty():
            q.get_nowait()
        q._chits_seq = 0  # type: ignore[attr-defined]
        self.enqueue_hello(q, resync=True)

    def enqueue_hello(self, q: asyncio.Queue, resync: bool = False) -> None:
        if not hasattr(q, "_chits_seq"):
            q._chits_seq = 0  # type: ignore[attr-defined]
        if resync and q.qsize():
            while not q.empty():
                q.get_nowait()
            q._chits_seq = 0  # type: ignore[attr-defined]
        self.push(q, {**self.hello(), "resync": resync})
        for w in self.worlds.values():
            self.push(q, {"type": "snapshot", **views.snapshot(w)})

    def end_experiment(self) -> None:
        """Turn an experiment run into ordinary play: models and settings can change again, and instinct covers a slow
        model. One way only (an experiment starts from a new game). A save left in experiment mode refused every brain
        swap with no way back from the observer (issue #64)."""
        if self.contract != "experiment":
            return
        # what the experiment was stays on record (when it ended, and whether it had already lost its validity), but
        # an experiment's lost durability no longer holds the play game's resume (Codex review)
        self.store.set_meta("experiment_ended", json.dumps(
            {"ticks": {wid: w.tick for wid, w in self.worlds.items()}, "invalid_reason": self.invalid_reason or None}))
        self.invalid_reason = ""
        self.contract = "play"
        self.mind.strict = False
        self.pace_to_brain = _pace_default()
        self.store.set_meta("contract", "play")
        try:
            self.write_manifest()  # (the run's record on disk says so too, Codex review)
        except Exception as e:
            log.error("could not write the manifest of an ended experiment: %s", e)
        for w in self.worlds.values():
            w.emit("contract", "The experiment ended here: from now on this world is played, not measured", 4)
        self._broadcast_snapshots()

    def hello(self) -> Dict[str, Any]:
        return {"type": "hello", "worlds": [views.world_meta(w) for w in self.worlds.values()],
                "control": self.control_state(), "brains": self.brain_summary(), "theme": theme.active()}

    def status_msg(self) -> str:
        return json.dumps({"type": "status", "control": self.control_state(), "brains": self.brain_summary()},
                          separators=(",", ":"), default=str)

    async def _broadcast_loop(self) -> None:
        n = 0
        while True:
            await asyncio.sleep(0.125)
            n += 1
            self.recorder.tend()  # disk housekeeping on the wall clock: it must run while the world is paused too
            try:
                frames = [self.frame(w) for w in self.worlds.values()]
            except Exception as e:  # never let presentation kill the broadcaster
                log.warning("frame build failed: %s", e)
                continue
            if not self.clients:
                continue
            payloads = [json.dumps(f, separators=(",", ":"), default=str) for f in frames]
            if n % 8 == 0:
                payloads.append(self.status_msg())
            for ws, q in list(self.clients.items()):
                if q.qsize() > 40:
                    # a slow client: drop its backlog and resync with a fresh snapshot
                    self._resync(q)
                    continue
                for p in payloads:
                    if not self._push_raw(q, p):
                        break
