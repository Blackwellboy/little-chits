"""Authoritative world state and the per-tick simulation loop.

Brains only ever *propose* plans (lists of steps). The world validates and
executes each step over many ticks via ``actions.advance``.
"""

from __future__ import annotations

import collections

import heapq
import math
import random
import time
import uuid
import zlib
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from . import terrain as T
from .agent import TICKS_PER_DAY, Agent, design_prereqs_met, make_name, new_agent
from .items import DESIGNS, ITEMS, RECIPES, STORES, Catalog, Item, Recipe, base_value, item_name, normalize_item
from . import artifacts as ART  # registers the artifacts as items (T28)
from . import animals as ANIMALS
from . import projects as PROJECTS  # village projects, research and wants (their shared state: world.civic)
from . import buildings as BLD

SEASONS = ("spring", "summer", "autumn", "winter")
DAYS_PER_SEASON = 3
SNAPSHOT_SCHEMA = 2  # bump when the saved shape changes, and add a step to migrate_snapshot
RNG_SCHEME = 2  # named domains; the legacy .rng property is weather-damage only (F18)


def _build() -> str:
    try:
        import subprocess
        from pathlib import Path

        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, capture_output=True,
                              text=True, timeout=3).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


BUILD = _build()


def migrate_snapshot(d: Dict[str, Any]) -> Dict[str, Any]:
    """Bring an old snapshot up to SNAPSHOT_SCHEMA. Refuses snapshots from a newer build."""
    d = dict(d)
    v = d.get("schema") or 1
    if v > SNAPSHOT_SCHEMA:
        raise ValueError(f"snapshot schema {v} is newer than this build ({SNAPSHOT_SCHEMA})")
    if v < 2:  # schema 1 had no identity: give it one
        d["uuid"] = d.get("uuid") or uuid.uuid4().hex
        d["epoch"] = d.get("epoch") or uuid.uuid4().hex
        d["epochs"] = d.get("epochs") or [{"epoch": d["epoch"], "parent": None, "from_tick": d.get("tick", 0),
                                          "created": time.time()}]
        d["schema"] = 2
    return d


POP_CAP = 60  # chits on a small island (the plan's invariants hold it to 60)
POP_CAP_BIG = 90  # ...and on an island of 256 or more: a 512 island held one village of 60 and its daughter villages died out
RUIN_DAYS = 6  # an unrepaired ruin crumbles away, freeing the land
ASHES_DAYS = 3  # a campfire left cold this long is gone (World A had 200 cold stone rings; they looked like graves)

# The long ladder (T22): each era begins with the first time this world knows or builds its key.
# An authored progression: chits still discover every step themselves, by experiment and invention.
ERAS: List[Tuple[str, Optional[str]]] = [
    ("Wanderers", None), ("Firekeepers", "design:campfire"), ("Toolmakers", "recipe:stone_axe"),
    ("Farmers", "design:farm"), ("Potters", "recipe:pot"), ("Scribes", "recipe:clay_tablet"),
    ("Copper Age", "recipe:copper"), ("Iron Age", "recipe:iron"), ("Machine Age", "recipe:engine"),
    ("Electric Age", "recipe:dynamo"), ("Space Age", "design:launch_pad"),
]

# Elections (T26): the winner needs the votes of at least this share of the adults
CHIEF_SUPPORT = 0.2
# Beliefs (T21): the first few may be founded freely; after that, a new one needs 2 quiet days since the last.
BELIEFS_BEFORE_BRAKE = 3
_STOP = {"about", "after", "again", "also", "because", "been", "being", "does", "each", "even", "every", "from",
         "have", "into", "just", "like", "more", "most", "much", "must", "only", "other", "over", "rather", "same",
         "should", "some", "such", "than", "that", "their", "them", "then", "there", "these", "they", "thing", "this",
         "those", "through", "under", "until", "very", "what", "when", "where", "which", "while", "will", "with",
         "without", "would", "your", "is", "not"}


def _content_words(text: str) -> Set[str]:
    words = "".join(ch.lower() if ch.isalpha() else " " for ch in str(text)).split()
    return {w.rstrip("s") for w in words if len(w) >= 4 and w not in _STOP}


# World capability flags: the only difference between the twin worlds.
CULTURE_FLAGS = {
    "direct": {"say": True, "teach": True, "write": True},
    "stigmergy": {"say": False, "teach": False, "write": False},
}


BOND_TO_BREED = 20  # how close two chits must be to have a child (was 25 when parents could pair with their children)
SITE_IDLE_DAYS = 10  # an unfinished site nobody has touched for this long is abandoned, even if begun


@dataclass
class Structure:
    id: str
    design: str
    x: int
    y: int
    w: int
    h: int
    founder: str
    created: int
    complete: bool = False
    needs: Dict[str, int] = field(default_factory=dict)
    work_done: float = 0.0
    work_total: float = 1.0
    builders: Dict[str, float] = field(default_factory=dict)  # agent id -> contribution
    completed: int = -1
    durability: float = 100.0
    fuel: float = 0.0
    storage: Dict[str, int] = field(default_factory=dict)
    planted: bool = False
    growth: float = 0.0
    shelf: List[str] = field(default_factory=list)  # tablet ids
    name: str = ""
    ruined_at: int = -1  # tick it fell into ruin; ruins crumble away after RUIN_DAYS
    out_since: int = -1  # a campfire: tick it burned out; cold ones are cleared away after ASHES_DAYS
    belief: str = ""  # a shrine's belief id (T21)
    last_work: int = -1  # last tick anyone delivered to or worked on this site
    worked_until: int = -1  # a station someone is working a shift at (smoke, sparks) until this tick
    produced: Dict[str, int] = field(default_factory=dict)  # item -> how many this station has made in shifts
    upgrade: Dict[str, Any] = field(default_factory=dict)  # a home being rebuilt bigger (buildings.do_upgrade)

    @property
    def ruined(self) -> bool:
        return self.complete and self.durability <= 0

    @property
    def functional(self) -> bool:
        return self.complete and self.durability > 0

    @property
    def lit(self) -> bool:
        return self.functional and self.design == "campfire" and self.fuel > 0

    def cells(self) -> Iterable[Tuple[int, int]]:
        for dy in range(self.h):
            for dx in range(self.w):
                yield self.x + dx, self.y + dy

    def center(self) -> Tuple[float, float]:
        return self.x + (self.w - 1) / 2, self.y + (self.h - 1) / 2

    def dist(self, x: int, y: int) -> int:
        dx = max(self.x - x, 0, x - (self.x + self.w - 1))
        dy = max(self.y - y, 0, y - (self.y + self.h - 1))
        return max(dx, dy)

    def stations(self) -> Set[str]:
        if not self.functional:
            return set()
        if self.design == "campfire":
            return {"fire"} if self.fuel > 0 else set()
        if self.design == "kiln":
            return {"kiln", "fire"}
        st = DESIGNS[self.design].station
        return {st} if st else set()

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Structure":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Tablet:
    id: str
    knowledge: str
    author: str
    author_name: str
    tick: int
    x: int
    y: int
    in_structure: Optional[str] = None
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class Event:
    seq: int
    tick: int
    kind: str
    text: str
    importance: int = 1
    actor: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class World:
    def __init__(self, world_id: str, name: str, seed: int, culture: str = "direct", size: int = 128,
                 n_agents: int = 18, label: str = ""):
        self.id = world_id
        self.name = name
        self.label = label or name
        self.seed = seed
        self.culture = culture
        self.flags = dict(CULTURE_FLAGS[culture])
        self.w = self.h = size
        self.tick = 0
        self._rngs: Dict[str, random.Random] = {}
        self.terrain_version = T.TERRAIN_VERSION
        self.tiles, self.res_kind, self.res_amt = T.generate(seed, size, size, self.terrain_version)
        self.traffic = [0.0] * (size * size)
        self.roads: Set[int] = set()
        self.tunnels: Dict[int, str] = {}  # rock a mine dug out (tile -> mine id): walkable, drawn as a road
        self.agents: Dict[str, Agent] = {}
        self.dead: Dict[str, Agent] = {}
        self.structures: Dict[str, Structure] = {}
        self.tablets: Dict[str, Tablet] = {}
        self.events: deque = deque(maxlen=4000)  # the RECENT window (UI, "what just happened"): never a whole-run total
        # lifetime counts of every event kind (and kind:design / kind:item / kind:recipe / kind:cause), kept as events
        # happen and saved with the world: whole-run totals come from here, never from the window (audit F6)
        self.tallies: Counter = Counter()
        self.tallies_since = 0  # the tick counting began (a save from before tallies: its oldest remembered event)
        self.seq = 0
        self.first: Dict[str, Dict[str, Any]] = {}  # knowledge/design -> first event info
        self.counters: Dict[str, int] = {"agent": 0, "struct": 0, "tablet": 0}
        self.dirty_res: Set[int] = set()
        self.dirty_struct: Set[str] = set()
        self.removed_struct: Set[str] = set()
        self.dirty_roads: Set[int] = set()
        self.listeners: List[Callable[[Event], None]] = []
        self.history: List[Dict[str, Any]] = []  # daily stats
        # durable identity: "A"/"B" is only a display slot; uuid names this world, epoch names its timeline
        self.settlements: Dict[str, Dict[str, Any]] = {}  # inferred villages: id -> name, founded, milestones (T09)
        self.weather = "clear"  # clear | rain | storm | drought | snow (T08)
        self.weather_until = 0
        self.signs: Dict[str, Dict[str, Any]] = {}  # marks in the land (T07)
        self.signs_dirty = False
        self.culture_names: Dict[str, str] = {}  # knowledge key -> this world's own name for it (T05)
        self.catalog = Catalog()  # this world's items: its own inventions, then the shared base physics (T20)
        self.inventions: Dict[str, Dict[str, Any]] = {}
        self.beliefs: Dict[str, Dict[str, Any]] = {}  # what chits believe (T21): content from minds, never magic
        self.era_index = 0
        self.trades: List[Dict[str, Any]] = []  # recent barter (T25)
        self.currency = ""  # whatever everyone ends up trading through; never declared
        self.leader = ""  # an authored institution (T26): an elected chief (A) or a recognised elder (B)
        self.leader_since = -1
        self.laws: List[Dict[str, Any]] = []
        self.challenge: Dict[str, Any] = {}  # the storyteller's current challenge (sim/storyteller.py)
        self.cold_until = -1  # a hard winter: colder until this tick
        self.militia_n = 0  # guard count at the last "militia" event (T27)
        self.ground: Dict[str, Dict[str, int]] = {}  # "x,y" -> items lying there, plus "_t" (T28)
        self.artifact_uses: Dict[str, int] = {}  # artifact teaching limits: slot -> day last used
        self.contact = False  # boats may cross to the other island (T30); set by the runtime
        self.outbox: List[Dict[str, Any]] = []  # chits at sea, on their way to the other world
        self.animals: Dict[str, Dict[str, Any]] = {}  # deer, sheep and wolves (T31)
        self.relations: Dict[str, Dict[str, Any]] = {}  # other world id -> how we stand with them (T34)
        self.incident_sink: Optional[Callable[["World", str, str], None]] = None  # set by the runtime
        self._wolf_nights: Set[str] = set()
        self.deliveries: deque = deque(maxlen=3000)  # who passed what to whom, through which channel (F7)
        self.uuid = uuid.uuid4().hex
        self.epoch = uuid.uuid4().hex
        self.epochs: List[Dict[str, Any]] = [{"epoch": self.epoch, "parent": None, "from_tick": 0, "created": time.time()}]
        self.occupied: Dict[int, str] = {}  # tile -> structure id
        self.spawn = T.find_spawn(self.tiles, self.res_kind, size, size, seed)
        self._zone_tick: Optional[int] = None
        self.rebuild_block()
        self._spawn_agents(n_agents)
        ANIMALS.initial(self)
        PROJECTS.init(self)

    # ------------------------------------------------------------------ setup
    # ------------------------------------------------------------------ randomness (F6)
    def rng_for(self, name: str) -> random.Random:
        """Independent deterministic streams, so an extra roll in one system (a fight, an experiment) never
        shifts another (the weather, regrowth, births). "misc" keeps the original seeding for old code."""
        r = self._rngs.get(name)
        if r is None:
            r = random.Random(self.seed * 31 + 7 if name == "misc" else zlib.crc32(f"{self.seed}:{name}".encode()))
            self._rngs[name] = r
        return r

    @property
    def rng(self) -> random.Random:
        """Legacy compatibility for the frozen weather test. Production code must use rng_for(domain);
        this stream is reserved for shared weather damage so culture-specific draws cannot move it."""
        return self.rng_for("weather_damage")

    def _new_id(self, kind: str) -> str:
        self.counters[kind] = self.counters.get(kind, 0) + 1
        return f"{kind[0]}{self.counters[kind]}"

    def _spawn_agents(self, n: int) -> None:
        rng = random.Random(self.seed)  # same chits in twin worlds
        taken: Set[str] = set()
        sx, sy = self.spawn
        for i in range(n):
            for _ in range(50):
                x = sx + rng.randint(-5, 5)
                y = sy + rng.randint(-5, 5)
                if self.passable(x, y):
                    break
            name = make_name(rng, taken)
            taken.add(name)
            a = new_agent(rng, self._new_id("agent"), name, x, y, 0, age_days=rng.uniform(4, 14))
            a.catalog = self.catalog
            self.agents[a.id] = a

    # ------------------------------------------------------------------ this world's catalogue (T20)
    def item(self, key: str) -> Optional[Item]:
        return self.catalog.item(key)

    def recipe(self, key: str) -> Optional[Recipe]:
        return self.catalog.recipe(key)

    def item_name(self, key: str) -> str:
        return item_name(key, self.catalog)

    def invention_by_name(self, text: Any) -> Optional[str]:
        """An invention of this world, by key or by its local name (case-insensitive)."""
        if not text:
            return None
        s = str(text).strip()
        if s in self.inventions:
            return s
        low = s.lower()
        for p in ("a ", "an ", "the "):
            if low.startswith(p) and low[len(p):]:
                low = low[len(p):]
        for k, inv in self.inventions.items():
            if inv["name"].lower() == low:
                return k
        return None

    def norm_item(self, raw: Any) -> Optional[str]:
        """Free text -> an item key: this world's inventions, then its local names for things ("stoneaxe"
        for sharp stone, shown to chits in their prompts) when it isn't a base item's name ("Stone" stays stone)."""
        return self.invention_by_name(raw) or normalize_item(raw) or self.culture_item(raw)

    def culture_item(self, raw: Any) -> Optional[str]:
        low = " ".join(str(raw or "").strip().lower().split())
        if not low:
            return None
        for kk, nm in getattr(self, "culture_names", {}).items():
            if kk.startswith("recipe:") and " ".join(str(nm).lower().split()) == low:
                return kk[7:]
        return None

    # ------------------------------------------------------------------ contact between islands (T30)
    def depart(self, a: Agent) -> None:
        """A chit sails away. It leaves this world (not a death) and is at sea for half a day."""
        self.agents.pop(a.id, None)
        bel = self.beliefs.get(a.belief)
        if bel and a.id in bel["followers"]:
            bel["followers"].remove(a.id)
        if a.id == self.leader:
            self.leader = ""
        for s in self.structures.values():
            s.builders.pop(a.id, None)
        if not a.homeland:
            a.homeland = self.id
        if not a.origin:  # sailing from its own land: its home waits for it
            a.voyage_home, a.home_id = a.home or "", a.id
        carried = {k: self.inventions[k] for k in self.inventions
                   if a.inventory.get(k) or f"recipe:{k}" in a.knows}
        self.outbox.append({"agent": a.to_dict(), "from": self.id, "arrive_tick": self.tick + BLD.voyage_ticks(self),
                            "inventions": carried})
        self.emit("voyage", f"{a.name} sailed away over the sea", 5, a.id, a.x, a.y)

    def arrive(self, agent_dict: Dict[str, Any], from_world_id: str, from_name: str = "",
               inventions: Optional[Dict[str, Any]] = None) -> Agent:
        from .invent import register_invention

        for key, inv in (inventions or {}).items():  # foreign inventions travel with the chit
            if self.catalog.item(key) is None:
                register_invention(self, key, inv["name"], inv["inputs"], tuple(inv.get("props") or ()), inv.get("effect") or {})
        a = Agent.from_dict(agent_dict)
        home_again = getattr(a, "homeland", "") == self.id
        if home_again and a.home_id and a.home_id not in self.agents and a.home_id not in self.dead:
            a.id = a.home_id  # home again under the id its kin know it by (a clash abroad renamed it)
        while a.id in self.agents or a.id in self.dead:
            a.id += "-x"
        coast = [(x, y) for y in range(self.h) for x in range(self.w) if self.coastal(x, y) and self.tile_free(x, y)]
        if coast:
            a.x, a.y = self.rng_for("contact").choice(coast)
        a.origin = "" if home_again else from_world_id
        a.home = None
        back = self.structures.get(a.voyage_home or "") if home_again else None
        if back is not None and back.functional:
            a.home = back.id  # a trader comes back to the home it sailed from
        if home_again and a.voyage_intent == "home":
            self._beach_boat(a)
        a.plan, a.pending_plan, a.thinking, a.path = [], None, False, []
        a.belief = ""  # a belief id means nothing here; the memory of it stays
        a.catalog = self.catalog
        a.remember(self.tick, "I crossed the sea and reached a new land", 5, "voyage")
        self.agents[a.id] = a
        if home_again:
            self.emit("arrival", f"{a.name} came home by boat from {from_name or 'across the sea'}!", 4, a.id, a.x, a.y,
                      origin=from_world_id, home=True)
        else:
            self.emit("arrival", f"A stranger named {a.name} arrived by boat from {from_name or 'across the sea'}!", 5,
                      a.id, a.x, a.y, origin=from_world_id, intent=a.voyage_intent)
        return a

    def _beach_boat(self, a: Agent) -> Optional[Structure]:
        """A trader home again draws the boat it sailed in up on the shore where it landed: the village keeps it."""
        spot = self.find_site("boat", a.x, a.y, 7, reach=(a.x, a.y))
        if spot is None:
            return None
        b = self.place_site("boat", spot[0], spot[1], a)
        b.complete, b.completed, b.needs, b.work_done = True, self.tick, {}, b.work_total
        return b

    WANDER_BELOW = 8  # a play world this small draws a wanderer every WANDER_EVERY_DAYS
    WANDER_EVERY_DAYS = 2

    def welcome_wanderer(self) -> Optional[Agent]:
        """A young adult from the wilds finds a dwindling village and stays. Play games only (the runtime decides):
        World B aged out to 5 chits overnight, and an empty world is the end of the show for anyone watching."""
        if not self.agents or len(self.agents) >= self.WANDER_BELOW:
            return None
        rng = self.rng_for("wanderers")
        near = rng.choice(list(self.agents.values()))
        x, y = near.x, near.y
        for _ in range(60):
            nx, ny = near.x + rng.randint(-12, 12), near.y + rng.randint(-12, 12)
            if self.passable(nx, ny) and self.tile_free(nx, ny):
                x, y = nx, ny
                break
        taken = {o.name for o in list(self.agents.values()) + list(self.dead.values())}
        a = new_agent(rng, self._new_id("agent"), make_name(rng, taken), x, y, self.tick, age_days=rng.uniform(4, 10))
        a.catalog = self.catalog
        a.brain = near.brain
        a.remember(self.tick, f"I wandered out of the wilds and found {self.name}", 5, "voyage")
        self.agents[a.id] = a
        self.emit("arrival", f"A wanderer named {a.name} found the village and stayed", 4, a.id, a.x, a.y, wanderer=True)
        return a

    def relation(self, other_id: str) -> Dict[str, Any]:
        return self.relations.setdefault(other_id, {"hostility": 0.0, "trades": 0, "raids": 0, "gifts": 0, "met": False,
                                                    "state": "unknown"})

    def incident(self, a: Agent, b: Optional[Agent], kind: str) -> None:
        """A theft, fight, trade or gift involving a chit from the other island (T34)."""
        other = next((x.origin for x in (a, b) if x is not None and x.origin and x.origin != self.id), None)
        if other and self.incident_sink:
            self.incident_sink(self, other, kind)

    def tile_free(self, x: int, y: int) -> bool:
        return (y * self.w + x) not in self.occupied

    # ------------------------------------------------------------------ things on the ground (T28)
    def put_ground(self, x: int, y: int, key: str, n: int = 1) -> None:
        pile = self.ground.setdefault(f"{x},{y}", {"_t": self.tick})
        pile[key] = pile.get(key, 0) + n
        pile["_t"] = self.tick

    def piles_near(self, x: int, y: int, radius: int) -> List[Tuple[int, int, Dict[str, int]]]:
        out = []
        for tile, pile in self.ground.items():
            px, py = (int(v) for v in tile.split(","))
            if max(abs(px - x), abs(py - y)) <= radius and any(k != "_t" and n > 0 for k, n in pile.items()):
                out.append((px, py, pile))
        out.sort(key=lambda p: max(abs(p[0] - x), abs(p[1] - y)))
        return out

    def _expire_ground(self) -> None:
        for tile in list(self.ground):
            pile = self.ground[tile]
            items = {k: n for k, n in pile.items() if k != "_t" and n > 0}
            if not items:
                del self.ground[tile]
            elif self.tick - pile.get("_t", 0) > 5 * TICKS_PER_DAY and not any(ART.is_artifact(k) for k in items):
                del self.ground[tile]

    # ------------------------------------------------------------------ leaders and laws (T26)
    def choose_leader(self, reason: str = "") -> None:
        adults = [a for a in self.agents.values() if not a.is_child(self.tick)]
        if not adults:
            return
        if self.flags.get("say"):
            votes: Dict[str, int] = {}
            # Approval voting: each adult backs every adult it likes (affinity >= 10). With one vote for a
            # single favourite, votes scattered across neighbourhoods and no one could reach the support a
            # chief needs (1-4 votes of 18-44 in every election of today's games).
            for v in adults:
                for o in adults:
                    if o is not v and v.affinity.get(o.id, 0.0) >= 10:
                        votes[o.id] = votes.get(o.id, 0) + 1
            if not votes:
                return
            best = max(votes.items(), key=lambda kv: (kv[1], -self.agents[kv[0]].born))[0]
            # a chief needs real backing: "elected with 1 of 18 votes" happened when friendships were new or votes
            # scattered. Short of a fifth of the adults (and at least 2), there's no chief yet or the old one stays.
            if votes[best] < max(2, math.ceil(len(adults) * CHIEF_SUPPORT)):
                return
            if best != self.leader:
                if self.leader:
                    from .. import diag

                    diag.of(self).chief["leader changed"] += 1  # (a question to the old chief can't be answered)
                self.leader, self.leader_since = best, self.tick
                a = self.agents[best]
                self.emit("election", f"{a.name} was elected chief with {votes[best]} of {len(adults)} votes", 4, a.id,
                          a.x, a.y, votes=votes[best], voters=len(adults), reason=reason)
                from . import hall

                hall.deed(a, f"was elected chief with {votes[best]} of {len(adults)} votes on day {self.day + 1}")
        else:
            score = {a.id: sum(o.affinity.get(a.id, 0.0) for o in adults if o is not a) for a in adults}
            best = max(score.items(), key=lambda kv: (kv[1], -self.agents[kv[0]].born))[0]
            if best != self.leader:
                self.leader, self.leader_since = best, self.tick
                a = self.agents[best]
                self.emit("elder", f"{a.name} is now looked to as the elder", 4, a.id, a.x, a.y, reason=reason)

    def decree(self, a: Agent, text: str) -> bool:
        if not self.flags.get("say") or a.id != self.leader:
            return False
        text = " ".join(str(text or "").split())[:120]
        if len(text) < 8:
            return False
        self.laws.append({"id": self._new_id("law"), "text": text, "by": a.id, "by_name": a.name, "tick": self.tick})
        from . import hall

        hall.deed(a, f'decreed: "{text[:160]}"')
        del self.laws[:-10]
        self.emit("law", f'Chief {a.name} decreed: "{text}"', 5, a.id, a.x, a.y, law=text)
        return True

    # ------------------------------------------------------------------ trade and money (T25)
    def value_for(self, a: Agent, key: str) -> float:
        it = self.item(key)
        v = base_value(key)
        if it and it.food > 0 and a.hunger < 50:
            v *= 2.5
        if it and it.tool and a.best_tool(it.tool) is None:
            v *= 2.0
        if a.inventory.get(key, 0) >= 10:
            v *= 0.5
        return v

    def near_market(self, x: int, y: int) -> bool:
        return any(s.functional for s in self.structures_near(x, y, 6, "market"))

    def accepts_trade(self, partner: Agent, trader: Agent, give: Dict[str, int], get: Dict[str, int]) -> bool:
        if partner.activity == "sleeping" or partner.affinity.get(trader.id, 0.0) < -20:
            return False
        threshold = 0.75 if self.near_market(partner.x, partner.y) else 0.9
        offered = sum(self.value_for(partner, k) * n for k, n in give.items())
        asked = sum(self.value_for(partner, k) * n for k, n in get.items())
        return offered >= threshold * asked

    def record_trade(self, a: Agent, b: Agent, give: Dict[str, int], get: Dict[str, int]) -> None:
        self.trades.append({"tick": self.tick, "a": a.id, "b": b.id, "give": dict(give), "get": dict(get)})
        del self.trades[:-500]

    def update_money(self) -> None:
        recent = [t for t in self.trades if self.tick - t["tick"] <= 3 * TICKS_PER_DAY]
        if len(recent) < 8:
            return
        count: Dict[str, int] = {}
        who: Dict[str, Set[str]] = {}
        for t in recent:
            for k in set(t["give"]) | set(t["get"]):
                count[k] = count.get(k, 0) + 1
                who.setdefault(k, set()).update((t["a"], t["b"]))
        ok = [(n, k) for k, n in count.items()
              if not ((it := self.item(k)) and it.food > 0) and n >= 0.4 * len(recent) and len(who[k]) >= 4]
        if not ok:
            return
        cur = max(ok)[1]
        if cur != self.currency:
            self.currency = cur
            self.emit("money", f"{self.item_name(cur)} has become money in {self.name}: most trades now go through it", 5,
                      item=cur)

    # ------------------------------------------------------------------ jobs (T24)
    SKILL_JOB = {"farming": "farmer", "building": "builder", "crafting": "crafter", "gathering": "gatherer"}

    def assign_jobs(self) -> None:
        for a in list(self.agents.values()):
            if a.is_child(self.tick) or a.job_source == "chosen":
                continue
            sk = sorted(((v, k) for k, v in a.skills.items() if k in self.SKILL_JOB), reverse=True)
            job = ""
            if sk and sk[0][0] >= 1.0 and (len(sk) < 2 or sk[0][0] >= 1.3 * sk[1][0]):
                job = self.SKILL_JOB[sk[0][1]]
            if job == "gatherer" and a.stats.get("fish", 0) >= 10:
                job = "fisher"
            if a.stats.get("read", 0) + a.stats.get("wrote", 0) + a.stats.get("studied", 0) >= 3:
                job = "scholar"
            if a.stats.get("guarded", 0) >= 3:
                job = "guard"
            self.set_job(a, job, "auto")

    def set_job(self, a: Agent, job: str, source: str) -> None:
        if job == a.job:
            a.job_source = source if job else a.job_source
            return
        first = bool(job) and not any(o.job == job for o in list(self.agents.values()) + list(self.dead.values()) if o is not a)
        a.job, a.job_source = job, source
        if not job:
            return
        if first:
            self.emit("job", f"{a.name} became the island's first {job}", 3, a.id, a.x, a.y, job=job, first=True)
        else:
            self.emit("job", f"{a.name} is now a {job}", 2, a.id, a.x, a.y, job=job)

    # ------------------------------------------------------------------ eras (T22)
    def era(self) -> Tuple[int, str]:
        best = 0
        for i, (_, key) in enumerate(ERAS):
            if key is None or key in self.first:
                best = i
        return best, ERAS[best][0]

    def update_era(self) -> None:
        i, name = self.era()
        if i > self.era_index:
            self.era_index = i
            self.emit("era", f"{self.name} enters the {name}", 5, era=name, index=i)

    # ------------------------------------------------------------------ beliefs (T21)
    def found_belief(self, a: Agent, name: Any, tenet: Any) -> Optional[str]:
        if a.belief:
            return None
        tenet = str(tenet or "").strip()
        if len(tenet) > 160:  # trim to the last clause, not mid-phrase
            from ..textcut import clause_cut
            tenet = clause_cut(tenet[:160])
        if len(tenet) < 8:
            return None
        nm = " ".join(str(name or "").replace("\n", " ").split()).strip(" \"'.,;:!?")[:40].strip()
        if not nm or not any(ch.isalpha() for ch in nm):
            nm = f"The Way of {a.name}"
        if any(b["name"].lower() == nm.lower() for b in self.beliefs.values()):
            return None
        twin = self.kindred_belief(tenet + " " + nm, min_shared=3, relative=0.5)
        if twin and self.convert(a, twin, "it said what they already felt"):
            return None  # mostly the same words as a faith that exists: that faith, not a copy of it
        recent = any(self.tick - b["tick"] < 2 * TICKS_PER_DAY for b in self.beliefs.values())
        if len(self.beliefs) >= BELIEFS_BEFORE_BRAKE and recent:
            # New faiths are rare. Once a few exist, a fresh conviction usually finds a home in one that says
            # much the same; otherwise the chit keeps it to itself for now.
            kin = self.kindred_belief(tenet + " " + nm, min_shared=2, among=self.known_beliefs(a))
            if kin and self.convert(a, kin, "it said what they already felt"):
                return None
            a.remember(self.tick, f'I felt a conviction ("{tenet}"), but kept it to myself for now', 2, "belief")
            return None
        bid = self._new_id("belief")
        self.beliefs[bid] = {"id": bid, "name": nm, "tenet": tenet, "founder": a.id, "founder_name": a.name,
                             "tick": self.tick, "followers": [a.id]}
        a.belief = bid
        a.remember(self.tick, f'I came to believe: "{tenet}" ({nm})', 5, "belief")
        self.emit("belief", f'{a.name} founded {nm}: "{tenet}"', 5, a.id, a.x, a.y, belief=bid, name=nm, tenet=tenet)
        self.check_insights(a)
        return bid

    def kindred_belief(self, text: str, min_shared: int = 1, relative: float = 0.0,
                       among: Optional[Iterable[str]] = None) -> Optional[str]:
        """The existing belief closest in spirit to `text` (shared meaningful words), ties to the one with more
        followers. It must share at least `min_shared` words, and at least `relative` of the smaller word set
        (so a long generic tenet doesn't match on "survival" and "fire"). `among` limits the candidates."""
        mine = _content_words(text)
        best, score = None, (0, 0)
        pool = self.beliefs if among is None else {b: self.beliefs[b] for b in among if b in self.beliefs}
        for bid, b in pool.items():
            theirs = _content_words(b["name"] + " " + b["tenet"])
            shared = len(mine & theirs)
            if shared < max(min_shared, relative * min(len(mine), len(theirs))):
                continue
            s = (shared, len(b["followers"]))
            if s > score:
                best, score = bid, s
        return best

    def known_beliefs(self, a: Agent) -> Set[str]:
        """The faiths this chit has met: preached to it, shown by a shrine it can see, or (where chits talk) held
        by a close friend nearby. The same set its reflection prompt lists."""
        ids = set(a.met_beliefs)
        ids |= {s.belief for s in self.structures_near(a.x, a.y, 30, "shrine") if s.functional and s.belief}
        if self.flags.get("say"):
            ids |= {o.belief for o in self.agents_near(a.x, a.y, 20, exclude=a.id) if o.belief and a.affinity.get(o.id, 0.0) >= 30}
        return ids

    def convert(self, a: Agent, belief_id: str, how: str) -> bool:
        b = self.beliefs.get(belief_id)
        if a.belief or not b:
            return False
        a.belief = belief_id
        if a.id not in b["followers"]:
            b["followers"].append(a.id)
        a.remember(self.tick, f'I came to believe in {b["name"]}: "{b["tenet"]}"', 4, "belief")
        self.emit("convert", f"{a.name} came to believe in {b['name']} ({how})", 3, a.id, a.x, a.y,
                  belief=belief_id, how=how)
        self.check_insights(a)
        return True

    def _belief_tick(self) -> None:
        """Every 10 ticks: co-believers warm to each other; a shrine of your own belief lifts your mood."""
        followers = [a for a in self.agents.values() if a.belief]
        if not followers:
            return
        shrines = [s for s in self.structures.values() if s.design == "shrine" and s.functional and s.belief]
        for i, a in enumerate(followers):
            for b in followers[i + 1:]:
                if b.belief == a.belief and max(abs(a.x - b.x), abs(a.y - b.y)) <= 3:
                    a.like(b.id, 0.5)
                    b.like(a.id, 0.5)
            if any(s.belief == a.belief and s.dist(a.x, a.y) <= 8 for s in shrines):
                a.mood = min(100.0, a.mood + 0.3)

    def invention_effect(self, a: Agent, kind: str) -> bool:
        return any(a.inventory.get(k, 0) > 0 and kind in inv.get("effect", {}) for k, inv in self.inventions.items())

    # ------------------------------------------------------------------ time
    @property
    def day(self) -> int:
        return self.tick // TICKS_PER_DAY

    @property
    def hour(self) -> float:
        return (self.tick % TICKS_PER_DAY) / TICKS_PER_DAY * 24.0

    @property
    def season(self) -> str:
        return SEASONS[(self.day // DAYS_PER_SEASON) % 4]

    @property
    def year(self) -> int:
        return self.day // (DAYS_PER_SEASON * 4) + 1

    @property
    def is_night(self) -> bool:
        h = self.hour
        return h < 5.5 or h >= 20.5

    def daylight(self) -> float:
        """0 (midnight) .. 1 (noon), smooth."""
        h = self.hour
        v = math.cos((h - 13.0) / 24.0 * 2 * math.pi)
        return max(0.0, min(1.0, 0.5 + 0.75 * v))

    def temperature(self) -> float:
        base = {"spring": 0.6, "summer": 0.95, "autumn": 0.5, "winter": 0.12}[self.season]
        storm = 0.15 if getattr(self, "weather", "clear") == "storm" else 0.0
        cold = 0.12 if self.tick < getattr(self, "cold_until", -1) and self.season in ("autumn", "winter") else 0.0
        return base - (0.3 if self.is_night else 0.0) + 0.1 * (self.daylight() - 0.5) - storm - cold

    # ------------------------------------------------------------------ weather (T08)
    WEATHER_TEXT = {"rain": "It is raining.", "storm": "A storm is raging.", "drought": "A drought parches the land.",
                    "snow": "Snow is falling."}

    def set_weather(self, kind: str, days: float = 1.0) -> None:
        if kind == self.weather:
            return
        self.weather = kind
        self.weather_until = self.tick + int(days * TICKS_PER_DAY)
        if kind == "storm":
            for s in self.structures.values():
                if s.design == "campfire" and s.fuel > 0:
                    s.fuel = 0.0
                    self.dirty_struct.add(s.id)
                if s.complete and DESIGNS[s.design].decay_per_day > 0 and self.rng.random() < 0.35:
                    s.durability = max(0.0, s.durability - 25)
                    if s.durability <= 0 and s.ruined_at < 0:
                        s.ruined_at = self.tick
                    self.dirty_struct.add(s.id)
            self.emit("storm", "A storm tears across the island", 4)
        elif kind == "drought":
            self.emit("drought", "A drought settles over the island: nothing grows", 3)
        elif kind == "rain":
            self.emit("rain", "Rain falls across the island", 1)
        elif kind == "snow":
            self.emit("snow", "Snow begins to fall", 1)

    def _roll_weather(self) -> None:
        r = self.rng_for("weather").random()
        season = self.season
        if season == "winter":
            kind = "snow" if r < 0.5 else "storm" if r < 0.6 else "clear"
        elif season == "autumn":
            kind = "storm" if r < 0.2 else "rain" if r < 0.45 else "clear"
        elif season == "summer":
            kind = "drought" if r < 0.15 else "rain" if r < 0.3 else "clear"
        else:
            kind = "rain" if r < 0.35 else "clear"
        if kind == "clear":
            self.weather, self.weather_until = "clear", self.tick
        else:
            self.set_weather(kind, 0.5 if kind == "storm" else 1.0)

    # ------------------------------------------------------------------ villages (T09)
    def update_settlements(self):
        from .settlements import detect

        found = detect(self)
        for s in found:
            rec = self.settlements.get(s.id)
            if rec is None:
                rec = self.settlements[s.id] = {"name": s.name, "founded": self.tick, "milestones": []}
                names = [self.agents[r].name for r in s.residents if r in self.agents][:3]
                if not names:
                    names = [a.name for a in (self.agents.get(b) for st in s.structures
                                              for b in self.structures[st].builders) if a][:3]
                    names = list(dict.fromkeys(names))[:3]
                self.emit("settlement", f"The village of {s.name} was founded by {_join_names(names) or 'unknown hands'}",
                          4, None, s.x, s.y, settlement=s.id, name=s.name)
            for m in (10, 20):
                if len(s.residents) >= m and m not in rec["milestones"]:
                    rec["milestones"].append(m)
                    self.emit("village_growth", f"{s.name} has grown to {len(s.residents)} chits", 3, None, s.x, s.y,
                              settlement=s.id, name=s.name, population=len(s.residents))
            from .settlements import RANKS

            best = rec.get("best_rank", "village")
            if RANKS.index(s.rank) > RANKS.index(best):  # a first: told once, and never again if it slips and recovers
                rec["best_rank"] = s.rank
                self.emit("town_rank", f"{s.name} has become a {s.rank}", 5, None, s.x, s.y, settlement=s.id,
                          name=s.name, rank=s.rank, population=len(s.residents))
            rec["rank"] = s.rank
        return found

    def settlement_of(self, a: Agent):
        if not a.home:
            return None
        from .settlements import detect

        for s in detect(self):
            if a.home in s.structures:
                return s
        return None

    def sheltered(self, a: Agent) -> bool:
        if self.in_home(a):
            return True
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                sid = self.occupied.get((a.y + dy) * self.w + (a.x + dx)) if self.inb(a.x + dx, a.y + dy) else None
                s = self.structures.get(sid) if sid else None
                if s and s.functional and s.design in BLD.HOMES:
                    return True
        if self.weather != "storm":
            for s in self.structures_near(a.x, a.y, 3, "campfire"):
                if s.lit and max(abs(s.x - a.x), abs(s.y - a.y)) <= 2:
                    return True
        return False

    def exposure(self, a: Agent) -> float:
        """Extra warmth lost per tick to the weather when out in it."""
        extra = {"storm": 0.35, "snow": 0.2, "rain": 0.05}.get(self.weather, 0.0)
        if not extra or self.sheltered(a):
            return 0.0
        return extra

    def clock(self) -> Dict[str, Any]:
        return {
            "tick": self.tick, "day": self.day + 1, "year": self.year, "season": self.season,
            "hour": round(self.hour, 2), "daylight": round(self.daylight(), 3), "night": self.is_night,
            "weather": getattr(self, "weather", "clear"),
            "day_of_season": self.day % DAYS_PER_SEASON + 1,
            "era": ERAS[getattr(self, "era_index", 0)][0],
        }

    # ------------------------------------------------------------------ geometry
    def inb(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def tile(self, x: int, y: int) -> int:
        return self.tiles[y * self.w + x]

    BLOCKING = ("workshop", "kiln", "furnace", "monument", "library")

    def rebuild_block(self) -> None:
        """Flat passability grid: terrain plus solid buildings. Rebuilt when buildings change."""
        blk = bytearray(0 if T.PASSABLE[t] else 1 for t in self.tiles)
        tunnels = getattr(self, "tunnels", {})
        for i in tunnels:
            blk[i] = 0  # a mine's tunnel through the rock
        for st in self.structures.values():
            if st.complete and st.design in self.BLOCKING:
                for cx, cy in st.cells():
                    blk[cy * self.w + cx] = 1
        self.block = blk
        base = [T.MOVE_COST[t] for t in self.tiles]
        for i in tunnels:
            base[i] = T.MOVE_COST[T.HILLS]
        BLD.lay_bridges(self, blk, base)  # a finished bridge is a walkable deck over the water
        self._base_cost = base

    def passable(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h and not self.block[y * self.w + x]

    def move_cost(self, x: int, y: int) -> float:
        i = y * self.w + x
        if i in self.roads:
            return 0.45
        c = self._base_cost[i]
        return c * 0.8 if self.traffic[i] > 30 else c

    def neighbors(self, x: int, y: int):
        for dx, dy, c in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                          (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            nx, ny = x + dx, y + dy
            if not self.passable(nx, ny):
                continue
            if dx and dy and not (self.passable(x + dx, y) and self.passable(x, y + dy)):
                continue
            yield nx, ny, c

    _NB = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))

    def _components(self) -> List[int]:
        """Connected passable land (4-way, which 8-way moves without corner cutting can't beat), relabelled
        whenever the block grid is rebuilt."""
        if getattr(self, "_comp_for", None) is self.block:
            return self._comp
        W, n, blk = self.w, self.w * self.h, self.block
        comp = [0] * n
        label = 0
        for i in range(n):
            if blk[i] or comp[i]:
                continue
            label += 1
            comp[i] = label
            stack = [i]
            while stack:
                j = stack.pop()
                x = j % W
                for k in (j - 1 if x else -1, j + 1 if x < W - 1 else -1, j - W, j + W):
                    if 0 <= k < n and not blk[k] and not comp[k]:
                        comp[k] = label
                        stack.append(k)
        self._comp, self._comp_for = comp, blk
        return comp

    def village_failed(self, a: Agent, radius: int = 30) -> "collections.Counter[str]":
        """Experiments that did nothing for the chits living around this one (it has seen or heard of them). Each chit
        only remembered its own, so one village tried "2 wood at the fire" 16 times over."""
        seen: collections.Counter = collections.Counter()
        if not self.flags.get("say"):
            return seen
        for o in self.agents_near(a.x, a.y, radius, exclude=a.id):
            seen.update(set(o.failed_experiments))
        return seen

    def same_land_xy(self, a: Agent, x: int, y: int) -> bool:
        """Is tile (x, y) (or a tile beside it) on the chit's own connected land?"""
        if not self.inb(x, y) or self.block[a.y * self.w + a.x]:
            return True
        comp = self._components()
        mine = comp[a.y * self.w + a.x]
        return any(self.inb(x + dx, y + dy) and comp[(y + dy) * self.w + x + dx] == mine
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1))

    def same_land(self, a: Agent, st: "Structure") -> bool:
        """Can this chit walk to the structure (a tile beside or on it on the chit's own connected land)?"""
        if self.block[a.y * self.w + a.x]:
            return True  # standing somewhere odd (on a building): don't guess
        comp = self._components()
        mine = comp[a.y * self.w + a.x]
        return any(comp[cy * self.w + cx] == mine for cx, cy in self.stand_tiles_for_structure(st) | set(st.cells())
                   if self.inb(cx, cy))

    def find_path(self, sx: int, sy: int, goals: Set[Tuple[int, int]], limit: Optional[int] = None) -> Optional[List[Tuple[int, int]]]:
        """A* over the flat grid to any goal tile (8-way, no corner cutting). The search budget grows with the map:
        9000 nodes was plenty on small islands, but on a 512 island chits who wandered 40+ tiles from home could no
        longer find their way back ("couldn't reach shelter" 35 times in a row) and froze or starved in winter."""
        chosen = limit is not None
        if limit is None:
            limit = max(9000, self.w * self.h // 8)
        if (sx, sy) in goals:
            return []
        if not goals:
            return None
        W, H = self.w, self.h
        blk = self.block
        roads = self.roads
        base = self._base_cost
        traffic = self.traffic
        goal_idx = {gy * W + gx for gx, gy in goals if 0 <= gx < W and 0 <= gy < H}
        if not goal_idx:
            return None
        if W * H > 16384 and not blk[sy * W + sx]:
            # on big islands a goal across water used to burn the whole search budget (~0.2-0.4 s, blocking
            # the server): if no goal tile (or its neighbour, for goals on a building) shares the start's
            # connected land, it can't be reached. Small maps skip this; results are the same either way.
            comp = self._components()
            near = {comp[k] for gi in goal_idx for k in (gi, gi - 1, gi + 1, gi - W, gi + W, gi - W - 1, gi - W + 1,
                                                        gi + W - 1, gi + W + 1) if 0 <= k < W * H}
            if comp[sy * W + sx] not in near:
                return None
            # the goal is on this land, so a path exists: a long way round water can take far more than 9000
            # nodes (a pile 14 tiles away was 140 on foot, and chits starved failing to reach it)
            if not chosen:
                limit = max(limit, W * H // 3)
        gxs = [g % W for g in goal_idx]
        gys = [g // W for g in goal_idx]
        tx = sum(gxs) / len(gxs)
        ty = sum(gys) / len(gys)
        rad = max(max(abs(x - tx) for x in gxs), max(abs(y - ty) for y in gys))
        start = sy * W + sx
        g = {start: 0.0}
        came: Dict[int, int] = {}
        h0 = max(abs(sx - tx), abs(sy - ty)) - rad
        openh = [(h0, 0.0, start)]
        n = 0
        push, pop = heapq.heappush, heapq.heappop
        while openh and n < limit:
            _, gc, cur = pop(openh)
            if cur in goal_idx:
                path = []
                while cur != start:
                    path.append((cur % W, cur // W))
                    cur = came[cur]
                path.reverse()
                return path
            if gc > g.get(cur, 1e18):
                continue
            n += 1
            x, y = cur % W, cur // W
            for dx, dy, c in self._NB:
                nx, ny = x + dx, y + dy
                if nx < 0 or ny < 0 or nx >= W or ny >= H:
                    continue
                ni = ny * W + nx
                if blk[ni]:
                    continue
                if dx and dy and (blk[y * W + nx] or blk[ny * W + x]):
                    continue
                mc = 0.45 if ni in roads else (base[ni] * 0.8 if traffic[ni] > 30 else base[ni])
                ng = gc + c * mc
                if ng < g.get(ni, 1e18):
                    g[ni] = ng
                    came[ni] = cur
                    hh = max(abs(nx - tx), abs(ny - ty)) - rad
                    push(openh, (ng + (hh if hh > 0 else 0) * 0.5, ng, ni))
        return None

    def stand_tiles_for(self, x: int, y: int) -> Set[Tuple[int, int]]:
        """Tiles from which a chit can work tile (x, y)."""
        out = set()
        if self.passable(x, y):
            out.add((x, y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx or dy) and self.passable(x + dx, y + dy):
                    out.add((x + dx, y + dy))
        return out

    def stand_tiles_for_structure(self, s: Structure) -> Set[Tuple[int, int]]:
        out = set()
        for cx, cy in s.cells():
            out |= self.stand_tiles_for(cx, cy)
        return out

    def ring_scan(self, x: int, y: int, radius: int, pred: Callable[[int, int, int], bool]) -> Optional[Tuple[int, int]]:
        """Nearest tile (by rings, then euclid within a ring) satisfying pred. Visits ring edges only."""
        W, H = self.w, self.h
        if 0 <= x < W and 0 <= y < H and pred(x, y, y * W + x):
            return x, y
        for r in range(1, radius + 1):
            best = None
            y0, y1, x0, x1 = y - r, y + r, x - r, x + r
            for nx in range(max(0, x0), min(W - 1, x1) + 1):
                for ny in (y0, y1):
                    if 0 <= ny < H and pred(nx, ny, ny * W + nx):
                        d = (nx - x) ** 2 + (ny - y) ** 2
                        if best is None or d < best[0]:
                            best = (d, nx, ny)
            for ny in range(max(0, y0 + 1), min(H - 1, y1 - 1) + 1):
                for nx in (x0, x1):
                    if 0 <= nx < W and pred(nx, ny, ny * W + nx):
                        d = (nx - x) ** 2 + (ny - y) ** 2
                        if best is None or d < best[0]:
                            best = (d, nx, ny)
            if best:
                return best[1], best[2]
        return None

    def reachable_edge(self, i: int) -> bool:
        """Can a chit stand on or next to tile i?"""
        W = self.w
        x, y = i % W, i // W
        blk = self.block
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < self.h and not blk[ny * W + nx]:
                    return True
        return False

    def nearest_resource(self, x: int, y: int, kind: str, radius: int = 24, avoid: Optional[Set[int]] = None) -> Optional[Tuple[int, int]]:
        k = T.RES_INDEX.get(kind)
        if kind == "seeds":
            k = T.RES_INDEX["fiber"]
        if k is None:
            return None
        avoid = avoid or set()
        rk, ra = self.res_kind, self.res_amt
        return self.ring_scan(x, y, radius, lambda nx, ny, i: rk[i] == k and ra[i] > 0 and i not in avoid and self.reachable_edge(i))

    # ------------------------------------------------------------------ structures
    def structures_near(self, x: int, y: int, radius: int, design: Optional[str] = None) -> List[Structure]:
        out = []
        for s in self.structures.values():
            if design and s.design != design and not (design == "stockpile" and s.design in STORES):
                continue  # (asking for stockpiles finds outpost camps' stores too)
            if s.dist(x, y) <= radius:
                out.append(s)
        out.sort(key=lambda s: s.dist(x, y))
        return out

    def stations_at(self, x: int, y: int, radius: int = 2) -> Set[str]:
        st: Set[str] = set()
        for s in self.structures_near(x, y, radius):
            st |= s.stations()
        return st

    def nearest_station(self, x: int, y: int, station: str, radius: int = 40) -> Optional[Structure]:
        for s in self.structures_near(x, y, radius):
            if station in s.stations():
                return s
        return None

    def footprint_free(self, x: int, y: int, w: int, h: int, margin: int = 0) -> bool:
        for dy in range(-margin, h + margin):
            for dx in range(-margin, w + margin):
                nx, ny = x + dx, y + dy
                if not self.inb(nx, ny):
                    return False
                i = ny * self.w + nx
                inside = 0 <= dx < w and 0 <= dy < h
                if i in self.occupied:
                    return False
                if inside and (not T.PASSABLE[self.tiles[i]] or self.tiles[i] == T.FOREST and self.res_amt[i] > 0 and self.res_kind[i] == T.R_WOOD):
                    return False
                if inside and i in self.roads:
                    return False
        return True

    def near_rock(self, x: int, y: int, w: int = 1, h: int = 1) -> bool:
        """Rock or hills within a couple of tiles of a footprint: where a mine can be dug."""
        from .buildings import MINE_ROCK

        for yy in range(y - MINE_ROCK, y + h + MINE_ROCK):
            for xx in range(x - MINE_ROCK, x + w + MINE_ROCK):
                if self.inb(xx, yy) and self.tiles[yy * self.w + xx] in (T.ROCK, T.HILLS):
                    return True
        return False

    def coastal(self, x: int, y: int) -> bool:
        """A passable land tile next (4-neighbour) to water."""
        if not self.passable(x, y):
            return False
        return any(self.inb(x + dx, y + dy) and self.tiles[(y + dy) * self.w + x + dx] in (T.DEEP, T.SHALLOW)
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    def find_site(self, design: str, x: int, y: int, radius: int = 7,
                  reach: Optional[Tuple[int, int]] = None) -> Optional[Tuple[int, int]]:
        """The best free spot near (x, y). With `reach`, only spots on the same connected land as that tile: a site
        across a river was chosen 8 tiles away and 140 on foot, and chits failed to reach it 1,684 times."""
        d = DESIGNS[design]
        w, h = d.size
        margin = 0 if design in ("road", "boat") else 1
        if design in ("boat", "lighthouse"):
            radius = max(radius, 60)  # the shore may be a long walk from the village
        if design == "sand_pit":
            radius = max(radius, 30)  # the nearest shore or riverbank
        if design == "mine":
            radius = max(radius, 30)  # the rocks may be a walk from the village
        comp = self._components() if reach and self.inb(*reach) and not self.block[reach[1] * self.w + reach[0]] else None
        home = comp[reach[1] * self.w + reach[0]] if comp else 0
        cands = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if design in ("boat", "lighthouse", "sand_pit") and not self.coastal(nx, ny):
                    continue
                if design == "mine" and not self.near_rock(nx, ny, w, h):
                    continue
                if comp and self.inb(nx, ny) and comp[ny * self.w + nx] != home:
                    continue
                if self.footprint_free(nx, ny, w, h, margin):
                    dist = abs(dx) + abs(dy)
                    # like to build near existing settlement
                    near = sum(1 for s in self.structures.values() if s.dist(nx, ny) <= 5)
                    cands.append((dist - min(near, 4) * 1.5 + self.rng_for("sites").random() * 0.5, nx, ny))
        if not cands:
            return None
        cands.sort()
        return cands[0][1], cands[0][2]

    def place_site(self, design: str, x: int, y: int, founder: Agent) -> Structure:
        d = DESIGNS[design]
        s = Structure(
            id=self._new_id("struct"), design=design, x=x, y=y, w=d.size[0], h=d.size[1], founder=founder.id,
            created=self.tick, needs=dict(d.material_map), work_total=float(d.work),
        )
        self.structures[s.id] = s
        for cx, cy in s.cells():
            self.occupied[cy * self.w + cx] = s.id
        self.dirty_struct.add(s.id)
        return s

    def complete_structure(self, s: Structure, by: Agent) -> None:
        if s.complete:
            return  # idempotent: finishing twice must not fire events, homes or firsts twice
        s.complete = True
        s.completed = self.tick
        s.durability = 100.0
        d = DESIGNS[s.design]
        if s.design == "campfire":
            s.fuel = 60.0
        if s.design == "farm":
            s.planted = True
            s.growth = 0.0
        if s.design == "shrine" and by.belief in self.beliefs:
            s.belief = by.belief
            s.name = f"Shrine of {self.beliefs[by.belief]['name']}"
        if s.design == "road":
            for cx, cy in s.cells():
                i = cy * self.w + cx
                self.roads.add(i)
                self.dirty_roads.add(i)
                self.occupied.pop(i, None)
            self.structures.pop(s.id, None)
            self.removed_struct.add(s.id)
            by.bump("roads")
            if "design:road" not in self.first:
                self._first("design:road", by, f"{by.name} paved the first road")
            return
        self.dirty_struct.add(s.id)
        if s.design in self.BLOCKING or s.design == "bridge":
            self.rebuild_block()
        names = [self.agents[a].name for a in s.builders if a in self.agents]
        together = len(s.builders) >= 2
        who = _join_names(names) if names else by.name
        first = f"design:{s.design}" not in self.first
        txt = f"{who} finished {'the first ' if first else 'a '}{d.name}" + (" together" if together else "")
        imp = 4 if first else (2 if together else 1)
        self.emit("built", txt, imp, by.id, *s.center(), design=s.design, structure=s.id, builders=list(s.builders),
                  together=together, first=first)
        if first:
            self.first[f"design:{s.design}"] = {"tick": self.tick, "by": by.id, "name": by.name}
        if s.design == "launch_pad":
            self._launch(s)
        if first:
            self.update_era()
        for aid in s.builders:
            a = self.agents.get(aid)
            if not a:
                continue
            a.made_it_work(f"design:{s.design}", self.tick)
            a.bump("built")
            a.remember(self.tick, f"I helped finish a {d.name}" + (f" with {_join_names([n for n in names if n != a.name])}" if together else ""), 3, "build")
            if a.learn(f"design:{s.design}", "built", self.tick):
                pass
            for bid in s.builders:
                if bid != aid:
                    a.like(bid, 6)
        if s.design in BLD.HOMES:
            for aid in list(s.builders)[: (2 if s.design == "hut" else 4)]:
                a = self.agents.get(aid)
                if a and (not a.home or self._crowded_out(a) or self._pioneer_home(a, s)):
                    a.home = s.id
                    a.bump_rev("it moved into the house it built")

    def _pioneer_home(self, a: Agent, s: "Structure") -> bool:
        from . import pioneers

        return pioneers.moves_in(self, a, s)

    def _crowded_out(self, a: Agent) -> bool:
        """A grown chit in a crowded family home it didn't found: it moves into a home it builds. (Instinct used to
        move it out when it merely drafted the idea, so a plan it never took left it homeless.)"""
        home = self.structures.get(a.home or "")
        if home is None or not home.functional or home.founder == a.id or a.is_child(self.tick):
            return False
        return sum(1 for o in self.agents.values() if o.home == home.id) > BLD.HOME_CAP.get(home.design, 3)

    def _launch(self, s: Structure) -> None:
        crew_ids = [aid for aid, _ in sorted(s.builders.items(), key=lambda kv: -kv[1])[:3]]
        crew = [self.agents.get(aid) or self.dead.get(aid) for aid in crew_ids]
        crew = [c for c in crew if c]
        for c in crew:
            c.astronaut = True
            c.remember(self.tick, "I saw the whole island from the sky", 5, "wonder")
        names = _join_names([c.name for c in crew]) or "Nobody"
        self.emit("launch", f"{names} rode the first rocket into the sky — {self.name}'s first astronauts!", 5,
                  crew[0].id if crew else None, *s.center(), crew=[c.id for c in crew])

    # ------------------------------------------------------------------ events
    TALLY_BY = ("design", "item", "recipe", "cause", "evidence")

    def _tally(self, kind: str, data: Dict[str, Any]) -> None:
        self.tallies[kind] += 1
        for k in self.TALLY_BY:
            v = data.get(k) if data else None
            if isinstance(v, str) and v:
                self.tallies[f"{kind}:{v}"] += 1

    def lifetime(self, kind: str, of: Optional[str] = None) -> int:
        """How many `kind` events (of one design, item, recipe or cause) since `tallies_since`: whole-run totals."""
        return self.tallies.get(f"{kind}:{of}" if of else kind, 0)

    def recent(self, kind: str) -> int:
        """How many `kind` events are in the recent window (at most the last 4,000 events of any kind)."""
        return sum(1 for e in self.events if e.kind == kind)

    def emit(self, kind: str, text: str, importance: int = 1, actor: Optional[str] = None,
             x: Optional[float] = None, y: Optional[float] = None, **data: Any) -> Event:
        self.seq += 1
        ev = Event(self.seq, self.tick, kind, text, importance, actor, x, y, data)
        self.events.append(ev)
        self._tally(kind, data)
        for fn in self.listeners:
            try:
                fn(ev)
            except Exception:
                pass
        return ev

    def _first(self, key: str, agent: Agent, text: str) -> None:
        self.first[key] = {"tick": self.tick, "by": agent.id, "name": agent.name}
        self.emit("first", text, 5, agent.id, agent.x, agent.y, key=key)

    def learned(self, agent: Agent, knowledge: str, how: str, source: Optional[Agent] = None) -> bool:
        """Grant knowledge with provenance + events. Returns True if new."""
        if not agent.learn(knowledge, how, self.tick, source.id if source else None):
            return False
        agent.bump_rev(f"it learned {knowledge.split(':', 1)[-1]} ({how})")
        channel = {"taught": "teach", "read": "read", "observed": "observe", "inspected": "inspect", "raised": "raised"}.get(how)
        if channel:
            self.deliver(channel, source, agent, knowledge, None)
        kind, key = knowledge.split(":", 1)
        nm = self.item_name(key) if kind == "recipe" else DESIGNS[key].name
        via = {
            "discovered": "discovered how to make", "taught": "was taught how to make", "observed": "watched and learned how to make",
            "inspected": "figured out how to make", "read": "read how to make", "insight": "imagined",
            "built": "learned to build",
        }.get(how, "learned")
        if kind == "design":
            via = {"taught": "was taught to build", "read": "read how to build", "inspected": "studied and learned to build",
                   "observed": "watched and learned to build", "insight": "came up with the idea of a", "built": "learned to build"}.get(how, "learned to build")
        src = f" from {source.name}" if source and how in ("taught",) else ""
        text = f"{agent.name} {via} {nm}{src}"
        local = self.culture_names.get(knowledge)
        extra = {"local_name": local} if local else {}
        is_first = knowledge not in self.first
        if is_first and how in ("discovered", "insight"):
            self.first[knowledge] = {"tick": self.tick, "by": agent.id, "name": agent.name}
            if local and kind == "recipe":
                text = f'{agent.name} discovered how to make {nm} and named it "{local}"'
            self.emit("discovery", f"{text} — a first for the world!", 5, agent.id, agent.x, agent.y, knowledge=knowledge, how=how, **extra)
            agent.set_emote("✨", self.tick, 40)
            self.update_era()
        else:
            if is_first:
                self.first[knowledge] = {"tick": self.tick, "by": agent.id, "name": agent.name}
            imp = 3 if how in ("taught", "read") else 2
            self.emit("learned", text, imp, agent.id, agent.x, agent.y, knowledge=knowledge, how=how,
                      source=source.id if source else None, **extra)
            agent.set_emote("💡", self.tick, 25)
        agent.remember(self.tick, f"I {via.replace(agent.name, '')} {nm}{src}".replace("  ", " "), 4, "learn")
        agent.bump("learned")
        # newly-met prerequisites may spark design ideas
        self.check_insights(agent)
        return True

    def check_insights(self, agent: Agent) -> None:
        for key in DESIGNS:
            if not agent.knows_design(key) and design_prereqs_met(agent, key):
                self.learned(agent, f"design:{key}", "insight")

    def notice_items(self, agent: Agent) -> None:
        # Agent.add has usually recorded the item already, so check for ideas every time (cheap: a few designs)
        agent.familiar.update(k for k, n in agent.inventory.items() if n > 0)
        self.check_insights(agent)

    # ------------------------------------------------------------------ queries for brains
    def agent_by_name(self, name: str, near: Optional[Agent] = None) -> Optional[Agent]:
        """The chit with this name or id. Several can share a name (old worlds named many "Chit2154"): then the one
        nearest `near`, the chit asking, not whichever came first: live, chits walked off after a namesake across
        the map and failed "couldn't find X to talk to" 36-48 times in ten days."""
        n = str(name or "").strip().lower()
        found = [a for a in self.agents.values() if a.name.lower() == n or a.id == n]
        if len(found) > 1 and near is not None:
            return min(found, key=lambda o: (o.id != n, max(abs(o.x - near.x), abs(o.y - near.y)), o.id))
        return found[0] if found else None

    def agents_near(self, x: int, y: int, radius: int, exclude: Optional[str] = None) -> List[Agent]:
        out = [a for a in self.agents.values() if a.id != exclude and max(abs(a.x - x), abs(a.y - y)) <= radius]
        out.sort(key=lambda a: max(abs(a.x - x), abs(a.y - y)))
        return out

    # ------------------------------------------------------------------ tick
    def step(self, brain_hook: Optional[Callable[["World", Agent], None]] = None) -> None:
        from . import actions

        self.tick += 1
        t = self.tick
        temp = self.temperature()
        winter = self.season == "winter"

        # environment
        if self.animals:
            if t % 4 == 0:
                ANIMALS.move(self)
            if t % 10 == 0:
                ANIMALS.attacks(self)
        if t % 10 == 0:
            self._regrow(winter)
            if self.beliefs:
                self._belief_tick()
        for s in list(self.structures.values()):
            self._structure_tick(s, winter)

        idols = ART.idol_positions(self) if self.ground or any("golden_idol" in a.inventory for a in self.agents.values()) else []
        for a in list(self.agents.values()):
            a.catalog = self.catalog
            self._needs(a, temp)
            if idols and any(max(abs(a.x - x), abs(a.y - y)) <= 6 for x, y in idols):
                a.mood = min(100.0, a.mood + 0.05)
            if not a.alive:
                continue
            actions.reflexes(self, a)
            if brain_hook:
                brain_hook(self, a)
            actions.run(self, a)
            i = a.y * self.w + a.x
            self.traffic[i] = min(100.0, self.traffic[i] + 0.6)
            if self.traffic[i] > 30 and i not in self.dirty_roads and self.traffic[i] - 0.6 <= 30:
                self.dirty_roads.add(i)

        if t % 60 == 0:
            self.update_settlements()
        if self.weather != "clear" and t >= self.weather_until:
            self.weather = "clear"
        if t % 30 == 0:
            self._company()
        if t % 10 == 0:
            PROJECTS.tick(self)
        if t % 60 == 0 and self.signs:
            old = [g for g, v in self.signs.items() if t - v["tick"] > 720]
            for g in old:
                del self.signs[g]
            if old:
                self.signs_dirty = True
        if t % 60 == 0:
            for i in range(0, len(self.traffic)):
                v = self.traffic[i]
                if v:
                    nv = v * 0.985
                    if v > 30 >= nv:
                        self.dirty_roads.add(i)
                    self.traffic[i] = nv if nv > 0.5 else 0.0
        BLD.step(self)  # schools, the morning bell, food rotting in the stores
        if t % TICKS_PER_DAY == 0:
            self._new_day()

    NEIGHBOUR_BOND = 1.0  # a day's worth of knowing the people who live next door

    def _neighbours(self) -> None:
        """Adults whose homes stand within 10 tiles come to know each other a little every day. Friendship only
        grew within 3 tiles, so once parents could no longer pair with their own children, a village's grown
        children rarely bonded with anyone outside the family: couples fell from 30 to 0-3 and every long run
        shrank after day 40 as the founders died of old age."""
        t = self.tick
        homed = [(a, self.structures.get(a.home or "")) for a in self.agents.values() if not a.is_child(t)]
        homed = [(a, h) for a, h in homed if h is not None and h.functional]
        for i, (a, ha) in enumerate(homed):
            for b, hb in homed[i + 1:]:
                if max(abs(ha.x - hb.x), abs(ha.y - hb.y)) <= 10:
                    a.like(b.id, self.NEIGHBOUR_BOND)
                    b.like(a.id, self.NEIGHBOUR_BOND)

    def _company(self) -> None:
        """Time spent near each other, awake, builds friendship. It needs no words, so it works in World B too."""
        for a in self.agents.values():
            for o in self.agents_near(a.x, a.y, 3, exclude=a.id):
                if o.id <= a.id:
                    continue
                if a.activity != "sleeping" and o.activity != "sleeping":
                    a.like(o.id, 0.35)
                    o.like(a.id, 0.35)
                elif a.home and a.home == o.home and self.in_home(a) and self.in_home(o):
                    a.like(o.id, 0.5)  # sharing a roof
                    o.like(a.id, 0.5)

    def _regrow(self, winter: bool) -> None:
        rng = self.rng_for("regrow")
        n = len(self.res_kind)
        # each tile should be visited about every 182 ticks: 900 samples per 10 ticks on a 128 map, and in
        # proportion on bigger ones (a fixed 900 left a 512 island ~15x slower to regrow; 128 is unchanged)
        samples = max(900, round(900 * n / 16384))
        for _ in range(samples):
            i = rng.randrange(n)
            k = self.res_kind[i]
            if not k:
                continue
            mx, period, wmul = T.RES_PROFILE[k]
            if period <= 0 or self.res_amt[i] >= mx:
                continue
            mul = wmul if winter else 1.0
            if k in (T.R_BERRIES, T.R_FIBER):
                if self.weather == "drought":
                    continue
                if self.weather == "rain" and k == T.R_BERRIES:
                    mul *= 1.5
            gain = mul * (n * 10 / samples) / period
            add = int(gain) + (1 if rng.random() < gain - int(gain) else 0)
            if add:
                self.res_amt[i] = min(mx, self.res_amt[i] + add)
                self.dirty_res.add(i)

    def _structure_tick(self, s: Structure, winter: bool) -> None:
        if not s.complete:
            # abandoned sites slowly fall apart
            idle = self.tick - max(s.created, s.last_work)
            if idle > TICKS_PER_DAY * 6 and (not s.builders or idle > TICKS_PER_DAY * SITE_IDLE_DAYS):
                # (the diagnostics' "sites abandoned" counted this event, which nothing ever emitted: it read 0)
                self.emit("abandoned", f"The unfinished {DESIGNS[s.design].name} was abandoned", 1, None, *s.center(),
                          design=s.design, structure=s.id)
                self.remove_structure(s)
            return
        d = DESIGNS[s.design]
        if d.decay_per_day > 0 and s.durability > 0:
            s.durability -= d.decay_per_day * (1.6 if winter else 1.0) / TICKS_PER_DAY
            if s.durability <= 0:
                s.durability = 0
                s.ruined_at = self.tick
                self.dirty_struct.add(s.id)
                self.emit("ruin", f"The {d.name} fell into ruin", 2, None, *s.center(), structure=s.id)
        if s.durability <= 0:
            if s.ruined_at < 0:
                s.ruined_at = self.tick
            elif self.tick - s.ruined_at > TICKS_PER_DAY * RUIN_DAYS:
                self.emit("crumbled", f"The ruined {d.name} crumbled away", 1, None, *s.center(), structure=s.id)
                self.remove_structure(s)
            return
        if s.design == "campfire" and s.fuel > 0:
            s.out_since = -1
            s.fuel -= (0.1 if not self.is_night else 0.14) + (0.05 if self.weather == "rain" else 0.0)
            if s.fuel <= 0:
                s.fuel = 0
                s.out_since = self.tick
                self.dirty_struct.add(s.id)
                self.emit("fire_out", "A campfire burned out", 1, None, *s.center(), structure=s.id)
            elif self.tick % 40 == 0:
                self.dirty_struct.add(s.id)
        elif s.design == "campfire":
            if s.out_since < 0:
                s.out_since = self.tick  # (an older save: count from now)
            elif self.tick - s.out_since > TICKS_PER_DAY * ASHES_DAYS:
                self.remove_structure(s)  # left cold: scattered stones and ash, then nothing
                return
        if s.design == "farm" and s.functional and s.planted and s.growth < 1.0 and not winter \
                and (self.weather != "drought" or BLD.watered(self, s)):
            s.growth = min(1.0, s.growth + (1.5 if self.weather == "rain" else 1.0) * BLD.growth_mult(self, s)
                           / (TICKS_PER_DAY * 0.9))
            if self.tick % 30 == 0 or s.growth >= 1.0:
                self.dirty_struct.add(s.id)

    def remove_structure(self, s: Structure) -> None:
        for cx, cy in s.cells():
            self.occupied.pop(cy * self.w + cx, None)
        self.structures.pop(s.id, None)
        self.removed_struct.add(s.id)
        # a crumbled library's tablets lie where it stood, to be read or shelved again: they stayed "in" a building
        # that was gone, where nothing could read them (World B kept 180 of its 196 tablets that way, steel among them)
        for tb in self.tablets.values():
            if tb.in_structure == s.id:
                tb.in_structure = None
                tb.x, tb.y = s.x, s.y
        if s.complete and (s.design in self.BLOCKING or s.design == "bridge"):
            self.rebuild_block()
            BLD.off_the_bridge(self, s)
        for a in self.agents.values():
            if a.home == s.id:
                a.home = None
                a.bump_rev("its home was destroyed")

    def in_home(self, a: Agent) -> Optional[Structure]:
        sid = self.occupied.get(a.y * self.w + a.x)
        if sid:
            s = self.structures.get(sid)
            if s and s.functional and (s.design in BLD.HOMES or s.design == "outpost"):
                return s  # (an outpost camp shelters those who sleep there)
        return None

    def _zones(self) -> Tuple[Set[int], Set[int]]:
        """Tiles warmed by fires and tiles cheered by monuments; rebuilt every few ticks."""
        if self._zone_tick is not None and self.tick - self._zone_tick < 5:
            return self._warm_tiles, self._joy_tiles
        warm: Set[int] = set()
        joy: Set[int] = set()
        for s in self.structures.values():
            if s.lit or (s.design in ("kiln", "furnace") and s.functional):
                r = 3
                tgt = warm
            elif s.design == "monument" and s.functional:
                r = 10
                tgt = joy
            elif s.design == "park" and s.functional:
                r = 6  # (BLD.PARK_RADIUS)
                tgt = joy
            else:
                continue
            for y in range(s.y - r, s.y + s.h + r):
                for x in range(s.x - r, s.x + s.w + r):
                    if 0 <= x < self.w and 0 <= y < self.h:
                        tgt.add(y * self.w + x)
        self._warm_tiles, self._joy_tiles, self._zone_tick = warm, joy, self.tick
        return warm, joy

    def near_fire(self, a: Agent, r: int = 3) -> bool:
        return (a.y * self.w + a.x) in self._zones()[0]

    HUT_WARM_TO = -0.3  # a hut keeps its sleepers warm on ordinary winter nights (-0.21), not in a winter storm

    def _needs(self, a: Agent, temp: float) -> None:
        t = self.tick
        sleeping = a.activity == "sleeping"
        child = a.is_child(t)
        a.hunger -= 0.22 * (0.7 if sleeping else 1.0) * (0.8 if child else 1.0)
        if sleeping:
            home = self.in_home(a)
            a.energy += (1.7 if home else 0.9) * BLD.rest_mult(self, a)  # a well nearby: fresh water, better rest
        else:
            a.energy -= 0.2
        sheltered = self.in_home(a)
        warm_src = self.near_fire(a) or (sheltered and (sheltered.design in BLD.WARM_HOMES or temp > self.HUT_WARM_TO)) or a.best_tool("light")
        cloak = 0.5 if self.inventions and self.invention_effect(a, "warmth") else 1.0
        if cloak == 1.0 and any(n > 0 and (it := self.item(k)) and "wearable" in it.props and "warm" in it.props
                                for k, n in a.inventory.items()):
            cloak = 0.5  # a warm thing to wear (T31)
        if temp < 0.42 and not warm_src:
            a.warmth -= (0.42 - temp) * 1.6 * (0.7 if sheltered else 1.0) * cloak
        else:
            a.warmth += 0.8
        if self.weather != "clear":
            ex = self.exposure(a)
            if ex:
                a.warmth -= ex * cloak
                if self.weather == "storm":
                    a.health -= 0.02
        a.hunger = max(0.0, min(100.0, a.hunger))
        a.energy = max(0.0, min(100.0, a.energy))
        a.warmth = max(0.0, min(100.0, a.warmth))
        dmg = 0.0
        causes = []
        if a.hunger <= 0:
            dmg += 0.22
            causes.append("starvation")
        if a.warmth <= 5:
            dmg += 0.16
            causes.append("cold")
        if a.energy <= 0:
            dmg += 0.08
            causes.append("exhaustion")
        if dmg:
            a.health -= dmg
        elif a.hunger > 40 and a.warmth > 40:
            heal = 0.08 + (0.12 if self.inventions and self.invention_effect(a, "heal") else 0.0)  # a remedy
            a.health = min(100.0, a.health + heal * BLD.heal_mult(self, a))  # (a healer's house nearby)
        # mood: comfort + monuments + company
        target = (a.hunger + a.energy + a.warmth) / 3.0
        if (a.y * self.w + a.x) in self._zones()[1]:
            target += 15
        a.mood += (target - a.mood) * 0.01
        if self.inventions and self.invention_effect(a, "mood"):
            a.mood = max(0.0, min(100.0, a.mood + 0.02))
        if a.health <= 0:
            self.kill(a, causes[0] if causes else "illness")
        elif t - a.born > a.lifespan:
            self.kill(a, "old age")

    def kill(self, a: Agent, cause: str) -> None:
        a.alive = False
        a.died = self.tick
        a.cause_of_death = cause
        a.activity = "dead"
        self.agents.pop(a.id, None)
        self.dead[a.id] = a
        bel = self.beliefs.get(a.belief)
        if bel and a.id in bel["followers"]:
            bel["followers"].remove(a.id)
        if a.id == self.leader:
            self.leader = ""  # a successor is chosen at the next day boundary
        days = a.age(self.tick)
        # drop inventory into a nearby stockpile or lose it
        imp = 4 if cause != "old age" else 3
        # the first chits arrive as young adults, so their age runs ahead of the world's day: say so
        founder = " (one of the first chits, who arrived as young adults)" if a.generation == 0 and not a.parents else ""
        self.emit("death", f"{a.name} died of {cause} at {days:.0f} days old{founder}", imp, a.id, a.x, a.y, cause=cause)
        for o in self.agents.values():
            if o.affinity.get(a.id, 0) > 20:
                o.remember(self.tick, f"My friend {a.name} died of {cause}", 5, "loss")
                o.mood -= 15
        from . import lore

        lore.on_death(self, a)  # the last one who knew how to make something: the village has forgotten it
        a.obituary()  # a dead chit's record keeps who it was and what it knew, not every memory and plan

    def _new_day(self) -> None:
        day = self.day
        self.update_era()
        self._expire_ground()
        self._neighbours()
        for a in self.agents.values():
            if a.reflex_rest:
                a.reflex_rest = {k: v for k, v in a.reflex_rest.items() if v > self.tick}
        ANIMALS.daily(self)
        self.assign_jobs()
        self.update_money()
        guards = sum(1 for a in self.agents.values() if a.job == "guard")
        if guards >= 4 and guards >= 2 * max(2, self.militia_n):
            self.militia_n = guards
            self.emit("militia", f"{self.name} now keeps a guard of {guards}", 4, guards=guards)
        if day % 10 == 0 or not self.leader or self.leader not in self.agents:
            if self.leader and self.leader not in self.agents:
                self.leader = ""
            self.choose_leader("scheduled" if day % 10 == 0 else "succession")
        if self.tick >= self.weather_until:
            self._roll_weather()
        if day % DAYS_PER_SEASON == 0:
            self.emit("season", f"{self.season.capitalize()} of year {self.year} begins", 2, season=self.season)
        PROJECTS.new_day(self)
        from . import lore

        lore.daily(self)  # an old chit is the last who knows how to make something: say so
        from . import pioneers

        pioneers.daily(self)  # a full village sends pioneers to found a new one
        self._births()
        self.history.append(self.stats())

    def pop_cap(self) -> int:
        return POP_CAP_BIG if self.w * self.h >= 256 * 256 else POP_CAP

    def _births(self) -> None:
        if len(self.agents) >= self.pop_cap():
            return
        from . import pioneers as PI

        size, n_villages = PI.village_sizes(self)
        adults = [a for a in self.agents.values() if not a.is_child(self.tick) and a.age(self.tick) < 40]
        # the smallest villages first: at the cap every free place went to the big village (its chits come first), and
        # all six daughter villages in the live worlds died out with their founders
        adults.sort(key=lambda a: size.get(a.id, 0))
        used = set()
        for a in adults:
            if a.id in used or self.tick - a.last_birth_tick < TICKS_PER_DAY * 5:
                continue
            if n_villages > 1 and size.get(a.id, 0) >= PI.VILLAGE_ROOM:
                continue  # a village this full has its children in the others (never when it is the only one)
            if a.hunger < 45 or a.health < 60:
                continue
            best = None
            for b in adults:
                if b.id == a.id or b.id in used or self.tick - b.last_birth_tick < TICKS_PER_DAY * 5:
                    continue
                if b.hunger < 45 or b.health < 60:
                    continue
                if a.affinity.get(b.id, 0) < BOND_TO_BREED or b.affinity.get(a.id, 0) < BOND_TO_BREED:
                    continue
                if b.id in a.parents or a.id in b.parents or set(a.parents) & set(b.parents):
                    continue  # never a parent and its child, or brothers and sisters
                if max(abs(a.x - b.x), abs(a.y - b.y)) > 12:
                    continue
                aff = a.affinity[b.id] + b.affinity[a.id]
                if best is None or aff > best[0]:
                    best = (aff, b)
            if not best:
                continue
            b = best[1]
            home, room = BLD.birth_home(self, a, b)  # a full home halves the chance of a child, an overfull one ends it
            if not home or not room:
                continue
            if self.rng_for("births").random() > 0.5 * room:
                continue
            used |= {a.id, b.id}
            self._make_child(a, b, home)
            if len(self.agents) >= self.pop_cap():
                return

    def _make_child(self, a: Agent, b: Agent, home: Structure) -> Agent:
        taken = {x.name for x in list(self.agents.values()) + list(self.dead.values())}
        name = make_name(self.rng_for("births"), taken)
        base = {t: (a.traits[t] + b.traits[t]) / 2 for t in a.traits}
        child = new_agent(self.rng_for("births"), self._new_id("agent"), name, home.x, home.y, self.tick, spread=0.08,
                          base_traits=base, generation=max(a.generation, b.generation) + 1, parents=(a.id, b.id),
                          age_days=0.0)
        br = self.rng_for("births")
        child.hue = int((a.hue + b.hue) / 2 + br.randint(-20, 20)) % 360 if abs(a.hue - b.hue) < 180 else (a.hue + br.randint(-20, 20)) % 360
        child.hunger = 80
        child.home = home.id
        child.brain = a.brain
        for p in (a, b):
            p.last_birth_tick = self.tick
            p.like(child.id, 50)
            child.like(p.id, 50)
            p.remember(self.tick, f"My child {name} was born", 5, "family")
            p.set_emote("♥", self.tick, 60)
        a.like(b.id, 10)
        b.like(a.id, 10)
        child.catalog = self.catalog
        # a child grows up hearing how its parents make things: each proven recipe is passed on half the time,
        # as "told, untried". Chits live 45-70 days and knowledge died with them (World A: charcoal lost twice)
        self.agents[child.id] = child
        rng = self.rng_for("inheritance")
        if self.flags.get("teach"):
            for p in (a, b):
                for k, v in list(p.knows.items()):
                    if k.startswith("recipe:") and v.get("status") == "worked" and v.get("how") != "instinct" and rng.random() < 0.5:
                        self.learned(child, k, "raised", p)
        self.emit("birth", f"{name} was born to {a.name} and {b.name}", 4, child.id, child.x, child.y,
                  parents=[a.id, b.id], generation=child.generation)
        if a.belief and a.belief == b.belief:
            self.convert(child, a.belief, "raised")
        return child

    # ------------------------------------------------------------------ stats / serialization
    def stats(self) -> Dict[str, Any]:
        built = [s for s in self.structures.values() if s.complete]
        by_design: Dict[str, int] = {}
        for s in built:
            by_design[s.design] = by_design.get(s.design, 0) + 1
        known = set()
        for a in self.agents.values():
            known |= set(a.knows)
        stored = sum(sum(s.storage.values()) for s in self.structures.values())
        return {
            "tick": self.tick, "day": self.day + 1, "population": len(self.agents), "deaths": len(self.dead),
            "structures": len(built), "sites": sum(1 for s in self.structures.values() if not s.complete),
            "by_design": by_design, "knowledge": len(known), "discoveries": len(self.first),
            "roads": len(self.roads), "tablets": len(self.tablets), "stored": stored,
            "avg_hunger": round(sum(a.hunger for a in self.agents.values()) / max(1, len(self.agents)), 1),
            "generations": max([a.generation for a in self.agents.values()] or [0]),
            "settlements": len(self.settlements), "era": ERAS[self.era_index][0],
            "jobs": _count_jobs(self.agents.values()),
            "guards": sum(1 for a in self.agents.values() if a.job == "guard"),
            "trades": sum(1 for t in self.trades if self.tick - t["tick"] <= TICKS_PER_DAY), "currency": self.currency,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "label": self.label, "seed": self.seed, "culture": self.culture,
            "terrain_version": self.terrain_version,
            "size": self.w, "tick": self.tick, "rng_scheme": RNG_SCHEME,
            "rng_state": {k: [r.getstate()[0], list(r.getstate()[1]), r.getstate()[2]] for k, r in self._rngs.items()},
            "res_amt": self.res_amt, "traffic": [round(v, 1) for v in self.traffic], "roads": sorted(self.roads),
            "tunnels": sorted([i, sid] for i, sid in self.tunnels.items()),
            "agents": [a.to_dict() for a in self.agents.values()], "dead": [a.to_dict() for a in self.dead.values()],
            "structures": [s.to_dict() for s in self.structures.values()],
            "tablets": [t.to_dict() for t in self.tablets.values()], "seq": self.seq, "first": self.first,
            "counters": self.counters, "history": self.history[-400:],
            "events": [e.to_dict() for e in list(self.events)[-1500:]],
            "tallies": dict(self.tallies), "tallies_since": self.tallies_since,
            "deliveries": list(self.deliveries)[-500:], "culture_names": self.culture_names, "signs": self.signs,
            "weather": self.weather, "weather_until": self.weather_until, "settlements": self.settlements,
            "inventions": self.inventions, "beliefs": self.beliefs, "era_index": self.era_index,
            "trades": self.trades[-200:], "currency": self.currency,
            "leader": self.leader, "leader_since": self.leader_since, "laws": self.laws, "militia_n": self.militia_n,
            "challenge": self.challenge, "cold_until": self.cold_until,
            "ground": self.ground, "artifact_uses": self.artifact_uses, "outbox": self.outbox,
            "animals": self.animals, "relations": self.relations, "civic": PROJECTS.save(self),
            "schema": SNAPSHOT_SCHEMA, "uuid": self.uuid, "epoch": self.epoch, "epochs": self.epochs, "build": BUILD,
        }

    def deliver(self, channel: str, frm: Optional[Agent], to: Agent, knowledge: Optional[str], message: Optional[str]) -> None:
        self.deliveries.append({"tick": self.tick, "channel": channel, "from": frm.id if frm else None, "to": to.id,
                                "knowledge": knowledge, "message": message})

    def timeline(self) -> List[Tuple[str, Optional[Tuple[Optional[int], int]]]]:
        """This timeline's history for reads: the current epoch, then each ancestor with (seq, tick) where its child
        forked from it. The ancestor's past is its events up to that seq (or, for forks made before seq was recorded,
        before that tick); what came after is an abandoned future. A restart after a crash forks a new epoch, and
        reads of the current epoch alone made every day before it vanish from the chronicle."""
        by = {e["epoch"]: e for e in self.epochs}
        out: List[Tuple[str, Optional[Tuple[Optional[int], int]]]] = []
        cur, until = self.epoch, None
        while cur and all(cur != x for x, _ in out):
            out.append((cur, until))
            e = by.get(cur)
            if not e or not e.get("parent"):
                break
            cur, until = e["parent"], (e.get("from_seq"), e["from_tick"])
        return out

    def fork_epoch(self, reason: str) -> str:
        """Start a new timeline (after a rewind/restore), so two futures are never spliced together."""
        parent = self.epoch
        self.epoch = uuid.uuid4().hex
        # from_seq: the parent's events up to this one are this timeline's past (a restored world carries its seq back)
        self.epochs.append({"epoch": self.epoch, "parent": parent, "from_tick": self.tick, "from_seq": self.seq,
                            "created": time.time()})
        self.emit("timeline", f"A new timeline begins ({reason})", 2, epoch=self.epoch, parent=parent)
        return self.epoch

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "World":
        d = migrate_snapshot(d)
        w = cls.__new__(cls)
        w.uuid, w.epoch, w.epochs = d["uuid"], d["epoch"], list(d["epochs"])
        w.deliveries = deque(d.get("deliveries") or [], maxlen=3000)
        w.culture_names = dict(d.get("culture_names") or {})
        w.catalog = Catalog()
        w.inventions = dict(d.get("inventions") or {})
        w.beliefs = dict(d.get("beliefs") or {})
        w.era_index = int(d.get("era_index", 0))
        w.trades = list(d.get("trades") or [])
        w.currency = d.get("currency", "") or ""
        w.leader = d.get("leader", "") or ""
        w.leader_since = int(d.get("leader_since", -1))
        w.laws = list(d.get("laws") or [])
        w.challenge = dict(d.get("challenge") or {})
        w.cold_until = int(d.get("cold_until", -1))
        w.militia_n = int(d.get("militia_n", 0))
        w.ground = {k: dict(v) for k, v in (d.get("ground") or {}).items()}
        w.artifact_uses = dict(d.get("artifact_uses") or {})
        w.outbox = list(d.get("outbox") or [])
        w.animals = {k: dict(v) for k, v in (d.get("animals") or {}).items()}
        w._wolf_nights = set()
        w.relations = {k: dict(v) for k, v in (d.get("relations") or {}).items()}
        w.incident_sink = None
        w.contact = False
        from .invent import register_invention

        for key, inv in w.inventions.items():  # the world must know its own items again after a restart
            register_invention(w, key, inv["name"], inv["inputs"], tuple(inv.get("props") or ()), inv.get("effect") or {})
        w.signs = dict(d.get("signs") or {})
        w.weather = d.get("weather", "clear")
        w.settlements = dict(d.get("settlements") or {})
        w.weather_until = d.get("weather_until", 0)
        w.signs_dirty = False
        w.id, w.name, w.label, w.seed, w.culture = d["id"], d["name"], d.get("label", d["name"]), d["seed"], d["culture"]
        w.flags = dict(CULTURE_FLAGS[w.culture])
        w.w = w.h = d["size"]
        w.tick = d["tick"]
        scheme = int(d.get("rng_scheme", 1))
        if scheme not in (1, RNG_SCHEME):
            raise ValueError(f"unsupported RNG scheme {scheme}; this build understands 1 and {RNG_SCHEME}")
        w._rngs = {}
        for k, st in (d.get("rng_state") or {}).items():
            r = random.Random()
            r.setstate((st[0], tuple(st[1]), st[2]))
            w._rngs[k] = r
        if "rng" in d and "misc" not in w._rngs:  # snapshots from before streams existed
            st = d["rng"]
            r = random.Random()
            r.setstate((st[0], tuple(st[1]), st[2]))
            w._rngs["misc"] = r
        # Scheme 1 shared misc between storm damage, preaching, fights and artifacts. Preserve the old
        # stream position as the starting weather-damage position, then keep every domain separate from now on.
        if "weather_damage" not in w._rngs and "misc" in w._rngs:
            r = random.Random()
            r.setstate(w._rngs["misc"].getstate())
            w._rngs["weather_damage"] = r
        w.rng_scheme = RNG_SCHEME
        w.terrain_version = d.get("terrain_version", 1)  # saves from before versioning used version 1
        w.tiles, w.res_kind, _ = T.generate(w.seed, w.w, w.h, w.terrain_version)
        w.res_amt = list(d["res_amt"])
        w.traffic = list(d["traffic"])
        w.roads = set(d["roads"])
        w.tunnels = {int(i): sid for i, sid in d.get("tunnels", [])}
        w.agents = {a["id"]: Agent.from_dict(a) for a in d["agents"]}
        w.dead = {a["id"]: Agent.from_dict(a) for a in d["dead"]}
        for a in w.dead.values():
            a.obituary()  # (older saves kept every dead chit's whole record)
        w.structures = {s["id"]: Structure.from_dict(s) for s in d["structures"]}
        for s_d in d["structures"]:
            st = w.structures[s_d["id"]]
            if "last_work" not in s_d and not st.complete:
                st.last_work = d["tick"]  # older save: count its sites as worked on now, not idle since tick -1
        w.tablets = {t["id"]: Tablet(**t) for t in d["tablets"]}
        for tb in w.tablets.values():  # (a save from before libraries let go of their tablets when they crumbled)
            if tb.in_structure and tb.in_structure not in w.structures:
                tb.in_structure = None
        w.events = deque((Event(**e) for e in d.get("events", [])), maxlen=4000)
        if "tallies" in d:
            w.tallies, w.tallies_since = Counter(d["tallies"]), int(d.get("tallies_since", 0))
        else:  # a save from before tallies: count what it remembers, and say from when (the window is contiguous)
            w.tallies = Counter()
            for e in w.events:
                w._tally(e.kind, e.data or {})
            w.tallies_since = w.events[0].tick if w.events else w.tick
        w.seq = d["seq"]
        w.first = d["first"]
        w.counters = d["counters"]
        w.dirty_res, w.dirty_struct, w.removed_struct, w.dirty_roads = set(), set(), set(), set()
        w.listeners = []
        w.history = d.get("history", [])
        w.occupied = {}
        for s in w.structures.values():
            for cx, cy in s.cells():
                w.occupied[cy * w.w + cx] = s.id
        w.spawn = T.find_spawn(w.tiles, w.res_kind, w.w, w.h, w.seed)
        w._zone_tick = None
        w.rebuild_block()
        for a in list(w.agents.values()) + list(w.dead.values()):
            a.catalog = w.catalog
        for a in w.agents.values():
            a.thinking = False
            a.pending_plan = None
        PROJECTS.load(w, d)
        return w


def _count_jobs(agents) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for a in agents:
        if a.job:
            out[a.job] = out.get(a.job, 0) + 1
    return out


def _join_names(names: List[str]) -> str:
    names = list(dict.fromkeys(names))
    if len(names) <= 1:
        return "".join(names)
    if len(names) > 4:
        return ", ".join(names[:3]) + f" and {len(names) - 3} others"
    return ", ".join(names[:-1]) + " and " + names[-1]
