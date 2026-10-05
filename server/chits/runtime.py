"""Runs the twin worlds forever (browser or no browser), persists them, and fans out frames."""

from __future__ import annotations

import asyncio
import gzip
import json
import shutil
import logging
import os
import sqlite3
import threading
import time
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import theme, views
from .brain.mind import INSTINCT, Mind
from .recorder import Recorder
from .sim.agent import TICKS_PER_DAY
from .sim.world import CULTURE_FLAGS, ERAS, POP_CAP_MIN, World
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


def save_summary(worlds: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """What the Saves list says about a save, from its snapshots alone: the day, how many chits, and the era."""
    rows = {}
    for wid, d in worlds.items():
        i = max(0, min(len(ERAS) - 1, int(d.get("era_index") or 0)))
        rows[wid] = {"name": str(d.get("name") or wid)[:60], "day": int(d.get("tick") or 0) // TICKS_PER_DAY + 1,
                     "population": len(d.get("agents") or []), "era": ERAS[i][0], "era_index": i}
    furthest = max(rows.values(), key=lambda r: r["era_index"], default={"era": ""})
    return {"day": max((r["day"] for r in rows.values()), default=1),
            "population": sum(r["population"] for r in rows.values()), "era": furthest["era"], "worlds": rows}


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
        self.pack: Optional[Dict[str, Any]] = self._starting_pack()  # a content pack: every world of the match gets it
        self.mind.strict = self.contract == "experiment"
        self.mind.model_only = False  # (a diagnostic, switched on by hand in play: never kept over a restart)
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
        self.loop_error = ""  # a world's step raised: the game is paused and says why (it used to stop without a word)
        self._resetting = False  # while a new match is built (in a worker thread), the loop doesn't step
        self._recorded_day: Optional[int] = None  # the last day handed to the recorder
        self.recorder = Recorder(self)
        self._task: Optional[asyncio.Task] = None
        self._bcast: Optional[asyncio.Task] = None
        self.tps = 0.0
        self.waiting_on_brain = False
        self.skip: Optional[Dict[str, Any]] = None  # ⏩ skipping ahead (start_skip); None in normal play
        self.last_skip: Optional[Dict[str, Any]] = None  # how the last skip ended, for the observer
        self._skip_lock = threading.Lock()  # (Stop can come from a request thread while the loop ends it too)
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

    def _starting_pack(self) -> Optional[Dict[str, Any]]:
        """The content pack this game's worlds are made with (docs/modding.md). The game remembers its own choice
        (the store's "pack", written when a match is made); only a data directory that has never held a match takes
        the pack named by CHITS_PACK. A pack that doesn't pass validation stops the start, with the reason."""
        from .sim import packs

        kept = self.store.get_meta("pack")
        if kept is not None:
            return packs.validate(json.loads(kept), check_base=False) if kept else None
        path = os.environ.get("CHITS_PACK", "").strip()
        pack = None
        if path and self.store.get_meta("run_id") is None and not any(
                self.store.get_meta("active_snapshot:" + wid) for wid in ("A", "B")):
            pack = packs.load_file(path)
            log.info("content pack %s (%s) from CHITS_PACK", pack["id"], pack["sha256"][:12])
        if self.contract_of_store() == "experiment":
            pack = None
        self.store.set_meta("pack", json.dumps(pack) if pack else "")
        return pack

    def contract_of_store(self) -> str:
        return self.store.get_meta("contract") or "play"

    def _new_pack(self, pack: Optional[Dict[str, Any]], contract: str) -> Optional[Dict[str, Any]]:
        """The pack a new match will use. `pack` None keeps the current one, {} means none, anything else is a raw
        pack to validate. An experiment run takes no pack: nothing but the intended flags may differ from the base
        game, and a pack is not part of any sealed protocol yet."""
        from .sim import packs

        if pack is None:
            new = self.pack
        elif not pack:
            new = None
        else:
            if len(json.dumps(pack)) > 4 * packs.MAX_BYTES:
                raise packs.PackError(f"content pack refused: larger than {packs.MAX_BYTES // 1024} KiB")
            new = packs.validate(pack)
        if new and contract == "experiment":
            raise ValueError("a content pack is not allowed in an experiment run: start the experiment without a pack")
        return new

    def mend_foreign(self) -> List[str]:
        """A thing made in one world of this game and carried to another: where the other world has only a stand-in
        for it (a save from before such things were kept), take what it is from the world that invented it."""
        mended = []
        for w in self.worlds.values():
            for k in sorted(getattr(w, "_strange", ())):
                src = next((o.inventions[k] for o in self.worlds.values() if o is not w and k in o.inventions), None)
                if src is not None:
                    w.adopt_foreign(k, src)
                    mended.append(f"{w.id}:{k}")
        if mended:
            log.info("things from another world named again: %s", ", ".join(mended))
        return mended

    def load_or_create(self) -> None:
        self._load_or_create()
        self.mend_foreign()

    def _load_or_create(self) -> None:
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
        w = World(wid, theme.world_name(wid), seed, culture, size, n, label=label, pack=self.pack)
        # a new play game's limit on each world's people (0: the island's own). Never an experiment's: its worlds run
        # by the island's own rules, whatever this machine's settings say (Codex, #79)
        cap = _env_int("CHITS_POP_CAP", 0) if self.contract != "experiment" else 0
        if cap:
            w.cap = max(POP_CAP_MIN, min(w.island_cap(), cap))
        self._attach(w)
        return w

    def _attach(self, w: World) -> None:
        self.worlds[w.id] = w
        if self.mind.model_only:  # (a restored save, a rewind or a loaded file: its saved instinct steps go too)
            self.mind.start_model_only(w)
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
              contract: Optional[str] = None, contact: Optional[bool] = None,
              pack: Optional[Dict[str, Any]] = None) -> None:
        """Start a new match (see _reset). The loop stops stepping meanwhile: it used to keep stepping the old
        worlds, so the new A and B started ticks apart and old decisions landed in the new run's records.
        `pack`: a content pack for the new match (None keeps the current one, {} plays without)."""
        self._check_reset(mode, contract, contact)  # a rejected reset leaves the running match untouched
        new_pack = self._new_pack(pack, contract or self.contract)  # (so does a pack that doesn't validate)
        self._resetting = True
        try:
            self.mind.new_match()
            # a new game is a new match: the model-only diagnostic doesn't carry over into it unnoticed, as it doesn't
            # over a restart or into an experiment. Turned on again by hand, it sanitizes the new worlds as usual
            self.set_model_only(False)
            self.pack = new_pack
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
        self.loop_error = ""  # (the failed match is gone)
        self.paused = False
        self.skip = self.last_skip = None
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
            self.set_model_only(False)  # an experiment never runs the model-only diagnostic
        elif self.contract == "experiment":
            self.pace_to_brain = _pace_default()  # leaving an experiment: back to the normal default
        self.contract = contract
        self.run_id = uuid.uuid4().hex
        self.gen += 1
        self.recorder.new_run()
        for k, v in (("contract", contract), ("run_id", self.run_id), ("contact", "1" if new_contact else "0"),
                     ("sandbox_modified", "0"), ("sandbox_reasons", "[]"), ("skips", "[]"),
                     ("pack", json.dumps(self.pack) if self.pack else "")):
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
    def pop_cap_state(self) -> Dict[str, Any]:
        ws = list(self.worlds.values())
        return {"cap": next((w.cap for w in ws if w.cap), None), "min": POP_CAP_MIN,
                "island": min((w.island_cap() for w in ws), default=None)}

    def set_pop_cap(self, cap: Optional[int]) -> Dict[str, Any]:
        """Hold every world of this game at so many chits (None: the island's own limit). Nobody is removed: births
        pause while a world is at or over the limit, so a bigger world shrinks as its old die. The same limit for
        every world; play only (an experiment's worlds are never changed from outside); marked on the run."""
        if self.contract == "experiment":
            raise PermissionError("not allowed in an experiment run")
        st = self.pop_cap_state()
        if cap is not None and not (st["min"] <= cap <= (st["island"] or cap)):
            raise ValueError(f"the limit must be between {st['min']} and {st['island']} (this island's own limit)")
        if cap == st["island"]:
            cap = None
        for w in self.worlds.values():
            w.cap = cap
        self.mark_sandbox(f"each world held at {cap} chits" if cap else "the limit on each world's chits was lifted")
        return self.pop_cap_state()

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
                "pop_cap": getattr(first, "cap", None) if first else None,
                "worlds": worlds, "prompt_version": P.PROMPT_VERSION, "rng_scheme": RNG_SCHEME,
                "source_commit": source_commit(),
                "code_stretches": json.loads(self.store.get_meta("code_stretches") or "[]"),
                "pacing": self.pace_to_brain, "contact": self.contact,
                "pack": self.pack_info(),  # content that is not the base game's, by id and sha256 (None: none)
                "first_contact_tick": int(self.store.get_meta("first_contact_tick") or 0) or None,
                "valid": not bool(self.invalid_reason), "invalid_reason": self.invalid_reason or None,
                "experiment_ended": json.loads(self.store.get_meta("experiment_ended") or "null"),
                "durable_tick": {wid: getattr(w, "_durable_tick", -1) for wid, w in self.worlds.items()},
                "sandbox_modified": self.store.get_meta("sandbox_modified") == "1",
                "sandbox_reasons": json.loads(self.store.get_meta("sandbox_reasons") or "[]"),
                # ⏩ stretches a player skipped through at full speed: mostly instinct-driven (see start_skip)
                "skips": json.loads(self.store.get_meta("skips") or "[]")}

    def pack_info(self) -> Optional[Dict[str, Any]]:
        """The content pack of this match as the worlds themselves carry it (the same in every world, or it says so)."""
        from .sim import packs

        seen = {wid: packs.describe(getattr(w, "pack", None)) for wid, w in self.worlds.items()}
        infos = list(seen.values())
        if not infos:
            return packs.describe(self.pack)
        if any(i != infos[0] for i in infos):  # (never by design: every world is made with the match's one pack)
            return {"mismatch": {wid: (i or {}).get("sha256") for wid, i in seen.items()}}
        return infos[0]

    def set_model_only(self, on: bool) -> None:
        """The model-only diagnostic (brain/mind.py): no instinct menu, fallback or reflexes, in every world."""
        from . import diag

        was, self.mind.model_only = self.mind.model_only, bool(on)
        for w in list(self.worlds.values()) + [f["world"] for f in self.forks.values() if "world" in f]:
            if on and not was:
                self.mind.start_model_only(w)  # (nothing from before the switch may act after it)
            elif not on:
                diag.model_only_from(w, None)
            w.model_only = bool(on)

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
                   "model": f["models"][0], "max_concurrency": f["suggested"]["max_concurrency"], "enabled": True,
                   "detect": True}  # (its first Test settles JSON mode and the thinking switch: brain/checkup.py)
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
            skipping = self.skip is not None and not self.paused
            if skipping:
                rate = max(SPEEDS.values())  # ⏩ a skip is the top speed without waiting for the models or the clock
            self.mind.speed_scale = max(1.0, rate / 2)  # a plan's age limit stretches with the game's speed
            # "waiting" only when pacing really holds the world back: at 1x it already runs at the pace cap
            self.waiting_on_brain = not skipping and self.pace_to_brain and rate > 2 and self._brain_backlog()
            if self.waiting_on_brain:
                rate = min(rate, 2)  # let the models catch up instead of letting instinct take over
            acc = 60.0 if skipping else min(acc + dt * rate, 60)
            steps = 0
            t0 = time.perf_counter()
            while acc >= 1.0 and not self._resetting and not self.paused and time.perf_counter() - t0 < 0.05:
                try:
                    self.step_worlds()
                except Exception as e:
                    # a step that raises must not end this loop: the task died without a word and the game stood
                    # still, unpaused, for as long as nobody looked at the tick (live, 2026-10-04)
                    log.exception("a world's step failed; the game is paused")
                    self.loop_error = f"{type(e).__name__}: {e}"
                    if self.contract == "experiment" and not self.invalid_reason:
                        # one world may have stepped before another failed: the worlds are no longer in step, so
                        # the run can't be resumed as a valid comparison (Codex, #83)
                        self.invalid_reason = f"a world's step failed: {self.loop_error}"
                        try:
                            self.write_manifest()
                        except Exception as manifest_error:
                            log.error("could not write invalid experiment manifest: %s", manifest_error)
                    if self.skip is not None:
                        self.stop_skip()
                    self.paused = True
                    acc = 0.0
                    break
                for w in self.worlds.values():
                    self._maybe_save(w)
                self._maybe_record()
                acc -= 1.0
                steps += 1
                if skipping:
                    self._skip_check()  # (does nothing if a storage error has ended the skip during this step)
                    if self.skip is None:  # it ended (or a failed checkpoint ended it): back to the speed it had
                        acc = 0.0
                        break
            count += steps
            if now - t_rate > 1.0:
                self.tps = count / (now - t_rate)
                count = 0
                t_rate = now
            if steps == 0 and not self.paused:
                acc = min(acc, 2.0)
            await asyncio.sleep(0 if skipping and self.skip is not None else 0.005 if steps else 0.02)

    # -------------------------------------------------------------- ⏩ skip ahead
    SKIP_UNTIL = ("discovery", "moment", "days")
    SKIP_MAX_DAYS = 30  # the most days one skip asks for, and where a skip that finds nothing gives up

    def start_skip(self, until: str, days: Optional[int] = None) -> Dict[str, Any]:
        """Run the worlds forward as fast as this machine allows until the next discovery, the next big moment
        (an event of importance 5) or `days` days have passed, then go back to the speed (or the pause) it had.
        Nothing else changes: the loop steps the same worlds through the same Mind, so a chit whose model has not
        answered is covered by the instinct filler exactly as at top speed with "wait for models" off. Skipped time
        is therefore mostly instinct-driven, which is why an experiment refuses it (PermissionError). Raises
        ValueError for a bad request and RuntimeError when the game can't run now."""
        if self.contract == "experiment":
            raise PermissionError("not allowed in an experiment run")
        if until not in self.SKIP_UNTIL:
            raise ValueError(f"until must be one of {', '.join(self.SKIP_UNTIL)}")
        if until == "days" and (type(days) is not int or not 1 <= days <= self.SKIP_MAX_DAYS):
            raise ValueError(f"days must be 1..{self.SKIP_MAX_DAYS}")
        if self.save_errors or self.invalid_reason:
            raise RuntimeError("cannot skip ahead while a storage error is unresolved")
        if self.skip is not None:
            raise RuntimeError("already skipping ahead: stop it first")
        if not self.worlds or self._resetting:
            raise RuntimeError("no world is running")
        n = days if until == "days" else self.SKIP_MAX_DAYS
        tick = max(w.tick for w in self.worlds.values())
        self.skip = {"until": until, "days": n, "from_tick": tick, "to_tick": tick + n * TICKS_PER_DAY,
                     "t0": time.perf_counter(), "was_paused": self.paused,
                     "firsts": {wid: set(w.first) for wid, w in self.worlds.items()},
                     "seq0": {wid: w.seq for wid, w in self.worlds.items()},
                     "seq": {wid: w.seq for wid, w in self.worlds.items()}}
        self.paused = False
        return self.skip_state()

    def stop_skip(self) -> None:
        if self.skip is not None:
            self._end_skip("stopped")

    def skip_state(self) -> Optional[Dict[str, Any]]:
        sk = self.skip
        if sk is None:
            return None
        tick = max((w.tick for w in self.worlds.values()), default=sk["from_tick"])
        return {"until": sk["until"], "days": sk["days"], "from_day": sk["from_tick"] // TICKS_PER_DAY + 1,
                "day": tick // TICKS_PER_DAY + 1, "seconds": int(time.perf_counter() - sk["t0"])}

    def _skip_check(self) -> None:
        """After a step of a skip: has what the player asked for happened? (Never called in normal play.)"""
        sk = self.skip
        if sk is None:
            return
        found = ""
        for wid, w in self.worlds.items():
            since = sk["seq"].get(wid, w.seq)
            if sk["until"] == "discovery" and len(w.first) > len(sk["firsts"].get(wid, ())):
                key = next(k for k in w.first if k not in sk["firsts"].get(wid, ()))
                found = found or self._first_text(w, key, sk["seq0"].get(wid, 0))
            elif sk["until"] == "moment" and w.seq > since:
                for e in reversed(w.events):
                    if e.seq <= since:
                        break
                    if e.importance >= 5:
                        found = e.text
            sk["seq"][wid] = w.seq
        if found:
            self._end_skip("found", found)
        elif max(w.tick for w in self.worlds.values()) >= sk["to_tick"]:
            self._end_skip("days" if sk["until"] == "days" else "limit")

    @staticmethod
    def _first_text(w: World, key: str, since: int) -> str:
        """The event that tells a discovery made during a skip, or a plain line when it has none."""
        for e in reversed(w.events):
            if e.seq <= since:
                break
            if key in (e.data.get("knowledge"), e.data.get("key")):
                return e.text
        return f"{w.first[key].get('name') or 'Someone'} found {key.split(':', 1)[-1].replace('_', ' ')}"

    def _end_skip(self, reason: str, text: str = "") -> None:
        """Leave the skip. The game goes back to the pause it had; after a storage error it stays frozen."""
        with self._skip_lock:
            sk, self.skip = self.skip, None
        if sk is None:
            return
        tick = max((w.tick for w in self.worlds.values()), default=sk["from_tick"])
        # (a failed checkpoint has already frozen the game: that stays)
        self.paused = sk["was_paused"] or (reason == "storage" and self.paused)
        self.last_skip = {"until": sk["until"], "reason": reason, "text": text, "ended": time.time(),
                          "from_day": sk["from_tick"] // TICKS_PER_DAY + 1, "day": tick // TICKS_PER_DAY + 1,
                          "ticks": tick - sk["from_tick"], "seconds": round(time.perf_counter() - sk["t0"], 1)}
        try:  # the run's record keeps which stretches were skipped (the store may be the thing that failed)
            skips = json.loads(self.store.get_meta("skips") or "[]")
            skips.append({"from_tick": sk["from_tick"], "to_tick": tick, "until": sk["until"], "reason": reason})
            self.store.set_meta("skips", json.dumps(skips[-200:]))
        except Exception as e:
            log.warning("could not record the skip: %s", e)

    def _skip_storage_error(self, e: Exception) -> None:
        """Something could not be written (a keyframe, a chronicle page, the diagnostics log). Normal play carries on
        past these; a skip stops at once, so hours of game are never run on storage that is failing."""
        if self.skip is not None and isinstance(e, (OSError, sqlite3.Error)):
            self._end_skip("storage", f"{type(e).__name__}: {str(e)[:300]}")

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
                self._skip_storage_error(e)
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
                    self._skip_storage_error(e)

    def _checkpoint_failed(self, w: World, exc: Exception) -> None:
        """A world in memory is not authoritative once its state could not be committed. Freeze every world so the
        gap cannot grow. Play may be retried explicitly with /api/save; an experiment is permanently invalid."""
        msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        self.save_errors[w.id] = msg
        self.paused = True
        if self.skip is not None:
            self._end_skip("storage", msg)  # a skip stops at once: nothing more may run on an unsaved world
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
                "save_errors": dict(self.save_errors), "invalid_reason": self.invalid_reason,
                "skip": self.skip_state(), "last_skip": self.last_skip, "pop_cap": self.pop_cap_state(),
                "loop_error": self.loop_error}

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
        if self.mind.model_only:  # (a copy runs under the same switch as the world it copies)
            self.mind.start_model_only(f)
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
            self._skip_storage_error(e)

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
        worlds = {wid: w.to_dict() for wid, w in self.worlds.items()}
        sid = self.store.save_point(name, tick, worlds, save_summary(worlds))
        return {"id": sid, "name": name, "tick": tick}

    def restore_point(self, sid: int) -> bool:
        """Every world goes back to a save point, as a unit: all of them, or (on any failure) none of them. The run is
        marked as a sandbox and each world starts a new timeline. PermissionError in an experiment."""
        sp = self.store.load_save_point(sid)
        if not sp:
            return False
        if self.contract == "experiment":
            raise PermissionError("not allowed in an experiment run")
        reason = f"restored save point {sp['name']}"
        # 1. Build every replacement first. A save that does not load has changed nothing.
        staged = [World.from_dict(d) for d in sp["worlds"].values()]
        # 2. Make every world that is about to be replaced durable. A failed checkpoint pauses the game (DURABILITY.md)
        #    and raises here, with every current world still in place.
        for w in staged:
            if w.id in self.worlds:
                self._flush_events(self.worlds[w.id])
        # 3. One transaction: each restored world's carried events (under the timeline they happened in), its first
        #    checkpoint in its new timeline and its active pointer, and the sandbox mark. If it fails, storage still
        #    points at the checkpoints of step 2 and the worlds in memory are those same worlds.
        entries = []
        for w in staged:
            identity, carried, mark = (w.id, w.uuid, w.epoch), list(w.events), w.seq
            w.fork_epoch(reason)
            entries.append({"identity": identity, "carried": carried, "world": w.to_dict(),
                            "events": [e for e in w.events if e.seq > mark]})
        reasons = json.loads(self.store.get_meta("sandbox_reasons") or "[]") + [reason]
        self.store.save_worlds(entries, {"sandbox_modified": "1", "sandbox_reasons": json.dumps(reasons[-50:])})
        # 4. Committed: only now do the restored worlds replace the running ones.
        self.stop_skip()  # (a skip was looking for news in the worlds that have just been replaced)
        for w in staged:
            w._stored_seq, w._durable_tick = w.seq, w.tick
            self._attach(w)
            self.save_errors.pop(w.id, None)
        self.gen += 1
        try:
            self.write_manifest()
        except Exception as e:  # (the mark is already committed in the store; the file copy follows at the next write)
            log.error("could not write the manifest after a restore: %s", e)
        self._broadcast_snapshots()
        return True

    # -------------------------------------------------------------- 💾 saves in the main UI, and save files
    SAVE_FORMAT, SAVE_VERSION = "little-chits-save", 1
    SAVE_FILE_MAX = 64 * 1024 * 1024  # an uploaded save file, as sent
    SAVE_JSON_MAX = 256 * 1024 * 1024  # and what it may unpack to

    def _play_only(self, what: str) -> None:
        if self.contract == "experiment":
            raise PermissionError(f"{what} not allowed in an experiment run")

    def saves(self) -> List[Dict[str, Any]]:
        """Every save point, newest first, with its day, population and era."""
        return self.store.save_summaries(save_summary)

    def load_save(self, sid: int) -> bool:
        """Load a save from the main UI. This is god mode's save-point restore and nothing else (restore_point: the
        run is marked as a sandbox and every world starts a new timeline), after checking the save fits this game.
        Raises PermissionError (experiment) or ValueError (the save holds other worlds than this game has)."""
        self._play_only("loading a save is")
        row = next((s for s in self.saves() if s["id"] == sid), None)
        if row is None:
            return False
        want = set(row.get("worlds") or self.worlds)
        if want != set(self.worlds):
            n, m = len(want), len(self.worlds)
            raise ValueError(f"This save holds {n} world{'s' if n != 1 else ''} and this game has {m}. "
                             f"Start a new game with {n} world{'s' if n != 1 else ''}, then load it.")
        ok = self.restore_point(sid)
        if ok and row.get("imported"):  # (the world now running was made somewhere else: say so on the run's record)
            self.mark_sandbox(f"save point {row['name']} came from an imported file")
        return ok

    def export_save(self, sid: int) -> Optional[Tuple[str, bytes]]:
        """One save as one file: gzipped JSON with a format name and version. Returns (file name, bytes)."""
        self._play_only("exporting a save is")
        sp = self.store.load_save_point(sid)
        if not sp:
            return None
        doc = {"format": self.SAVE_FORMAT, "version": self.SAVE_VERSION, "name": sp["name"], "tick": sp["tick"],
               "exported": time.strftime("%Y-%m-%dT%H:%M:%S"), "build": source_commit(), "worlds": sp["worlds"]}
        slug = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in sp["name"]).strip("-")[:40] or "save"
        return f"little-chits-{slug}.lcsave", gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), 6)

    SAVE_TRIAL_TICKS = 24  # an imported world must run this long on a throwaway copy before it is kept

    @staticmethod
    def _snapshot_problem(w: World) -> str:
        """What is wrong with the shape of a world read from a save file, or "". World.from_dict copies what the file
        says: a per-tile list of the wrong length, or a chit or building off the map, loads and then crashes the first
        step that looks at that tile."""
        n = w.w * w.h

        def number(v) -> bool:
            return type(v) in (int, float) and v == v and abs(v) != float("inf")

        def tile(x, y) -> bool:
            return type(x) is int and type(y) is int and w.inb(x, y)

        for name, arr in (("resource amounts", w.res_amt), ("paths", w.traffic)):
            if len(arr) != n or not all(map(number, arr)):
                return f"its {name} do not cover the {w.w} by {w.h} map"
        if not all(type(i) is int and 0 <= i < n for i in [*w.roads, *w.tunnels]):
            return "a road or tunnel is off the map"
        if not all(tile(a.x, a.y) for a in [*w.agents.values(), *w.dead.values()]):
            return "a chit is off the map"
        if not all(type(v) is int and v > 0 for s in w.structures.values() for v in (s.w, s.h)) \
                or not all(tile(s.x, s.y) and tile(s.x + s.w - 1, s.y + s.h - 1) for s in w.structures.values()):
            return "a building is off the map"
        if not all(tile(t.x, t.y) for t in w.tablets.values()):
            return "a tablet is off the map"
        for key in w.ground:
            x, _, y = str(key).partition(",")
            if not (x.isdigit() and y.isdigit() and w.inb(int(x), int(y))):
                return "a pile on the ground is off the map"
        if not all(isinstance(a, dict) and tile(a.get("x"), a.get("y")) for a in w.animals.values()):
            return "an animal is off the map"
        return ""

    @staticmethod
    def _match_problem(worlds: Dict[str, Dict[str, Any]]) -> str:
        """Why the snapshots of a save file can't be one game, or "". Every world of a match is built from the same
        seed and differs only in its culture (MODES); a save point takes them all at one moment. Two unrelated
        islands in one file would be loaded and then played, scored and compared as twins."""
        ids = sorted(worlds)
        cultures = tuple(worlds[wid].get("culture") for wid in ids)
        if cultures not in {tuple(m["culture"][wid] for wid in m["worlds"]) for m in MODES.values()}:
            return "no game mode has worlds with these cultures (" + ", ".join(str(c)[:20] for c in cultures) + ")"
        for key, what, default in (("seed", "seeds", None), ("size", "sizes", None),
                                   ("terrain_version", "terrain versions", 1), ("rng_scheme", "random-number schemes", 1),
                                   ("schema", "snapshot versions", 1)):
            if len({json.dumps(worlds[wid].get(key, default)) for wid in ids}) > 1:
                return f"they have different {what}"
        ticks = [worlds[wid]["tick"] for wid in ids]
        if max(ticks) - min(ticks) > TICKS_PER_DAY:  # (twins step together; a crash can leave them a checkpoint apart)
            return "they are more than a day apart"
        return ""

    def import_save(self, raw: bytes) -> Dict[str, Any]:
        """A save file becomes a new save point (nothing is loaded, and nothing is written but that row). The file is
        untrusted: its size, format name and version are checked, it is only ever parsed as JSON, and every world in
        it must load in this build before it is kept. Raises ValueError with a plain reason."""
        self._play_only("importing a save is")
        if len(raw) > self.SAVE_FILE_MAX:
            raise ValueError(f"This file is too big (the limit is {self.SAVE_FILE_MAX // 2 ** 20} MB).")
        if raw[:2] == b"\x1f\x8b":
            try:
                unpack = zlib.decompressobj(16 + zlib.MAX_WBITS)
                text = unpack.decompress(raw, self.SAVE_JSON_MAX + 1)
            except zlib.error:
                raise ValueError("This file is damaged: it could not be unpacked.")
            if len(text) > self.SAVE_JSON_MAX or unpack.unconsumed_tail:
                raise ValueError("This file unpacks to more than a save can hold.")
        else:
            text = raw
        try:
            doc = json.loads(text)
        except (ValueError, RecursionError):
            raise ValueError("This file is not a Little Chits save.")
        if not isinstance(doc, dict) or doc.get("format") != self.SAVE_FORMAT:
            raise ValueError("This file is not a Little Chits save.")
        version = doc.get("version")
        if type(version) is not int or version != self.SAVE_VERSION:
            raise ValueError(f"This save file is version {str(version)[:20]}; this build reads version {self.SAVE_VERSION}.")
        worlds = doc.get("worlds")
        if not isinstance(worlds, dict) or sorted(worlds) not in (["A"], ["A", "B"]):
            raise ValueError("This save file holds no worlds this game knows.")
        for wid, d in worlds.items():
            size, tick = (d.get("size"), d.get("tick")) if isinstance(d, dict) else (None, None)
            if type(size) is not int or not MIN_SIZE <= size <= MAX_SIZE or type(tick) is not int or tick < 0 \
                    or d.get("id") != wid or not isinstance(d.get("agents"), list) or len(d["agents"]) > 5000:
                raise ValueError(f"World {wid} in this save file is not a world this build can read.")
            try:  # (a copy: the trial below steps it, and what is kept must be the file's own snapshot)
                trial = World.from_dict(json.loads(json.dumps(d)))  # refuses a snapshot schema newer than this build
            except Exception as e:
                raise ValueError(f"World {wid} in this save file can't be read by this build "
                                 f"({type(e).__name__}: {str(e)[:120]}).")
            wrong = self._snapshot_problem(trial)
            if wrong:
                raise ValueError(f"World {wid} in this save file is damaged: {wrong}.")
            try:  # it loads and it is whole: can it run? (on instinct, no model is asked; the copy is thrown away)
                hook = Mind(None).hook
                for _ in range(self.SAVE_TRIAL_TICKS):
                    trial.step(hook)
            except Exception as e:
                raise ValueError(f"World {wid} in this save file loads but can't run in this build "
                                 f"({type(e).__name__}: {str(e)[:120]}).")
        wrong = self._match_problem(worlds)
        if wrong:
            raise ValueError(f"The worlds in this save file are not one game: {wrong}.")
        name = "".join(ch for ch in str(doc.get("name") or "") if ch.isprintable()).strip()[:60] or "imported save"
        tick = max(d["tick"] for d in worlds.values())
        summary = {**save_summary(worlds), "imported": True}
        sid = self.store.save_point(name, tick, worlds, summary)
        return {"id": sid, "name": name, "tick": tick, **summary}

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
                "control": self.control_state(), "brains": self.brain_summary(), "theme": theme.active(),
                "pack": self.pack_info()}

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
