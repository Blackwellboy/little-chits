"""What a run did, watched from outside the game: preventable deaths, stuck chits and how often each mechanism fired.

A Probe attaches to one World and only reads it. It listens to the world's events (``w.listeners``), plans for the
chits the way the instinct runs do (``Probe.hook``), looks at the hungry ones after each tick, and sums the chits'
own lifetime counters (``Agent.stats``) at the end. The game itself gains no code and no cost.

    probe = Probe(world)
    with probe:
        for _ in range(days * 240):
            world.step(probe.hook)
            probe.after_tick()
    probe.report()
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any, Dict, List, Optional

from chits.sim.actions import DONE  # (the server dir under test must be on sys.path: run.py puts it there)

HUNGRY = 40  # a chit's hunger (100 = full) at or below which its ring buffer records what it is doing
RING = 30  # entries kept per chit
RESAMPLE = 20  # ticks between entries while nothing about the chit changes
STORE_LOOK = 60  # tiles: how far the ring buffer looks for the nearest store with food
PREVENTABLE_NEAR = 30  # tiles: a starvation with food in a store on the chit's own land this close was preventable
# A chit that replans the same goal with a failing first step more than STUCK_AFTER times in a row is stuck. Over
# seeds 42, 24, 7 and 99 (60 days, 128 map, main at 2011d88) such runs were 792 one deep, 10 two deep and 1 three
# deep (ordinary retries), then 5, 6 and 56 deep: a deer that kept getting away, a pick nobody had, and a chit
# trying to pick up wood for a stockpile 56 times with its hands full.
STUCK_AFTER = 3

# Every mechanism the run counts, in one place: name -> (source, key, breakdown). "event" counts the world's events of
# kind `key` (broken down by that event's data field, if given); "stat" sums each chit's lifetime counter `key`
# (Agent.bump), or every counter starting with it when it ends in "_" (broken down by the rest of the name).
MECHANISMS: Dict[str, tuple] = {
    "craft": ("stat", "made_", "recipe"),  # (the "crafted" event is only a chit's first of each thing)
    "build": ("event", "built", "design"),
    "mend building": ("stat", "repaired", None),
    "mend tool": ("stat", "tools_mended", None),
    "smelt tool down": ("stat", "tools_smelted", None),
    "restore ruin": ("event", "restored", None),
    "refuel": ("stat", "refueled", None),
    "light fire": ("event", "fire_lit", None),
    "station shift": ("stat", "shifts", None),
    "station goods": ("stat", "produced_", "item"),
    "experiment": ("stat", "experiments", None),
    "discovery": ("event", "discovery", None),
    "invention": ("event", "invention", None),
    "trade": ("event", "trade", None),
    "barter": ("stat", "bartered", None),
    "voyage": ("event", "voyage", None),
    "arrival": ("event", "arrival", None),
    "wolf attack": ("event", "wolf", None),
    "wolf driven off": ("event", "wolf_driven_off", None),
    "fight": ("event", "fight", None),
    "theft": ("event", "theft", None),
    "hunt": ("event", "hunt", None),
    "tame": ("event", "tamed", None),
    "fish": ("stat", "fish", None),
    "plant": ("stat", "planted", None),
    "harvest": ("event", "harvest", None),
    "mine": ("stat", "mined", None),
    "prospect": ("stat", "prospected", None),
    "road": ("stat", "roads", None),
    "teach": ("stat", "taught", None),
    "write": ("stat", "wrote", None),
    "read": ("stat", "read", None),
    "school lesson": ("stat", "school_lessons", None),
    "forgotten": ("event", "forgotten", None),
    "project done": ("event", "project_done", None),
    "pioneers": ("event", "pioneers", None),
    "daughter village": ("event", "daughter_village", None),
    "tunnel": ("event", "tunnel", None),
    "tool broke": ("event", "tool_broke", None),
    "spoiled": ("event", "spoiled", None),
    "birth": ("event", "birth", None),
    "death": ("event", "death", "cause"),
}


def _food_in(world, s) -> int:
    return sum(n for k, n in s.storage.items() if n > 0 and (it := world.item(k)) is not None and it.food > 0)


class Probe:
    def __init__(self, world, brain=None) -> None:
        if brain is None:
            from chits.brain.instinct import Instinct  # (imported here so a test can hand in its own brain)

            brain = Instinct()
        self.w, self.brain = world, brain
        self.events: Counter = Counter()  # kind, and "kind:value" for a mechanism's breakdown field
        self.seen: Dict[str, Any] = {}  # agent id -> its latest Agent (a chit that sailed away keeps its counters)
        self.buf: Dict[str, deque] = {}
        self._sig: Dict[str, tuple] = {}
        self.starved: List[Dict[str, Any]] = []  # every starvation, each with its buffer and whether it was preventable
        self._first: Dict[str, Any] = {}  # agent id -> the first step of the plan the probe gave it
        self._fail: Dict[str, list] = {}  # agent id -> [goal, failing first steps in a row, its stuck entry or None]
        self.stuck: List[Dict[str, Any]] = []  # one entry per stuck episode
        self.streaks: Counter = Counter()  # length of each finished run of same-goal first-step failures -> how many
        self._breakdown = {kind: field for kind, field in ((m[1], m[2]) for m in MECHANISMS.values() if m[0] == "event")
                           if field}
        world.listeners.append(self._on_event)

    # ------------------------------------------------------------------ wiring
    def __enter__(self) -> "Probe":
        """Watch step outcomes (chits.diag.action_finished, which the game calls for every finished step)."""
        from chits import diag

        self._diag, self._orig = diag, getattr(diag, "action_finished", None)
        if self._orig is None:  # (an older tree: no stuck detector there)
            return self
        orig, me = self._orig, self

        def action_finished(world, a, step, result):
            orig(world, a, step, result)
            if world is me.w:
                me._finished(a, step, result)

        diag.action_finished = action_finished
        return self

    def __exit__(self, *exc) -> None:
        if self._orig is not None:
            self._diag.action_finished = self._orig

    def hook(self, world, a) -> None:
        """The brain hook the instinct A/B runs have always used (tests/identity_runner.py's, without plan_source),
        noting the first step of each plan it hands out."""
        self.seen[a.id] = a
        if not a.plan:
            p = self.brain.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]
            self._first[a.id] = a.plan[0] if a.plan else None

    # ------------------------------------------------------------------ events
    def _on_event(self, ev) -> None:
        self.events[ev.kind] += 1
        field = self._breakdown.get(ev.kind)
        if field and isinstance(v := (ev.data or {}).get(field), str):
            self.events[f"{ev.kind}:{v}"] += 1
        if ev.kind == "death" and (ev.data or {}).get("cause") == "starvation":
            a = self.w.dead.get(ev.actor)
            if a is not None:
                self.starved.append(self._autopsy(a, ev))

    def _autopsy(self, a, ev) -> Dict[str, Any]:
        """At the moment of death: was there food in a store on its own land within PREVENTABLE_NEAR tiles?"""
        near = [(s.dist(a.x, a.y), s) for s in self.w.structures_near(a.x, a.y, PREVENTABLE_NEAR, "stockpile")]
        food = sorted(((d, s) for d, s in near if _food_in(self.w, s) and self.w.same_land(a, s)), key=lambda x: x[0])
        best = food[0] if food else None
        return {"name": a.name, "id": a.id, "tick": self.w.tick, "day": self.w.tick // 240, "text": ev.text,
                "at": [a.x, a.y], "preventable": best is not None,
                "store": None if best is None else {"id": best[1].id, "dist": round(best[0], 1),
                                                    "food": _food_in(self.w, best[1])},
                "buffer": list(self.buf.get(a.id, ()))}

    # ------------------------------------------------------------------ stuck detector
    def _finished(self, a, step, result) -> None:
        first = self._first.get(a.id)
        if first is None or step is not first:
            return
        self._first[a.id] = None
        f = self._fail.get(a.id)
        if result == DONE:
            self._end_streak(a.id)
            return
        if f is None or f[0] != a.goal:
            self._end_streak(a.id)
            f = self._fail[a.id] = [a.goal, 0, None]
        f[1] += 1
        why = f"{step.get('do')}:{step.get('what') or step.get('target') or ''} -> {str(result)[:80]}"
        if f[1] == STUCK_AFTER + 1:
            f[2] = {"name": a.name, "id": a.id, "tick": self.w.tick, "day": self.w.tick // 240, "goal": a.goal,
                    "failure": why, "times": f[1]}
            self.stuck.append(f[2])
        elif f[2] is not None:
            f[2]["times"] = f[1]

    def _end_streak(self, aid: str) -> None:
        f = self._fail.pop(aid, None)
        if f and f[1]:
            self.streaks[f[1]] += 1

    # ------------------------------------------------------------------ ring buffer
    def after_tick(self) -> None:
        w = self.w
        for a in w.agents.values():
            if a.hunger > HUNGRY:
                continue
            head = a.plan[0] if a.plan else {}
            sig = (a.goal, head.get("do"), head.get("what"), a.last_result)
            if self._sig.get(a.id) == sig and w.tick % RESAMPLE:
                continue
            self._sig[a.id] = sig
            b = self.buf.get(a.id)
            if b is None:
                b = self.buf[a.id] = deque(maxlen=RING)
            b.append({"tick": w.tick, "hunger": round(a.hunger), "at": [a.x, a.y], "goal": a.goal,
                      "step": f"{head.get('do')}:{head.get('what') or head.get('target') or ''}" if head else None,
                      "reflex": bool(head.get("_reflex")), "result": str(a.last_result)[:80],
                      "food_held": sum(n for k, n in a.inventory.items() if n > 0 and (it := w.item(k)) and it.food > 0),
                      "store": self._nearest_store(a)})

    def _nearest_store(self, a) -> Optional[Dict[str, Any]]:
        w = self.w
        near = sorted(((s.dist(a.x, a.y), s) for s in w.structures_near(a.x, a.y, STORE_LOOK, "stockpile")
                       if _food_in(w, s)), key=lambda x: x[0])
        if not near:
            return None
        d, s = near[0]
        return {"id": s.id, "dist": round(d, 1), "food": _food_in(w, s), "same_land": w.same_land(a, s),
                "unreachable": a.reflex_rest.get("unreach:" + s.id, 0) > w.tick}

    # ------------------------------------------------------------------ results
    def fired(self) -> Dict[str, int]:
        """How often each mechanism fired over the run (MECHANISMS order)."""
        stats = self._stats()
        out = {}
        for name, (src, key, _) in MECHANISMS.items():
            if src == "event":
                out[name] = self.events.get(key, 0)
            elif key.endswith("_"):
                out[name] = sum(n for k, n in stats.items() if k.startswith(key))
            else:
                out[name] = stats.get(key, 0)
        return out

    def breakdown(self) -> Dict[str, Dict[str, int]]:
        """The mechanisms with a breakdown, by recipe, design, item or cause."""
        stats = self._stats()
        out = {}
        for name, (src, key, field) in MECHANISMS.items():
            if not field:
                continue
            if src == "event":
                pre = key + ":"
                out[name] = {k[len(pre):]: n for k, n in sorted(self.events.items()) if k.startswith(pre)}
            else:
                out[name] = {k[len(key):]: n for k, n in sorted(stats.items()) if k.startswith(key)}
        return out

    def _stats(self) -> Counter:
        seen = dict(self.seen)
        for a in list(self.w.agents.values()) + list(self.w.dead.values()):
            seen[a.id] = a
        c: Counter = Counter()
        for a in seen.values():
            c.update(a.stats)
        return c

    def report(self) -> Dict[str, Any]:
        fired = self.fired()
        streaks = Counter(self.streaks)
        for f in self._fail.values():
            if f[1]:
                streaks[f[1]] += 1
        return {"preventable": sum(1 for s in self.starved if s["preventable"]),
                "stuck": len({s["id"] for s in self.stuck}), "stuck_episodes": len(self.stuck),
                "fired": fired, "fired_by": self.breakdown(),
                "never_fired": [k for k, n in fired.items() if n == 0],
                "fail_streaks": {str(k): streaks[k] for k in sorted(streaks)}}

    def autopsy_text(self, examples: int = 12) -> str:
        L = []
        for s in self.starved:
            tag = (f"PREVENTABLE: {s['store']['food']} food in {s['store']['id']} {s['store']['dist']} tiles away "
                   f"on its land") if s["preventable"] else "no food in a store on its land within 30 tiles"
            L.append(f"=== {s['text']} (tick {s['tick']}, day {s['day']}) at {tuple(s['at'])}: {tag}")
            for e in s["buffer"]:
                st = e["store"]
                where = "none" if st is None else (f"{st['id']} d{st['dist']} food{st['food']} land{int(st['same_land'])}"
                                                    f"{' UNREACH' if st['unreachable'] else ''}")
                L.append(f"    t{e['tick']} h{e['hunger']} at{tuple(e['at'])} goal={e['goal']!r} step={e['step']}"
                         f"{' R' if e['reflex'] else ''} result={e['result']!r} held_food={e['food_held']} store={where}")
        if self.stuck:
            L.append(f"=== stuck: {len(self.stuck)} episodes (the same goal replanned with a failing first step more "
                     f"than {STUCK_AFTER} times in a row)")
            for s in self.stuck[:examples]:
                L.append(f"    day {s['day']} t{s['tick']} {s['name']}: {s['goal']!r} x{s['times']}, {s['failure']}")
        return "\n".join(L)
