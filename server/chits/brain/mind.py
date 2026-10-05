"""The Mind: routes each chit to a brain and keeps the world from ever waiting on one.

- Models get asked for a new plan *before* the current one runs out (prefetch).
- While a model is thinking and the chit has nothing to do, instinct supplies a
  single filler step, so chits never freeze in place. This is labelled honestly.
- Failed or garbled replies fall back to instinct for that plan and are counted.
- Once a day each model-driven chit reflects on its memories and keeps lessons.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import random
import time
import uuid
import zlib
from collections import Counter, deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import diag
from ..sim.agent import TICKS_PER_DAY, Agent
from . import prompt as P
from .instinct import Instinct, tools_first
from .llm import BrainConfig, LLMBrain
from .pioneers import plan as pioneer_plan
from .parse import ParseError, parse_lesson_items, parse_lessons, parse_plan, parse_reflection

log = logging.getLogger("chits.mind")

INSTINCT = "instinct"
# bounded action repair for choosing brains (issue #112): a menu choice that failed puts the simulator's reason in the
# next choice scene (prompt.repair_line) and in a cascade's full plan. Off: until now a choosing model never heard why
CHOICE_REPAIR = False

PRESETS = [
    {"id": "llamacpp", "label": "llama.cpp server", "base_url": "http://127.0.0.1:8080/v1", "max_concurrency": 4, "enabled": False},
    {"id": "ollama", "label": "Ollama", "base_url": "http://127.0.0.1:11434/v1", "max_concurrency": 2, "enabled": False},
    {"id": "lmstudio", "label": "LM Studio", "base_url": "http://127.0.0.1:1234/v1", "max_concurrency": 2, "enabled": False},
]


class StaleMatch(Exception):
    """A queued request from a match that has since been replaced."""


REFLECT_EVERY_DAYS = 7  # a chit sits down to draw lessons (and maybe a belief or a decree) once a week
STALE_TICKS = 120  # a model plan older than this (in world ticks) is out of date
QUEUE_PER_SLOT = 3  # plan requests waiting per parallel slot before more are shed to instinct
TICKS_PER_SEC = 2.0  # the world's pace at 1x (speed_scale stretches it)
SLOW_TICKS = 12  # a model whose reply takes this many world ticks or more is asked two steps before a plan runs out
ROUTINE = frozenset({"eat", "sleep", "rest", "shelter", "store", "drop", "refuel"})  # (and "go", with one of these)


def _lesson_words(text: str) -> set:
    return {w for w in "".join(c.lower() if c.isalpha() else " " for c in text).split() if len(w) >= 4}


def reflection_due(a: Agent, day: int, hour: int) -> bool:
    """Once a week. Daily reflections flooded the chronicle with "reflected:" notes and took about half of a slow
    GPU's time. Each chit has its own day of the week and hour (all at once doubled plan latency); a busy brain can
    put it off but not skip it (the caller lets it go ahead after 20:00), and a missed one happens later that week."""
    crc = zlib.crc32(a.id.encode())
    own_hour, own_day = 7 + crc % 12, (crc >> 8) % REFLECT_EVERY_DAYS
    if day < own_day:
        return False
    if (day - own_day) % REFLECT_EVERY_DAYS == 0 and hour <= own_hour:
        return False  # on its own weekday, not before its own hour (in every week, not only the first)
    if a.last_reflect_day < 0:
        return True
    return (day - own_day) // REFLECT_EVERY_DAYS != (a.last_reflect_day - own_day) // REFLECT_EVERY_DAYS


def apply_reflection(world, a: Agent, text: str) -> Dict[str, Any]:
    """Apply a weekly reflection: keep new lessons (at most 6), remembering which real memories each one cites."""
    items = parse_lesson_items(text)
    parsed = parse_reflection(text)
    if parsed.get("truncated"):
        # the model ran out of room mid-reply: keep the finished lessons, but don't turn a half-sentence into
        # a law, an ambition or a faith (8 of 23 decrees in one day's games were cut mid-sentence)
        if items and json.dumps(items[-1][0]) not in text:  # the last lesson itself was cut mid-way
            items = items[:-1]
        parsed["ambition"], parsed["decree"], parsed["belief"], parsed["project"] = "", "", None, ""
    valid = {m.id for m in a.memories}
    lessons = []
    for t, cites in items:
        lessons.append(t)
        mine = _lesson_words(t)
        twin = next((old for old in a.lessons if len(mine & _lesson_words(old)) >= 0.5 * max(1, min(len(mine), len(_lesson_words(old))))), None)
        if twin is not None and twin != t:  # the same lesson again in other words: keep the newer wording once
            a.lessons.remove(twin)
            a.lesson_sources.pop(twin, None)
        if t not in a.lessons:
            a.lessons.append(t)
        a.lesson_sources[t] = [c for c in cites if c in valid]
    del a.lessons[:-6]
    for k in list(a.lesson_sources):
        if k not in a.lessons:
            del a.lesson_sources[k]
    if lessons:
        world.emit("reflection", f'{a.name} reflected: "{lessons[0]}"', 1, a.id, a.x, a.y, lessons=lessons)
    amb = parsed["ambition"]
    if amb and amb.lower() != a.ambition.lower():
        a.ambition, a.ambition_since = amb, world.tick
        world.emit("ambition", f'{a.name} set their heart on: "{amb}"', 3, a.id, a.x, a.y, ambition=amb)
    if parsed.get("decree") and hasattr(world, "decree"):
        world.decree(a, parsed["decree"])
    if parsed.get("project") and hasattr(world, "civic"):
        from ..sim.projects import name_project

        name_project(world, a, parsed["project"])  # the chief sets the village's project (checked by the world)
    bel = parsed.get("belief")
    if bel and not a.belief:  # meaning comes from minds: only a reflection can found a belief (T21)
        norm = lambda s: " ".join("".join(c.lower() if c.isalnum() else " " for c in s).split()).removeprefix("the ")
        said = {norm(bel["name"]), norm(bel["tenet"])} - {""}
        join = next((bid for bid, b in getattr(world, "beliefs", {}).items()
                     if norm(b["name"]) in said or norm(b["tenet"]) in said), None)
        if join:  # naming a belief that already exists means joining it
            world.convert(a, join, "they chose it")
        elif bel["tenet"]:
            world.found_belief(a, bel["name"] or f"The Way of {a.name}", bel["tenet"])
    parsed["lessons"] = lessons
    return parsed


CIVIC_STYLES = ("chief-project", "vote", "trade-offer")  # one-letter civic choices: decisions, but not plans

class Mind:
    def __init__(self, config_path: Optional[Path] = None):
        self.instinct = Instinct()
        self.brains: Dict[str, LLMBrain] = {}
        self.config_path = config_path
        self.world_brain: Dict[str, str] = {}  # world id -> default brain id
        self.patience_ticks = 12  # how long a chit waits idle for a model before instinct fills in
        self.log: List[Dict[str, Any]] = []  # recent model exchanges for the UI
        self._tasks: set = set()
        self.plans_out: Counter = Counter()  # brain id -> plan requests spawned and not finished (queued or running)
        self.strict = False  # experiment contract: a model's chits never get instinct plans
        # model-only (a diagnostic, never a comparison): nothing from instinct covers for the model. No instinct plans,
        # as strict; the full prompt whatever a brain's style (no menu of instinct's options); its plans as written
        # (no tools_first); and the worlds it drives run without the body's reflexes (sim/actions.py REFLEXES)
        self.model_only = False
        self.repair: Optional[bool] = None  # bounded action repair: None = on in play, off in an experiment
        self.narrator = ""  # one storyteller brain for every world (T32); "" = each world's own model
        self.decisions: deque = deque(maxlen=5000)  # one record per model request (F2)
        self.adopted: Counter = Counter()  # world id -> plan decisions adopted this match (the scorecard's denominator)
        self.match = 0  # bumped by new_match(): replies to an older match are dropped
        self.on_decision: Optional[Callable[[Dict[str, Any]], None]] = None
        self.load()

    # ------------------------------------------------------------ config
    def load(self) -> None:
        if not self.config_path or not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text())
        except Exception as e:
            log.warning("could not read %s: %s", self.config_path, e)
            return
        for b in data.get("brains", []):
            cfg = BrainConfig(**{k: v for k, v in b.items() if k in BrainConfig.__dataclass_fields__})
            self.brains[cfg.id] = LLMBrain(cfg)
        self.world_brain.update(data.get("assign", {}))
        self.narrator = data.get("narrator", "") or ""

    def merge_preset(self, path: Path) -> None:
        """Merge a brains.json-style preset (brains + assignments) over the current config, and save it."""
        data = json.loads(Path(path).read_text())
        for b in data.get("brains", []):
            self.upsert(b)
        self.world_brain.update(data.get("assign", {}))
        self.save()

    def save(self) -> None:
        if not self.config_path:
            return
        data = {
            "brains": [{**b.cfg.__dict__} for b in self.brains.values()],
            "assign": self.world_brain,
            "narrator": self.narrator,
        }
        self.config_path.write_text(json.dumps(data, indent=2))

    def upsert(self, cfg: Dict[str, Any]) -> LLMBrain:
        bid = str(cfg.get("id") or "").strip() or f"brain{len(self.brains) + 1}"
        cur = self.brains.get(bid)
        base = dict(cur.cfg.__dict__) if cur else {}
        if cur and cfg.get("api_key") == "•••":
            cfg = {k: v for k, v in cfg.items() if k != "api_key"}
        base.update({k: v for k, v in cfg.items() if k in BrainConfig.__dataclass_fields__})
        base["id"] = bid
        b = LLMBrain(BrainConfig(**base))
        if cur:
            b.stats = cur.stats
            b.stats.resolved_model = ""
        self.brains[bid] = b
        self.save()
        return b

    def remove(self, bid: str) -> None:
        self.brains.pop(bid, None)
        for w, b in list(self.world_brain.items()):
            if b == bid:
                self.world_brain[w] = INSTINCT
        self.save()

    def assign(self, world, brain_id: str, agent_ids: Optional[List[str]] = None) -> None:
        if brain_id != INSTINCT and brain_id not in self.brains:
            raise KeyError(brain_id)
        targets = [world.agents[a] for a in agent_ids if a in world.agents] if agent_ids else list(world.agents.values())
        if not agent_ids:
            self.world_brain[world.id] = brain_id
        for a in targets:
            a.brain = brain_id
            a.pending_plan = None
            if self.model_only:
                self._became_model_driven(world, a)
        self.save()

    def brain_for(self, a: Agent) -> Optional[LLMBrain]:
        if a.brain == INSTINCT:
            return None
        return self.brains.get(a.brain)

    # ------------------------------------------------------------ per-tick hook
    def hook(self, world, a: Agent) -> None:
        world.__dict__["_mind_strict"] = self.strict  # (the prompt's loop note is for play only)
        if self.model_only or world.__dict__.get("model_only"):
            world.__dict__["model_only"] = self.model_only  # (the body's reflexes follow the mind's switch)
        if self.model_only:
            self._became_model_driven(world, a)
        brain = self.brain_for(a)
        if brain is not None:
            dg = diag.of(world)
            dg.model_ticks += 1
            if a.thinking and (not a.plan or a.plan[0].get("_filler")):
                dg.waiting_ticks += 1
        if a.brain != INSTINCT and brain is None:
            if self.no_stand_in():
                if not a.plan:
                    self._wait(a)
                return
            # unknown brain id (removed): inherit the world default
            a.brain = self.world_brain.get(world.id, INSTINCT)
            brain = self.brain_for(a)
        if brain is None or not brain.healthy():
            if brain is not None:  # its mind can't vote or weigh an offer now: the simulator's rule stands in
                from ..sim import ballots as BAL

                BAL.skip(world, a.id)
                o = BAL.pending_offer(world, a.id)
                if o is not None:
                    BAL.answer_offer(world, a.id, o["tick"], None)
            ask = (getattr(world, "civic", None) or {}).get("ask")
            if brain is not None and ask and ask.get("leader") == a.id and not ask.get("sent"):
                diag.chief(world, "blocked: the chief's brain unavailable", ask)
            if not a.plan:
                if self.no_stand_in() and a.brain != INSTINCT:
                    self._wait(a)
                else:
                    self._instinct_plan(world, a, "instinct" if brain is None else f"instinct ({brain.label} unavailable)")
            return
        self._civic_asks(world, a, brain)
        # the village needs its next project and this chit is its chief: put the choice to its model
        ask = (getattr(world, "civic", None) or {}).get("ask")
        if ask and ask.get("leader") == a.id and not ask.get("sent"):
            ask["sent"] = True
            diag.chief(world, "sent", ask, queued_behind=brain.stats.queued)
            self._ask_chief(world, a, brain, ask)
        # a pioneer's duty comes before its model's plans: World B's model-minded pioneers founded 1 village in 14 tries
        if not self.no_stand_in() and (not a.plan or a.plan[0].get("_filler")) and self._duty(world, a):
            if a.pending_plan:
                rec = getattr(a, "_decision", None)
                a.pending_plan = None
                if rec is not None:
                    rec["stale_why"] = "a pioneer's duty came first"
                    self._resolve(rec, "stale", world.tick)
            return
        # adopt a finished model plan when the current one is done (or only filler remains)
        if a.pending_plan and (not a.plan or a.plan[0].get("_filler")):
            p = a.pending_plan
            a.pending_plan = None
            rec = getattr(a, "_decision", None)
            too_old = STALE_TICKS * max(1.0, getattr(self, "speed_scale", 1.0))
            menu = self.model_only and rec is not None and rec.get("parse") == "choice"
            if rec is not None and (menu or a.rev != rec["rev_requested"]
                                    or world.tick - rec["tick_requested"] > too_old):
                # the world moved on while the model was thinking: don't act on an out-of-date intention (and in a
                # model-only run never on instinct's drafted option, even one asked for before the switch)
                rec["stale_why"] = ("model-only: a menu choice" if menu else
                                    a.rev_why if a.rev != rec["rev_requested"] else "too old")
                self._resolve(rec, "stale", world.tick)
                if not a.thinking:
                    self._ask(world, a, brain)
                return
            a.plan = p["steps"] if self.model_only else tools_first(world, a, p["steps"])  # a pick before the ore
            origin = "model_selected" if rec and rec.get("parse") == "choice" else "model_generated"
            if rec and rec.get("style") == "repair":
                origin = "model_repaired"
            for step in a.plan:
                step["_origin"] = origin
                step["_decision_id"] = rec.get("request_id") if rec else None
            diag.of(world).authorship[origin] += 1
            a.goal = p.get("goal") or a.goal
            a.thought = p.get("thought") or a.thought
            a.plan_source = f"model:{brain.id}"
            a.plan_started = world.tick
            a.plan_id = uuid.uuid4().hex
            a.decisions += 1
            if p.get("job"):
                world.set_job(a, p["job"], "chosen") if hasattr(world, "set_job") else None
            obj = (p.get("objective") or "").strip()
            if obj and obj.lower() != a.objective.lower():
                a.objective, a.objective_since = obj, world.tick
                world.emit("objective", f'{a.name} is working towards: "{obj}"', 2, a.id, a.x, a.y, objective=obj)
            if rec is not None:
                rec["plan_id"] = a.plan_id
                self._resolve(rec, "adopted", world.tick)
            diag.plan_from(world, "model")
            if p.get("say") and world.flags.get("say") and not any(s.get("do") == "say" for s in a.plan):
                # a reply's "say" answers whoever just spoke to this chit (it went to "all" and never counted)
                heard = a.spoken_to or {}
                to = heard.get("name") if heard.get("id") in world.agents and world.tick - heard.get("tick", 0) < 240 else "all"
                a.plan.insert(0, {"do": "say", "to": to, "text": p["say"]})
            return
        # ask ahead of time: on the last step, or two steps before the end when the model is slow to answer (the
        # 5090's replies took 12.7 s at the median, 25 ticks, while a step often takes fewer)
        need = (not a.plan) or (not a.plan[0].get("_filler") and len(a.plan) <= self.lead(brain))
        if need and not a.thinking and a.pending_plan is None:
            if not a.plan and self.focused(brain) and self._routine(world, a):
                return  # eating and sleeping don't need the model
            slots = max(1, brain.cfg.max_concurrency)
            if not self.no_stand_in() and (brain.stats.queued >= QUEUE_PER_SLOT * slots
                                    or self.plans_out[brain.id] >= (QUEUE_PER_SLOT + 1) * slots):
                # the model is far behind: a request now would wait a minute and come back stale (live, 229 queued
                # behind the 3090's 8 slots, 65 s each, 311 plans stale). Instinct now; ask again next time.
                if not a.plan:  # (counted once, as shed: counted as instinct too, it still diluted the model's share)
                    self._instinct_plan(world, a, f"instinct ({brain.label} queue full)", kind="shed")
                return
            self._ask(world, a, brain)
        if not a.plan and a.thinking and world.tick - a.think_started > self.patience_ticks:
            if self.no_stand_in():
                self._wait(a)
            else:
                self._instinct_plan(world, a, "instinct (while thinking)", filler=True)
        # weekly reflection
        day = world.tick // TICKS_PER_DAY
        if reflection_due(a, day, world.hour) and len(a.memories) >= 6 and not a.thinking \
                and (brain.stats.queued < 2 or world.hour > 20):
            a.last_reflect_day = day
            self._spawn(self._reflect(world, a, brain))

    def new_match(self) -> None:
        """A new match starts: requests still in flight belong to the old one and must not be recorded in it."""
        self.match += 1
        self.decisions.clear()
        self.adopted.clear()

    def _resolve(self, rec: Dict[str, Any], outcome: str, tick: int) -> None:
        rec["outcome"] = outcome
        rec["tick_resolved"] = tick
        if rec.get("match", self.match) != self.match:
            return  # a reply from the previous match
        if outcome == "adopted" and rec.get("style") not in CIVIC_STYLES:
            self.adopted[rec.get("world")] += 1
        if self.on_decision:
            try:
                self.on_decision(rec)
            except Exception as e:  # recording must never break the world
                log.warning("decision record failed: %s", e)

    def _wait(self, a: Agent) -> None:
        """Experiment contract: no instinct stand-in. The chit simply waits for its own mind."""
        a.plan_source = "waiting"
        a.activity = "waiting for its mind"

    def lead(self, brain: LLMBrain) -> int:
        """How many steps before a plan runs out to ask for the next one: 2 for a model slower than SLOW_TICKS."""
        ticks = brain.stats.latency_ms_avg / 1000.0 * TICKS_PER_SEC * max(1.0, getattr(self, "speed_scale", 1.0))
        return 2 if ticks >= SLOW_TICKS else 1

    def repairs(self) -> bool:
        """Bounded action repair (item 40) is on in play; an experiment has it only when its protocol declares it."""
        return self.repair if self.repair is not None else not self.strict

    def _repair_note(self, world, a: Agent) -> Optional[Dict[str, Any]]:
        """The model's step just failed: its next request (this one) says exactly why and asks for a plan that works.
        Once per failure, not in reply to a repaired plan's own failure (sim/actions.py), and only while fresh."""
        rep = a.__dict__.pop("_repair", None)
        if not rep or not self.repairs() or world.tick - rep["tick"] > STALE_TICKS:
            return None
        return rep

    def focused(self, brain: LLMBrain) -> bool:
        return bool(getattr(brain.cfg, "focus", False)) and not self.no_stand_in()  # an experiment's model decides everything

    def start_model_only(self, world) -> int:
        """Model-only switched on mid-game: every chit drops the steps its model didn't write itself (instinct,
        reflex, filler, routine, duty, fallback and menu choices) and every request in flight goes stale (its rev is
        bumped), so nothing from before the switch acts after it. The moment is recorded (diag.model_only_from).
        Returns how many steps were dropped."""
        dropped = sum(self._model_only_clean(world, a, "model-only switched on") for a in world.agents.values())
        world.model_only = True
        diag.model_only_from(world, dropped)
        return dropped

    def _model_only_clean(self, world, a: Agent, why: str) -> int:
        """One chit, under model-only: drop the steps its model didn't write and any menu choice waiting to be
        adopted, and stale what is in flight. Marked with its brain, so it isn't cleaned twice under the same one.
        Returns the steps dropped."""
        own = ("model_generated", "model_repaired")
        keep = [s for s in a.plan if s.get("_origin") in own and not s.get("_reflex") and not s.get("_filler")]
        dropped = len(a.plan) - len(keep)
        a.plan = keep
        if a.pending_plan is not None:
            rec = getattr(a, "_decision", None)
            if rec is not None and rec.get("parse") == "choice":
                a.pending_plan = None
                rec["stale_why"] = "model-only: a menu choice"
                self._resolve(rec, "stale", world.tick)
        a.bump_rev(why)
        a.__dict__["_model_only_brain"] = a.brain
        return dropped

    def _became_model_driven(self, world, a: Agent) -> None:
        """Under model-only, a chit that has just come under a model (assigned one, or arriving where one drives
        it) leaves its instinct plan behind before it acts."""
        if a.brain != INSTINCT and a.__dict__.get("_model_only_brain") != a.brain:
            diag.model_only_dropped(world, self._model_only_clean(world, a, "model-only: a model took over"))

    def no_stand_in(self) -> bool:
        """No instinct plan for a model's chit, ever: the experiment contract, or a model-only diagnostic run."""
        return self.strict or self.model_only

    def style_of(self, brain: LLMBrain) -> str:
        """The prompt style a request goes out in: the brain's own, or full in a model-only run (no instinct menu)."""
        return "full" if self.model_only else (getattr(brain.cfg, "prompt_style", "full") or "full")

    def _duty(self, world, a: Agent) -> bool:
        """A pioneer (sim/pioneers.py) lights the new village's fire and builds its home there on instinct, whatever its
        model would rather do. Not in an experiment, where the model decides everything."""
        p = pioneer_plan(world, a)
        if not p:
            return False
        a.plan = p["steps"]
        a.goal, a.thought = p["goal"], p["thought"]
        a.plan_source = "instinct-duty"
        a.plan_started = world.tick
        a.plan_id = uuid.uuid4().hex
        for step in a.plan:
            step["_origin"] = "duty"
        diag.of(world).authorship["duty"] += 1
        diag.plan_from(world, "duty")
        return True

    def _routine(self, world, a: Agent) -> bool:
        """Instinct's next plan, if it is only routine (eat, sleep, rest, shelter, store, drop, refuel, and going to do
        one of those): adopted without asking the model. Anything else goes to the model as before."""
        p = self.instinct.plan(world, a)
        verbs = {st.get("do") for st in p["steps"]}
        if not p["steps"] or not verbs <= ROUTINE | {"go"} or not verbs & ROUTINE:
            return False
        a.plan = p["steps"]
        a.goal, a.thought = p["goal"], p["thought"]
        a.plan_source = "instinct-routine"
        a.plan_started = world.tick
        a.plan_id = uuid.uuid4().hex
        for step in a.plan:
            step["_origin"] = "routine"
        diag.of(world).authorship["routine"] += 1
        diag.plan_from(world, "routine")
        return True

    def _instinct_plan(self, world, a: Agent, source: str, filler: bool = False, kind: str = "") -> None:
        p = self.instinct.plan(world, a)
        steps = p["steps"]  # the whole plan: cut to its first step, "gather clay" never reached "experiment"
        if filler:
            for s in steps:
                s["_filler"] = True
        a.plan = steps
        if not filler or not a.goal:
            a.goal = p["goal"]
            a.thought = p["thought"]
        kind = kind or ("filler" if filler else ("fallback" if "unavailable" in source else "instinct"))
        a.plan_source = {"filler": "instinct-filler", "fallback": "instinct-fallback"}.get(kind, "instinct")
        a.plan_started = world.tick
        a.plan_id = uuid.uuid4().hex
        for step in a.plan:
            step["_origin"] = kind
        diag.of(world).authorship[kind] += 1
        diag.plan_from(world, kind)

    # ------------------------------------------------------------ async requests
    def _spawn(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None
        t = loop.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def _spawn_plan(self, brain: LLMBrain, coro) -> None:
        """A plan request, counted out against its brain until it finishes. The count is taken here, when the request
        is made: the brain's own queue count only rises once the task first runs, after the whole tick, so every chit
        in a tick saw the same short queue and all of them went past the cap (Codex, #29)."""
        t = self._spawn(coro)
        if t is not None:
            bid = brain.id
            self.plans_out[bid] += 1
            t.add_done_callback(lambda _t: self.plans_out.subtract([bid]))

    def _ask(self, world, a: Agent, brain: LLMBrain) -> None:
        # the brain's own prompt_style, or full in a model-only run (no instinct menu): the same rule as style_of
        style = "full" if self.model_only else (getattr(brain.cfg, "prompt_style", "full") or "full")
        if style in ("choose", "cascade"):
            return self._ask_choice(world, a, brain, cascade=style == "cascade")
        rep = self._repair_note(world, a)
        msgs = P.messages(world, a, style=style)
        if rep:
            msgs = P.with_repair(msgs, rep)
        a.thinking = True
        a.think_started = world.tick
        rec = {"request_id": uuid.uuid4().hex, "world": world.id, "epoch": getattr(world, "epoch", ""),
               "agent": a.id, "agent_name": a.name, "brain": brain.id,
               "model": brain.cfg.model or brain.stats.resolved_model, "base_url": brain.cfg.base_url,
               "tick_requested": world.tick, "rev_requested": a.rev, "prompt_version": P.PROMPT_VERSION,
               "prompt_hash": hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()[:16],
               "temperature": brain.cfg.temperature, "max_tokens": brain.cfg.max_tokens,
               "latency_ms": None, "tokens_in": None, "tokens_out": None, "response_hash": None,
               "parse": None, "rejected_steps": 0, "outcome": "pending", "tick_resolved": None, "plan_id": None}
        rec["match"] = self.match
        if rep:  # both attempts are on record: this one points at the decision whose step failed
            rec.update(style="repair", repair_of=rep.get("decision_id"), repair_step=rep["failed"],
                       repair_reason=rep["reason"])
        self.decisions.append(rec)
        a._decision = rec

        def at_send():  # the 3090 queued requests ~6 s: describe the chit as it is when the request goes out
            if rec.get("match") != self.match:
                raise StaleMatch()  # a new match started while this waited: don't spend the GPU on it
            fresh = P.messages(world, a, style=style)
            if rep:
                fresh = P.with_repair(fresh, rep)
            rec["tick_requested"], rec["rev_requested"] = world.tick, a.rev
            rec["prompt_hash"] = hashlib.sha256(json.dumps(fresh, sort_keys=True).encode()).hexdigest()[:16]
            sent["msgs"] = fresh
            return fresh

        sent: Dict[str, Any] = {"msgs": msgs}
        self._spawn_plan(brain, self._think(world, a, brain, at_send, rec, sent))

    def _ask_choice(self, world, a: Agent, brain: LLMBrain, cascade: bool = False) -> None:
        """Choose mode: instinct drafts a few plans, the model picks one by letter (one output token, scored by
        logprobs). The chit still follows its model's choice; the model just doesn't write the plan."""
        a.thinking = True
        a.think_started = world.tick
        rec = {"request_id": uuid.uuid4().hex, "world": world.id, "epoch": getattr(world, "epoch", ""),
               "agent": a.id, "agent_name": a.name, "brain": brain.id, "style": "choose",
               "model": brain.cfg.model or brain.stats.resolved_model, "base_url": brain.cfg.base_url,
               "tick_requested": world.tick, "rev_requested": a.rev, "prompt_version": P.PROMPT_VERSION,
               "prompt_hash": "", "temperature": brain.cfg.temperature, "max_tokens": 1,
               "latency_ms": None, "tokens_in": None, "tokens_out": None, "response_hash": None,
               "parse": None, "rejected_steps": 0, "outcome": "pending", "tick_resolved": None, "plan_id": None,
               "match": self.match}
        rep = self._repair_note(world, a) if CHOICE_REPAIR else None
        if rep:  # as in _ask: its choice is then "model_repaired", and a repaired choice that fails isn't repaired again
            rec.update(style="repair", repair_of=rep.get("decision_id"), repair_step=rep["failed"],
                       repair_reason=rep["reason"])
        self.decisions.append(rec)
        a._decision = rec
        sent: Dict[str, Any] = {"repair": rep}

        def at_send():
            if rec.get("match") != self.match:
                raise StaleMatch()
            opts = self.instinct.options(world, a)
            # shuffled, so the model's pick is its own and not "always the first one" (instinct's)
            random.Random(world.tick * 13 + zlib.crc32(a.id.encode())).shuffle(opts)
            sent["options"] = opts
            msgs = P.choice_messages(world, a, opts, own_idea=cascade, repair=rep)
            rec["tick_requested"], rec["rev_requested"] = world.tick, a.rev
            rec["prompt_hash"] = hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()[:16]
            return msgs

        self._spawn_plan(brain, self._choose(world, a, brain, at_send, rec, sent, cascade))

    def _ask_chief(self, world, a: Agent, brain: LLMBrain, ask: Dict[str, Any]) -> None:
        """The chief chooses the village's next project from the world's candidates: one token, scored by logprobs,
        recorded as a decision. The world checks the answer (projects.answer); without one, need decides."""
        from ..sim import projects as PJ

        options = list(ask["options"])
        msgs = P.chief_project_messages(world, a, options)
        rec = {"request_id": uuid.uuid4().hex, "world": world.id, "epoch": getattr(world, "epoch", ""),
               "agent": a.id, "agent_name": a.name, "brain": brain.id, "style": "chief-project",
               "model": brain.cfg.model or brain.stats.resolved_model, "base_url": brain.cfg.base_url,
               "tick_requested": world.tick, "rev_requested": a.rev, "prompt_version": P.PROMPT_VERSION,
               "prompt_hash": hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()[:16],
               "temperature": brain.cfg.temperature, "max_tokens": 1, "latency_ms": None, "tokens_in": None,
               "tokens_out": None, "response_hash": None, "parse": None, "rejected_steps": 0, "outcome": "pending",
               "tick_resolved": None, "plan_id": None, "match": self.match}
        self.decisions.append(rec)

        async def run() -> None:
            try:
                res = await brain.chat(msgs, max_tokens=1, json_reply=False, extra={"logprobs": True, "top_logprobs": 10})
                if rec.get("match") != self.match:
                    return
                diag.chief(world, "answered", ask, queue_ms=round(res.get("queue_ms") or 0),
                           latency_ms=round(res.get("latency_ms") or 0))
                valid = P.LETTERS[:len(options)]
                scores = {t.strip().upper(): lp for t, lp in (res.get("top_logprobs") or {}).items()
                          if t.strip().upper() in valid and len(t.strip()) == 1}
                letter = max(scores, key=scores.get) if scores else res["text"].strip().upper()
                rec.update(latency_ms=round(res["latency_ms"]), tokens_in=res.get("tokens_in"),
                           tokens_out=res.get("tokens_out"), response_hash=letter[:1])
                if letter not in valid or len(letter) != 1:
                    rec["parse"] = "invalid_choice"
                    brain.stats.parse_failed += 1
                    self._resolve(rec, "failed", world.tick)
                    diag.chief(world, "invalid choice", ask, end=True)
                    return
                rec["parse"] = "choice"
                rec["choice"] = {"requested": letter, "confidence": round(math.exp(scores[letter]), 2) if letter in scores else None,
                                 "options": [PJ.option_words(o) for o in options]}
                p = PJ.answer(world, a.id, valid.index(letter))
                adopted = p is not None and p.get("chosen_by") == "chief"
                self._resolve(rec, "adopted" if adopted else "stale", world.tick)
                diag.chief(world, "adopted" if adopted else "stale on arrival", ask, end=True)
            except Exception as e:  # the question stands until it expires; need decides then
                rec["parse"] = rec.get("parse") or f"error: {type(e).__name__}"
                self._resolve(rec, "failed", world.tick)
                diag.chief(world, "request failed", ask, error=type(e).__name__)

        self._spawn(run())

    def _civic_asks(self, world, a: Agent, brain: LLMBrain) -> None:
        """An election this chit votes in, or a trade offered to it: one letter from its own mind (sim/ballots.py)."""
        from ..sim import ballots as BAL

        p = BAL.poll(world)
        if p and a.id in p["voters"] and a.id not in p["sent"] and a.id not in p["ballots"] and a.id not in p["skipped"]:
            p["sent"].append(a.id)
            cands = [world.agents[c] for c in BAL.ballot_for(world, a.id)]
            if not cands:
                BAL.skip(world, a.id)
            else:
                ids = [o.id for o in cands]
                self._ask_letter(world, a, brain, "vote", P.vote_messages(world, a, cands), len(cands),
                                 lambda i: BAL.cast(world, a.id, ids[i]), lambda: BAL.skip(world, a.id),
                                 {"options": [o.name for o in cands]})
        o = BAL.pending_offer(world, a.id)
        if o is not None and not o["sent"]:
            o["sent"] = True
            trader = world.agents.get(o["from"])
            if trader is None:
                BAL.answer_offer(world, a.id, o["tick"], None)
                return
            t0 = o["tick"]
            self._ask_letter(world, a, brain, "trade-offer", P.trade_messages(world, a, trader, o["give"], o["get"]), 2,
                             lambda i: BAL.answer_offer(world, a.id, t0, i == 0),
                             lambda: BAL.answer_offer(world, a.id, t0, None),
                             {"options": ["accept", "refuse"], "from": trader.name})

    def _ask_letter(self, world, a: Agent, brain: LLMBrain, style: str, msgs, n: int, on_choice, on_fail,
                    info: Dict[str, Any]) -> None:
        """A one-letter question to a chit's mind, scored by logprobs and recorded as a decision. `on_choice(i)` hands
        the world the answer (it returns whether the world took it); `on_fail()` lets the simulator decide."""
        rec = {"request_id": uuid.uuid4().hex, "world": world.id, "epoch": getattr(world, "epoch", ""),
               "agent": a.id, "agent_name": a.name, "brain": brain.id, "style": style,
               "model": brain.cfg.model or brain.stats.resolved_model, "base_url": brain.cfg.base_url,
               "tick_requested": world.tick, "rev_requested": a.rev, "prompt_version": P.PROMPT_VERSION,
               "prompt_hash": hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()[:16],
               "temperature": brain.cfg.temperature, "max_tokens": 1, "latency_ms": None, "tokens_in": None,
               "tokens_out": None, "response_hash": None, "parse": None, "rejected_steps": 0, "outcome": "pending",
               "tick_resolved": None, "plan_id": None, "match": self.match}
        self.decisions.append(rec)

        async def run() -> None:
            try:
                res = await brain.chat(msgs, max_tokens=1, json_reply=False, extra={"logprobs": True, "top_logprobs": 10})
                if rec.get("match") != self.match:
                    return
                valid = P.LETTERS[:n]
                scores = {t.strip().upper(): lp for t, lp in (res.get("top_logprobs") or {}).items()
                          if t.strip().upper() in valid and len(t.strip()) == 1}
                letter = max(scores, key=scores.get) if scores else res["text"].strip().upper()
                rec.update(latency_ms=round(res["latency_ms"]), tokens_in=res.get("tokens_in"),
                           tokens_out=res.get("tokens_out"), response_hash=letter[:1])
                if letter not in valid or len(letter) != 1:
                    rec["parse"] = "invalid_choice"
                    brain.stats.parse_failed += 1
                    on_fail()
                    self._resolve(rec, "failed", world.tick)
                    return
                rec["parse"] = "choice"
                rec["choice"] = {"requested": letter, "confidence": round(math.exp(scores[letter]), 2) if letter in scores
                                 else None, **info}
                self._resolve(rec, "adopted" if on_choice(valid.index(letter)) else "stale", world.tick)
            except Exception as e:  # no answer: the simulator's rule decides
                rec["parse"] = rec.get("parse") or f"error: {type(e).__name__}"
                on_fail()
                self._resolve(rec, "failed", world.tick)

        self._spawn(run())

    async def _choose(self, world, a: Agent, brain: LLMBrain, at_send, rec, sent, cascade: bool = False) -> None:
        m0 = time.monotonic()
        entry: Dict[str, Any] = {"t": time.time(), "world": world.id, "agent": a.name, "brain": brain.label, "tick": world.tick}
        try:
            res = await brain.chat(at_send, max_tokens=1, json_reply=False,
                                   extra={"logprobs": True, "top_logprobs": 10})
            opts = sent.get("options") or []
            if not opts:
                raise ValueError("no options")
            valid = P.LETTERS[:len(opts) + (1 if cascade else 0)]
            scores = {t.strip().upper(): lp for t, lp in (res.get("top_logprobs") or {}).items()
                      if t.strip().upper() in valid and len(t.strip()) == 1}
            letter = max(scores, key=scores.get) if scores else res["text"].strip().upper()
            if letter not in valid or len(letter) != 1:
                brain.stats.parse_failed += 1
                rec["parse"] = "invalid_choice"
                raise ParseError("choice reply was not a valid option letter")
            probs = {k: math.exp(v) for k, v in scores.items()}
            conf = round(probs.get(letter, 0.0), 2) if scores else None
            rec["choice"] = {"requested": letter, "confidence": conf,
                             "prompt_hash": rec["prompt_hash"], "max_tokens": 1,
                             "latency_ms": round(res["latency_ms"]), "queue_ms": res.get("queue_ms"),
                             "tokens_in": res.get("tokens_in"), "tokens_out": res.get("tokens_out")}
            own = cascade and letter == valid[-1]
            unsure = cascade and conf is not None and conf < float(getattr(brain.cfg, "escalate_below", 0.5) or 0)
            a.last_choice = {"tick": world.tick, "chose": letter, "confidence": conf, "escalated": False,
                             "options": [{"letter": valid[i], "goal": o.get("goal", ""), "p": round(probs.get(valid[i], 0.0), 3)}
                                         for i, o in enumerate(opts)]
                             + ([{"letter": valid[-1], "goal": P.OWN_IDEA, "p": round(probs.get(valid[-1], 0.0), 3)}] if cascade else [])}
            recent = brain.__dict__.setdefault("recent_escalations", deque(maxlen=40))
            budget = len(recent) < 5 or sum(recent) / len(recent) < float(getattr(brain.cfg, "escalate_share", 0.3) or 0)
            go_full = (own or unsure) and budget and brain.stats.queued < max(1, brain.cfg.max_concurrency)
            recent.append(bool(go_full))
            rec["choice"].update(escalation_requested=bool(own or unsure), escalated=bool(go_full),
                                 denial=("budget" if not budget else "queue") if (own or unsure) and not go_full else None)
            if not go_full and (own or unsure):
                a.last_choice["why"] = "wanted its own idea, but the mind was busy" if own else f"unsure ({conf}), mind busy"
            if go_full:
                # the cascade (JEV's confidence gate): its own idea, or not sure, and the server has room -> it
                # writes its own plan. Routine moments stay one token; the interesting ones get the full mind.
                a.last_choice["escalated"] = True
                a.last_choice["why"] = "its own idea" if own else f"unsure ({conf})"
                brain.stats.ok += 1
                entry.update(ok=True, ms=round(res["latency_ms"]), chose=f"{letter} of {len(valid)}", confidence=conf,
                             escalated=a.last_choice["why"])
                sent_full: Dict[str, Any] = {}

                def full_at_send():
                    if rec.get("match") != self.match:
                        raise StaleMatch()
                    fresh = P.messages(world, a, style="full")
                    if sent.get("repair"):  # the plan it writes answers the failure, as a full brain's does
                        fresh = P.with_repair(fresh, sent["repair"])
                    rec["prompt_hash"] = hashlib.sha256(json.dumps(fresh, sort_keys=True).encode()).hexdigest()[:16]
                    rec["max_tokens"] = brain.cfg.max_tokens
                    rec["tick_requested"], rec["rev_requested"] = world.tick, a.rev
                    rec["style"] = "repair" if sent.get("repair") else "cascade-full"
                    sent_full["msgs"] = fresh
                    return fresh

                self.log.append(entry)
                entry = {}
                await self._think(world, a, brain, full_at_send, rec, sent_full)
                return
            if own:
                letter = max((k for k in scores if k != valid[-1]), key=scores.get, default="A")
            rec["choice"]["executed"] = letter
            a.last_choice["requested"] = a.last_choice["chose"]
            a.last_choice["chose"] = letter
            chosen = opts[valid.index(letter)] if letter in valid[:len(opts)] else opts[0]
            plan = {"goal": chosen.get("goal", ""), "thought": chosen.get("thought", ""), "steps": chosen["steps"],
                    "objective": "", "say": "", "job": None, "repaired": False, "rejected": 0}
            brain.stats.ok += 1
            rec.update(latency_ms=round(res["latency_ms"]), queue_ms=res.get("queue_ms"), tokens_in=res.get("tokens_in"), tokens_out=res.get("tokens_out"),
                       response_hash=letter, parse="choice", model=brain.stats.resolved_model or rec.get("model"))
            if a.alive:
                a.pending_plan = plan
            entry.update(ok=True, ms=round(res["latency_ms"]), goal=plan["goal"], thought=plan["thought"],
                         chose=f"{letter} of {len(opts)}", confidence=conf,
                         steps=[{k: v for k, v in s.items() if not k.startswith("_")} for s in plan["steps"]])
        except StaleMatch:
            entry.update(ok=False, error="dropped: a new match started while this was queued")
        except Exception as e:
            entry.update(ok=False, error=f"{type(e).__name__}: {str(e)[:160]}")
            rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            self._resolve(rec, "failed", world.tick)
        finally:
            if entry:  # (an escalated choice logged its entry and handed over to _think)
                a.thinking = False
                entry["wall_ms"] = round((time.monotonic() - m0) * 1000)
                self.log.append(entry)
                del self.log[:-80]

    async def _think(self, world, a: Agent, brain: LLMBrain, msgs, rec: Optional[Dict[str, Any]] = None,
                     sent: Optional[Dict[str, Any]] = None) -> None:
        rec = rec if rec is not None else {"outcome": "pending", "rev_requested": a.rev, "tick_requested": world.tick}
        t0 = time.time()
        m0 = time.monotonic()  # for the duration: WSL wall time steps back ~2.7 s every ~30 s
        entry: Dict[str, Any] = {"t": t0, "world": world.id, "agent": a.name, "brain": brain.label, "tick": world.tick}
        text = ""
        try:
            res = await brain.chat(msgs)
            text = res["text"]
            parse_how = "ok"
            try:
                plan = parse_plan(text)
            except ParseError:
                parse_how = "retried"
                # one gentle retry asking for strict JSON
                brain.stats.parse_failed += 1
                brain.stats.retries += 1
                first = sent["msgs"] if sent else msgs
                res = await brain.chat(first + [{"role": "assistant", "content": text[:1500]},
                                               {"role": "user", "content": "That wasn't valid. Reply with ONLY the JSON object: {\"thought\":...,\"goal\":...,\"plan\":[...]}"}])
                text = res["text"]
                plan = parse_plan(text)
            brain.stats.ok += 1
            if plan.get("repaired"):
                brain.stats.repaired += 1
                if parse_how == "ok":
                    parse_how = "repaired"
            rec.update(latency_ms=round(res["latency_ms"]), queue_ms=res.get("queue_ms"), tokens_in=res.get("tokens_in"), tokens_out=res.get("tokens_out"),
                       response_hash=hashlib.sha256(text.encode()).hexdigest()[:16], parse=parse_how,
                       rejected_steps=plan.get("rejected", 0), model=brain.stats.resolved_model or rec.get("model"))
            if a.alive:
                a.pending_plan = plan
            entry.update(ok=True, ms=round(res["latency_ms"]), goal=plan["goal"], thought=plan["thought"],
                         steps=[{k: v for k, v in s.items() if not k.startswith("_")} for s in plan["steps"]])
        except ParseError as e:
            brain.stats.parse_failed += 1
            rec.update(parse="failed", response_hash=hashlib.sha256(text.encode()).hexdigest()[:16])
            self._resolve(rec, "failed", world.tick)
            entry.update(ok=False, error=f"unreadable reply: {e}", raw=text[:400])
            a.last_result = "(your last reply could not be understood — reply with the JSON object only)"
        except StaleMatch:
            entry.update(ok=False, error="dropped: a new match started while this was queued")
        except Exception as e:
            entry.update(ok=False, error=f"{type(e).__name__}: {str(e)[:160]}")
            rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            self._resolve(rec, "failed", world.tick)
        finally:
            a.thinking = False
            entry["wall_ms"] = round((time.monotonic() - m0) * 1000)
            self.log.append(entry)
            del self.log[:-80]

    async def _reflect(self, world, a: Agent, brain: LLMBrain) -> None:
        match = self.match

        def at_send():
            if self.match != match:
                raise StaleMatch()
            return P.reflection_messages(world, a)

        try:
            res = await brain.chat(at_send, max_tokens=450, temperature=0.6)
        except Exception:
            return
        if self.match != match:
            return
        if a.alive:
            apply_reflection(world, a, res["text"])

    # ------------------------------------------------------------ status
    def status(self, speed: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        out = []
        for b in self.brains.values():
            st = b.stats.__dict__.copy()
            row = {"config": b.cfg.public(), "stats": st, "label": b.label, "healthy": b.healthy()}
            if speed and b.id in speed:
                row["speed"] = speed[b.id]
            out.append(row)
        return {"brains": out, "assign": self.world_brain, "presets": PRESETS, "log": self.log[-30:], "narrator": self.narrator,
                "model_only": self.model_only}

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        for b in self.brains.values():
            await b.close()
