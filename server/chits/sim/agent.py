"""A Chit: body, needs, knowledge, memory, relationships."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .items import BASE, DESIGNS, ITEMS, STARTING_DESIGNS, STARTING_RECIPES

TICKS_PER_DAY = 240
BASE_CAPACITY = 12
MEMORY_CAP = 60
LESSON_CAP = 6
JOBS = ("farmer", "builder", "crafter", "gatherer", "fisher", "scholar", "explorer", "guard")

_SYL_A = ["pi", "mo", "ta", "bi", "ru", "ke", "lo", "za", "fi", "nu", "do", "ve", "sa", "yo", "mi", "ga", "pe", "wu", "ri", "ko"]
_SYL_B = ["p", "x", "n", "b", "ra", "lo", "mi", "sh", "tt", "ck", "ndo", "va", "zz", "ri", "ble", "po", "ki", "m", "l", "ssa"]


def make_name(rng: random.Random, taken: set) -> str:
    for _ in range(200):
        n = rng.choice(_SYL_A) + rng.choice(_SYL_B)
        if rng.random() < 0.25:
            n += rng.choice(["o", "a", "i", "y"])
        n = n.capitalize()
        if n not in taken and 3 <= len(n) <= 7:
            return n
    return f"Chit{len(taken)}"


TRAITS = ("curiosity", "sociability", "diligence", "caution", "generosity")

TRAIT_WORDS = {
    "curiosity": ("incurious", "curious"),
    "sociability": ("solitary", "chatty"),
    "diligence": ("easy-going", "hard-working"),
    "caution": ("bold", "careful"),
    "generosity": ("possessive", "generous"),
}

DEAD_MEMORIES, DEAD_BONDS, DEAD_LESSONS = 12, 5, 5  # what a dead chit's record keeps (Agent.obituary)


@dataclass
class Memory:
    tick: int
    text: str
    importance: int = 1  # 1..5
    kind: str = "event"
    id: int = 0  # per chit, increasing: lessons cite these

    def to_dict(self) -> Dict[str, Any]:
        return {"tick": self.tick, "text": self.text, "importance": self.importance, "kind": self.kind, "id": self.id}


# how something was learned -> what the chit can honestly claim about it (F7)
KNOW_STATUS = {"discovered": "worked", "insight": "worked", "built": "worked", "instinct": "worked",
               "taught": "told", "read": "told", "observed": "seen", "inspected": "seen"}


@dataclass
class Agent:
    id: str
    name: str
    x: int
    y: int
    hue: int
    traits: Dict[str, float]
    born: int = 0
    generation: int = 0
    parents: Tuple[str, ...] = ()
    lifespan: int = TICKS_PER_DAY * 50

    hunger: float = 85.0  # 100 = full
    energy: float = 90.0
    warmth: float = 90.0
    health: float = 100.0
    mood: float = 60.0

    inventory: Dict[str, int] = field(default_factory=dict)
    tool_wear: Dict[str, int] = field(default_factory=dict)
    knows: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # "recipe:x"/"design:y" -> provenance
    familiar: set = field(default_factory=set)  # item keys handled
    failed_experiments: List[str] = field(default_factory=list)
    memories: List[Memory] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)
    skills: Dict[str, float] = field(default_factory=dict)
    affinity: Dict[str, float] = field(default_factory=dict)  # other agent id -> -100..100
    home: Optional[str] = None
    last_birth_tick: int = -10_000

    # cognition / action state
    brain: str = "instinct"  # brain id
    goal: str = ""
    thought: str = ""
    plan: List[Dict[str, Any]] = field(default_factory=list)
    plan_source: str = "instinct"
    plan_started: int = 0
    pending_plan: Optional[Dict[str, Any]] = None
    thinking: bool = False
    think_started: int = 0
    last_result: str = ""
    activity: str = "idle"
    emote: str = ""
    emote_until: int = 0
    say: str = ""
    say_until: int = 0
    path: List[Tuple[int, int]] = field(default_factory=list)
    move_acc: float = 0.0
    work_acc: float = 0.0
    alive: bool = True
    died: int = -1
    cause_of_death: str = ""
    stats: Dict[str, int] = field(default_factory=dict)
    last_reflect_day: int = -1
    decisions: int = 0
    # F2: an observation revision (bumped when the chit's situation meaningfully changes), a lasting
    # objective separate from the current plan, and the id of the model plan being followed
    rev: int = 0
    objective: str = ""
    # the last time someone spoke to this chit directly: {"id", "name", "text", "tick"} until it answers
    spoken_to: Dict[str, Any] = field(default_factory=dict)
    # beliefs this chit has actually met: preached to it, or shown by a shrine it prayed at
    met_beliefs: List[str] = field(default_factory=list)
    # reflex -> tick until which it stays quiet: it just found nowhere to go, so let the chit's own plan run
    reflex_rest: Dict[str, int] = field(default_factory=dict)
    rev_why: str = ""  # what last made a pending plan out of date (shown in the decision log)
    last_choice: Dict[str, Any] = field(default_factory=dict)  # choose/cascade: the options it weighed, and its pick
    objective_since: int = -1
    plan_id: str = ""
    mem_seq: int = 0
    ambition: str = ""        # a life goal the chit chose itself (T06)
    ambition_since: int = -1
    belief: str = ""  # id of the belief this chit follows (T21), "" for none
    astronaut: bool = False  # rode the first rocket (T22)
    job: str = ""  # a specialisation mechanic (T24): inferred from practice ("auto") or declared by a model ("chosen")
    job_source: str = ""
    origin: str = ""  # the world this chit sailed from (T30); "" for natives
    homeland: str = ""  # where it was born, once it has been to sea (T34)
    voyage_intent: str = ""  # why it sailed: raid | trade | explore | settle
    voyage_home: str = ""  # the home it sailed from, kept for when it comes back (a trader's round trip)
    home_id: str = ""  # its id in its homeland, kept at sea (a clash abroad may rename it)
    deeds: List[str] = field(default_factory=list)  # elections won and laws decreed, for the hall of ancestors (sim/hall.py)
    lesson_sources: Dict[str, List[int]] = field(default_factory=dict)
    want: Dict[str, Any] = field(default_factory=dict)  # one current wish (sim/wants.py): {"kind", "key", "text", ...}
    renown: float = 0.0  # standing in the village: discoveries, project work, teaching, wishes come true

    # ---- derived ----
    def age(self, tick: int) -> float:
        return (tick - self.born) / TICKS_PER_DAY

    def is_child(self, tick: int) -> bool:
        return self.age(tick) < 3.0

    # the world's catalogue (T20), set by the world whenever it creates, restores or receives this chit; not saved
    catalog = None

    def _item(self, k: str):
        return (self.catalog or BASE).item(k)

    def capacity(self) -> int:
        cap = BASE_CAPACITY
        bonus = [it.carry_bonus for k in self.inventory if self.inventory[k] > 0 and (it := self._item(k)) and it.carry_bonus]
        return cap + sum(sorted(bonus, reverse=True)[:2])

    def load(self) -> int:
        return sum(it.weight * n for k, n in self.inventory.items() if (it := self._item(k)))

    def free_space(self) -> int:
        return self.capacity() - self.load()

    def has(self, item: str, n: int = 1) -> bool:
        return self.inventory.get(item, 0) >= n

    def add(self, item: str, n: int = 1) -> int:
        """Add up to n items, respecting capacity. Returns how many were added."""
        it = self._item(item)
        w = it.weight if it else 1
        can = max(0, min(n, self.free_space() // max(1, w)))
        if can:
            self.inventory[item] = self.inventory.get(item, 0) + can
            self.familiar.add(item)
        return can

    def remove(self, item: str, n: int = 1) -> int:
        have = self.inventory.get(item, 0)
        take = min(have, n)
        if take:
            if have - take <= 0:
                self.inventory.pop(item, None)
            else:
                self.inventory[item] = have - take
        return take

    def best_tool(self, cls: str) -> Optional[str]:
        best = None
        for k, n in self.inventory.items():
            it = self._item(k)
            if n > 0 and it and it.tool == cls and (best is None or it.tool_power > self._item(best).tool_power):
                best = k
        return best

    def knows_recipe(self, key: str) -> bool:
        return f"recipe:{key}" in self.knows

    def knows_design(self, key: str) -> bool:
        return f"design:{key}" in self.knows

    def bump_rev(self, why: str = "") -> None:
        """The chit's situation changed enough that a plan its model is still writing is out of date."""
        self.rev += 1
        self.rev_why = why

    def learn(self, knowledge: str, how: str, tick: int, source: Optional[str] = None) -> bool:
        if knowledge in self.knows:
            return False
        self.knows[knowledge] = {"how": how, "tick": tick, "from": source, "status": KNOW_STATUS.get(how, "told")}
        if self.knows[knowledge]["status"] == "worked":
            self.knows[knowledge]["worked_tick"] = tick
        return True

    def made_it_work(self, knowledge: str, tick: int) -> None:
        """First success turns 'told how'/'saw it done' into knowledge the chit has proven for itself."""
        k = self.knows.get(knowledge)
        if k and k.get("status") != "worked":
            k["status"] = "worked"
            k["worked_tick"] = tick

    def skill(self, name: str) -> float:
        return self.skills.get(name, 0.0)

    def practice(self, name: str, amount: float = 1.0) -> None:
        self.skills[name] = min(100.0, self.skills.get(name, 0.0) + amount * (0.6 + 0.8 * self.traits.get("diligence", 0.5)))

    def skill_speed(self, name: str) -> float:
        """Work multiplier from practice: 1.0 .. 1.8."""
        return 1.0 + 0.8 * (self.skill(name) / 100.0)

    def remember(self, tick: int, text: str, importance: int = 1, kind: str = "event") -> None:
        if self.memories and self.memories[-1].text == text:
            return
        self.mem_seq += 1
        self.memories.append(Memory(tick, text, importance, kind, self.mem_seq))
        if len(self.memories) > MEMORY_CAP:
            # forget the least important of the oldest half
            half = self.memories[: MEMORY_CAP // 2]
            victim = min(range(len(half)), key=lambda i: (half[i].importance, half[i].tick))
            self.memories.pop(victim)

    def recall(self, n: int = 8, keywords: Optional[List[str]] = None, now: int = 0) -> List[Memory]:
        if not self.memories:
            return []
        kws = [k.lower() for k in (keywords or []) if k]

        def score(m: Memory) -> float:
            recency = 1.0 / (1.0 + (now - m.tick) / 120.0)
            rel = sum(1 for k in kws if k in m.text.lower()) * 0.6
            return m.importance * 0.5 + recency * 2.0 + rel

        best = sorted(self.memories, key=score, reverse=True)[:n]
        return sorted(best, key=lambda m: m.tick)

    def bump(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def like(self, other_id: str, delta: float) -> None:
        self.affinity[other_id] = max(-100.0, min(100.0, self.affinity.get(other_id, 0.0) + delta))

    def set_emote(self, e: str, tick: int, dur: int = 20) -> None:
        self.emote = e
        self.emote_until = tick + dur

    def speak(self, text: str, tick: int, dur: int = 40) -> None:
        self.say = text[:140]
        self.say_until = tick + dur

    def personality(self) -> str:
        words = []
        for t in TRAITS:
            v = self.traits.get(t, 0.5)
            lo, hi = TRAIT_WORDS[t]
            if v >= 0.65:
                words.append(hi)
            elif v <= 0.35:
                words.append(lo)
        return ", ".join(words) if words else "even-tempered"

    def obituary(self) -> None:
        """What a dead chit keeps: who it was, what it knew and did, its closest bonds, its last lessons and
        memories. Everything else (the whole memory log, whom it liked, old plans and choices) was 70% of a save
        (7.6 of 10.8 MB for 497 dead chits), written every checkpoint, and nothing reads it after death."""
        self.memories = self.memories[-DEAD_MEMORIES:]
        self.affinity = dict(sorted(self.affinity.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:DEAD_BONDS])
        self.lessons = self.lessons[-DEAD_LESSONS:]
        kept = {m.id for m in self.memories}
        self.lesson_sources = {k: [i for i in v if i in kept] for k, v in self.lesson_sources.items() if k in self.lessons}
        self.failed_experiments, self.plan, self.path, self.pending_plan = [], [], [], None
        self.last_choice, self.spoken_to, self.reflex_rest, self.tool_wear = {}, {}, {}, {}

    # ---- serialization ----
    def to_dict(self) -> Dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["familiar"] = sorted(self.familiar)
        d["memories"] = [m.to_dict() for m in self.memories]
        d["path"] = [list(p) for p in self.path]
        d["parents"] = list(self.parents)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Agent":
        d = dict(d)
        d["familiar"] = set(d.get("familiar") or [])
        d["memories"] = [Memory(**m) for m in d.get("memories") or []]
        d["path"] = [tuple(p) for p in d.get("path") or []]
        d["parents"] = tuple(d.get("parents") or ())
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        a = cls(**known)
        for k in a.knows.values():  # snapshots from before knowledge had a status
            if "status" not in k:
                k["status"] = KNOW_STATUS.get(k.get("how", ""), "told")
            if k["status"] == "worked" and k.get("worked_tick") is None and KNOW_STATUS.get(k.get("how", "")) == "worked":
                k["worked_tick"] = k.get("tick", 0)  # (proven when learned: instinct, discovery, building; a told
                # thing marked worked with no tick stays unbacked, and the InvariantMonitor says so)
        if a.memories and not a.mem_seq:
            for i, m in enumerate(a.memories, 1):
                m.id = m.id or i
            a.mem_seq = max(m.id for m in a.memories)
        return a


def new_agent(rng: random.Random, aid: str, name: str, x: int, y: int, tick: int, *, spread: float = 0.12,
              base_traits: Optional[Dict[str, float]] = None, generation: int = 0, parents: Tuple[str, ...] = (),
              age_days: float = 8.0) -> Agent:
    traits = {}
    for t in TRAITS:
        base = (base_traits or {}).get(t, 0.5)
        traits[t] = round(max(0.0, min(1.0, base + rng.uniform(-spread, spread) * 2)), 2)
    a = Agent(
        id=aid, name=name, x=x, y=y, hue=rng.randint(0, 359), traits=traits,
        born=tick - int(age_days * TICKS_PER_DAY), generation=generation, parents=parents,
        lifespan=int(TICKS_PER_DAY * rng.uniform(45, 70)),
    )
    for key in [f"design:{d}" for d in STARTING_DESIGNS] + [f"recipe:{r}" for r in STARTING_RECIPES]:
        # (as learn() records instinct: proven, from birth; these had no status until a reload filled it in, then
        # "worked" with no tick, which the InvariantMonitor flags as a claim nothing backs)
        a.knows[key] = {"how": "instinct", "tick": tick, "from": None, "status": "worked", "worked_tick": tick}
    return a


def design_prereqs_met(agent: Agent, key: str) -> bool:
    d = DESIGNS[key]
    for kind, k in d.prereqs:
        if kind == "item" and k not in agent.familiar:
            return False
        if kind == "recipe" and not agent.knows_recipe(k):
            return False
        if kind == "design" and not agent.knows_design(k):
            return False
        if kind == "belief" and not agent.belief:
            return False
    return True
