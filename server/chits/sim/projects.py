"""Village projects (Civilization, Settlers): one shared goal the whole village works towards.

Progress used to be mostly luck: a new thing appeared when some chit happened to combine the right items. A project
gives the village something to be "next": the next step on the road to its next age (a discovery, a building, or
enough of a made material for that building: "make 4 iron for the forge"), or a building it lacks. The chief names it
(a model chief may, in its weekly reflection), the elder picks it where chits can't talk, and failing both the
village picks it by need. It is tracked, it is one line in every chit's scene, and instinct weighs helping it.

This module also holds the village's shared state (``world.civic``) for research (research.py) and for wants and
renown (wants.py), and runs their periodic upkeep, so the world needs only a few small hooks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .agent import TICKS_PER_DAY, Agent
from .items import DESIGNS, GATHER_RULES, RECIPES, STORES, item_name, normalize_design

STALL_DAYS = 8  # a project nobody has moved for this long is given up on...
SKIP_DAYS = 4  # ...and isn't picked again for a while
DISCOVER_DAYS = 6  # a discovery the village hasn't made in this long is set aside too
DONE_KEEP = 30
ASK_DAYS = 1  # a model chief has this long to choose the next project before the village's need does
ASK_N = 4  # candidates put to the chief

# what a village lacks, and how much it matters (before the leader's own leanings)
LACKING = {"stockpile": 2.0, "farm": 2.2, "workshop": 2.2, "kiln": 2.2, "furnace": 2.5, "library": 1.8, "forge": 2.2,
           "factory": 2.0, "market": 1.0, "pen": 0.8, "brick_house": 1.0, "monument": 1.0,
           "great_library": 1.2, "aqueduct": 1.2, "lighthouse": 0.8,  # great works need many hands (min_pop)
           # the later ages: a village works together to make the steel, gears and engine these need (on their own,
           # chits knew them but always had a project or a meal to see to first)
           "steam_pump": 1.6, "sawmill": 1.4, "printing_press": 1.8, "power_station": 2.0, "street_lamp": 0.8,
           "town_hall": 1.8}
NEXT_AGE = 4.0  # the next step on the road to the next age
SITE_SIGHT = 12  # where chits can't talk, a building project is known by those who can see its site going up
STATION_DESIGN = {"fire": "campfire", "kiln": "kiln", "workshop": "workshop", "furnace": "furnace", "forge": "forge",
                  "factory": "factory", "loom": "tailor"}

Step = Tuple[str, str, Dict[str, Any]]  # ("discover" | "build" | "make", key, {"n": .., "for": design} for "make")


# ---------------------------------------------------------------------------------------------- shared state
def init(world) -> None:
    world.civic = {"project": None, "done": [], "skip": {}, "seq": 0, "insight": 0.0, "hints": [], "hints_given": 0,
                   "renown_seq": world.seq}


def save(world) -> Dict[str, Any]:
    return dict(getattr(world, "civic", None) or {})


def load(world, d: Dict[str, Any]) -> None:
    init(world)
    world.civic.update(d.get("civic") or {})
    if not (d.get("civic") or {}).get("renown_seq"):
        world.civic["renown_seq"] = world.seq  # an older save: don't hand out renown for its whole history


def tick(world) -> None:
    """Every 10 ticks (world.step): the project's progress, hints that came true, wishes that came true, renown."""
    from . import research, wants

    if not hasattr(world, "civic"):
        init(world)
    _track(world)
    _expire_ask(world)
    from . import ballots

    ballots.tick(world)
    research.tick(world)
    wants.tick(world)


def new_day(world) -> None:
    from . import wants

    if not hasattr(world, "civic"):
        init(world)
    if world.civic.get("project") is None and not world.civic.get("ask"):
        next_project(world)
    wants.new_day(world)


# ---------------------------------------------------------------------------------------------- the road ahead
def _known(world) -> Tuple[set, set]:
    designs, recipes = set(), set()
    for a in world.agents.values():
        for k in a.knows:
            kind, key = k.split(":", 1)
            (designs if kind == "design" else recipes).add(key)
    return designs, recipes


def _stations(world) -> set:
    out: set = set()
    for s in world.structures.values():
        if s.functional:
            out |= {s.design} | s.stations()
    return out


def stock(world, key: str, for_design: Optional[str] = None) -> int:
    """How much of a thing the village has: in its stockpiles, in hand, and (for `for_design`) already delivered to
    an unfinished site of that building."""
    n = sum(s.storage.get(key, 0) for s in world.structures.values() if s.design in STORES and s.functional)
    n += sum(a.inventory.get(key, 0) for a in world.agents.values())
    if for_design:
        need = DESIGNS[for_design].material_map.get(key, 0)
        n += sum(max(0, need - s.needs.get(key, 0)) for s in world.structures.values()
                 if s.design == for_design and not s.complete)
    return n


def made(a: Agent, key: str) -> int:
    """How many batches of a thing a chit has made: by hand (crafting) or in shifts at a station (production)."""
    return a.stats.get(f"made_{key}", 0) + a.stats.get(f"produced_{key}", 0)


def _station_missing(have: set, station: Optional[str]) -> Optional[str]:
    st = STATION_DESIGN.get(station or "")
    return st if station and station not in have and st not in have else None


def imaginers(world, d) -> List[Agent]:
    """Chits who know all that `d` takes but for the things it's made from (they'd imagine it on handling them)."""
    def ok(a: Agent, pk: str, pv: str) -> bool:
        return pk == "item" or (pk == "recipe" and a.knows_recipe(pv)) or (pk == "design" and a.knows_design(pv)) \
            or (pk == "belief" and bool(a.belief))

    return [a for a in world.agents.values() if all(ok(a, pk, pv) for pk, pv in d.prereqs)]


def _unhandled(world, d) -> Optional[str]:
    """A raw thing that must be handled before anyone can imagine building `d` (a furnace takes someone who knows
    bricks and has held copper ore): the first one none of the chits who know the rest has handled."""
    items = [pv for pk, pv in d.prereqs if pk == "item" and pv in GATHER_RULES]
    if not items:
        return None
    handled = set().union(*(a.familiar for a in imaginers(world, d)))
    return next((pv for pv in items if pv not in handled), None)


def next_step(world, designs: set, recipes: set, have: set, kind: str, key: str, depth: int = 0,
              make: bool = True) -> Optional[Step]:
    """The first step still to take towards `key`: discover a recipe, build a building, make enough of a known
    material for a building, or find a raw thing nobody has handled yet. None once it's done, or while it's out of
    reach. A recipe needs its inputs and its station first; a building needs its materials known, someone who can
    imagine it (who knows what it takes, and has handled what it's made from), and (with `make`) enough of each
    made material. (The world knows its own laws; chits only ever hear the step, not the road.)"""
    if depth > 6:
        return None
    if kind == "recipe":
        r = RECIPES.get(key)
        if r is None or key in recipes:
            return None
        for k, _ in r.inputs:
            if k in RECIPES and k not in recipes:
                return next_step(world, designs, recipes, have, "recipe", k, depth + 1, make)
        st = _station_missing(have, r.station)
        if st:
            return next_step(world, designs, recipes, have, "design", st, depth + 1, make)
        if make:
            # its made ingredients, in hand or in store, before anyone can try for it: World A sought the dynamo for
            # 700 days with no steam engine anywhere in its stores
            for k, n in r.inputs:
                if k in RECIPES and stock(world, k) < n:
                    st = _station_missing(have, RECIPES[k].station)
                    if st:
                        return next_step(world, designs, recipes, have, "design", st, depth + 1, make)
                    return "make", k, {"n": n, "try": key}
        return "discover", key, {}
    d = DESIGNS.get(key)
    if d is None or key in have:
        return None
    for m, _ in d.materials:
        if m not in GATHER_RULES and m not in recipes:
            return next_step(world, designs, recipes, have, "recipe", m, depth + 1, make)
    if key not in designs:
        for pk, pv in d.prereqs:
            if pk == "recipe" and pv not in recipes:
                return next_step(world, designs, recipes, have, "recipe", pv, depth + 1, make)
        raw = _unhandled(world, d)
        return ("find", raw, {"for": key}) if raw else None  # otherwise nobody has had the idea yet
    if len(world.agents) < d.min_pop:
        return None
    if make:
        for m, n in d.materials:
            if m in RECIPES and stock(world, m, key) < n:  # a made thing the village hasn't enough of yet
                st = _station_missing(have, RECIPES[m].station)
                if st:
                    return next_step(world, designs, recipes, have, "design", st, depth + 1, make)
                return "make", m, {"n": n, "for": key}
    return "build", key, {}


def road(world) -> Optional[Dict[str, Any]]:
    """The road to the next age for the observer: each thing on it, done or not, and what a building still needs.
    'Machine Age: iron ✓ · forge ✗ (needs 3 more iron, 10 more brick) · steel ✗ · gear ✗ · steam engine ✗'."""
    from .world import ERAS

    i, _ = world.era()
    if i + 1 >= len(ERAS):
        return None
    age, target = ERAS[i + 1]
    designs, recipes = _known(world)
    have = _stations(world)
    steps: List[Dict[str, Any]] = []
    seen: set = set()

    def done(kind: str, key: str) -> bool:
        return key in recipes if kind == "recipe" else key in have

    def name(kind: str, key: str) -> str:
        return item_name(key) if kind == "recipe" else DESIGNS[key].name

    def visit(kind: str, key: str, depth: int) -> None:
        if (kind, key) in seen or depth > 8:
            return
        seen.add((kind, key))
        if kind == "recipe":
            r = RECIPES[key]
            kids = [("recipe", k) for k, _ in r.inputs if k in RECIPES]
            st = _station_missing(have, r.station)
            kids += [("design", st)] if st else []
            needs = ""
        else:
            d = DESIGNS[key]
            kids = [("recipe", m) for m, _ in d.materials if m in RECIPES]
            kids += [("recipe", pv) for pk, pv in d.prereqs if pk == "recipe"]
            short = [(m, n - stock(world, m, key)) for m, n in d.materials if m in RECIPES and stock(world, m, key) < n]
            parts = [("needs " + ", ".join(f"{n} more {item_name(m)}" for m, n in short))] if short else []
            if key not in designs:
                raw = _unhandled(world, d)
                parts.insert(0, f"nobody has handled {item_name(raw)} yet" if raw else "nobody has had the idea yet")
            needs = "; ".join(parts)
        for k in kids:
            if done(*k):
                if k not in seen and k[0] == "recipe":  # a ready input: shown, not followed further
                    seen.add(k)
                    steps.append({"kind": k[0], "key": k[1], "name": name(*k), "done": True, "needs": ""})
            else:
                visit(k[0], k[1], depth + 1)
        steps.append({"kind": kind, "key": key, "name": name(kind, key), "done": False, "needs": needs})

    kind, key = target.split(":", 1)
    if done(kind, key):
        return None
    visit(kind, key, 0)
    text = f"{age}: " + " · ".join(f"{s['name']} {'✓' if s['done'] else '✗'}" + (f" ({s['needs']})" if s["needs"] else "")
                                   for s in steps)
    return {"age": age, "steps": steps, "text": text}


# ---------------------------------------------------------------------------------------------- choosing
Cand = Tuple[float, str, str, str, Dict[str, Any]]


def _utility_site(world, d: str) -> Optional[Tuple[int, int]]:
    """Where a machine-age building would do its work, or None where it would do none: a steam pump among farms, a
    sawmill by the woods, a press by a library, a power station by the benches, a lamp where wolves come. As a bare
    project they went up wherever their builder stood (a pump with no farm near, Codex #23); instinct's own plans for
    them (brain/builder.py) ask the same."""
    from . import pioneers

    vs = [v for v in pioneers.villages(world) if v.residents]
    if vs:  # the biggest settlement's middle; before there is one, the middle of everyone
        v = max(vs, key=lambda v: (len(v.residents), v.id))
        cx, cy = int(v.x), int(v.y)
    elif world.agents:
        cx = round(sum(o.x for o in world.agents.values()) / len(world.agents))
        cy = round(sum(o.y for o in world.agents.values()) / len(world.agents))
    else:
        return None
    near = world.structures_near(cx, cy, 25)
    if d == "steam_pump":
        farms = [s for s in near if s.design == "farm" and s.functional]
        return (round(sum(f.x for f in farms) / len(farms)), round(sum(f.y for f in farms) / len(farms))) if len(farms) >= 2 else None
    if d == "sawmill":
        return world.nearest_resource(cx, cy, "wood", 20)
    if d == "printing_press":
        lib = next((s for s in near if s.design == "library" and s.functional), None)
        return (lib.x, lib.y) if lib else None
    if d == "power_station":
        st = next((s for s in near if s.functional and s.stations() & POWERED_STATIONS), None)
        return (st.x, st.y) if st else None
    if d == "street_lamp":
        wolves = any(w["kind"] == "wolf" and max(abs(w["x"] - cx), abs(w["y"] - cy)) <= 25
                     for w in getattr(world, "animals", {}).values())
        return (cx, cy) if wolves else None
    return None


UTILITY = ("steam_pump", "sawmill", "printing_press", "power_station", "street_lamp")
POWERED_STATIONS = {"workshop", "kiln", "furnace", "forge", "mill", "factory"}


def candidates(world) -> List[Cand]:
    """(score, kind, key, why, extra) for every project the village could take on now: the next step on the road to
    the next age, or a building someone knows and the village lacks."""
    designs, recipes = _known(world)
    have = _stations(world)
    sites = {s.design for s in world.structures.values() if not s.complete}
    pop = len(world.agents)
    skip = world.civic.get("skip", {})
    out: Dict[Tuple[str, str], Tuple[float, str, Dict[str, Any]]] = {}

    def add(score: float, kind: str, key: str, why: str, extra: Dict[str, Any]) -> None:
        if skip.get(f"{kind}:{key}", 0) > world.tick:
            return
        if (kind, key) not in out or out[(kind, key)][0] < score:
            out[(kind, key)] = (score, why, extra)

    from .world import ERAS

    i, _ = world.era()
    if i + 1 < len(ERAS):
        kind, key = ERAS[i + 1][1].split(":", 1)
        step = next_step(world, designs, recipes, have, kind, key)
        if step:
            why = f"on the road to the {ERAS[i + 1][0]}"
            if step[0] in ("make", "find") and step[2].get("for") in DESIGNS:
                why = f"for a {DESIGNS[step[2]['for']].name}, " + why
            elif step[0] == "make":
                why = "to try for something new, " + why
            add(NEXT_AGE, step[0], step[1], why, step[2])
    for d, score in LACKING.items():
        if next_step(world, designs, recipes, have, "design", d, make=False) != ("build", d, {}):
            continue
        if d == "pen" and not any(x["kind"] == "sheep" for x in getattr(world, "animals", {}).values()):
            continue
        if (d == "market" and pop < 10) or (d == "monument" and pop < 12):
            continue
        extra: Dict[str, Any] = {}
        if d in UTILITY:
            spot = _utility_site(world, d)
            if spot is None:
                continue  # (nothing for it to do yet)
            extra = {"near": f"{spot[0]},{spot[1]}"}
        add(score + (0.5 if d in sites else 0.0), "build", d, "the village has none", extra)
    return sorted(((s, k, key, why, ex) for (k, key), (s, why, ex) in out.items()), key=lambda c: (-c[0], c[1], c[2]))


def title(p: Dict[str, Any]) -> str:
    """The project as the observer sees it (the real names)."""
    if p["kind"] == "build":
        return f"build a {DESIGNS[p['key']].name}"
    if p["kind"] == "make":
        if p.get("for") not in DESIGNS:  # (an ingredient to try for a discovery, not a building's material)
            return f"make {p['n']} {item_name(p['key'])} to try for something new"
        return f"make {p['n']} {item_name(p['key'])} for a {DESIGNS[p['for']].name}"
    if p["kind"] == "find":
        return f"find {item_name(p['key'])} for a {DESIGNS[p['for']].name}"
    return f"discover how to make {item_name(p['key'])}"


def _heard(p: Dict[str, Any]) -> str:
    """The project as chits hear it: a thing nobody has seen is described by what it is like, not named."""
    if p["kind"] == "discover":
        return f"discover {_riddle(p['key'])}"
    if p["kind"] == "find":
        return f"find {_riddle(p['key'])} (nobody here has handled any yet)"
    return title(p)


def _riddle(key: str) -> str:
    """What a thing is like, never its name or how it's made: "something black that burns very hot"."""
    from .items import ITEMS
    from .research import _VERBISH

    props = list(ITEMS[key].props)
    noun = next((p for p in props if p in ("container", "tool")), "")
    adj = [p for p in props if p != noun and (p.startswith("very ") or (" " not in p and p not in _VERBISH))]
    rest = [p for p in props if p != noun and p not in adj]
    that = [p for p in rest if p.split(" ", 1)[0] in _VERBISH]
    with_ = [p for p in rest if p not in that]

    def join(ws: List[str]) -> str:
        return ws[0] if len(ws) == 1 else ", ".join(ws[:-1]) + " and " + ws[-1]

    if noun:
        head = " ".join(adj[:2] + [noun])
        out = ("an " if head[:1] in "aeiou" else "a ") + head
    else:
        out = "something" + (f" {join(adj[:3])}" if adj else "" if rest else " new")
    if with_:
        out += f" with {join(with_[:1])}"
    if that:
        out += f" that {join(that[:2])}"
    return out


def pick(world, reason: str = "") -> Optional[Dict[str, Any]]:
    """The village's need sets the next project. This is the world's own choice, so it is never presented as anyone's
    call: it used to be announced as "Chief X called on..." (and "your call" in the chief's scene) when no model had
    chosen anything. A model chief sets the project itself in its reflection (name_project)."""
    cands = candidates(world)
    if not cands:
        return None
    rng = world.rng_for("projects")
    scored = [(score + rng.random() * 0.3, kind, key, why, extra) for score, kind, key, why, extra in cands]
    score, kind, key, why, extra = max(scored, key=lambda c: c[0])
    if reason:  # need decided because a chief's choice didn't come: say so (a model's decision never silently becomes the world's)
        extra = {**(extra or {}), "fallback": reason}
        world.civic["fallbacks"] = world.civic.get("fallbacks", 0) + 1
    return start(world, kind, key, why, None, "need", extra)


def start(world, kind: str, key: str, why: str, leader: Optional[Agent], by: str,
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    world.civic["seq"] = world.civic.get("seq", 0) + 1
    p = {"id": f"p{world.civic['seq']}", "kind": kind, "key": key, "why": why, "by": leader.id if leader else "",
         "by_name": leader.name if leader else "", "chosen_by": by, "tick": world.tick, "site": "", "seen": {},
         "exp": {a.id: a.stats.get("experiments", 0) for a in world.agents.values()}, "attempts": 0,
         "helpers": {}, "last_progress": world.tick, **(extra or {})}
    if kind == "make":
        p["made"] = {a.id: made(a, key) for a in world.agents.values()}
        p["made0"], p["best"] = dict(p["made"]), stock(world, key, p.get("for"))
    if kind == "find":
        p["went"] = {a.id: a.stats.get("explored", 0) for a in world.agents.values()}
    world.civic["project"] = p
    what = title(p)
    if by == "chief":
        text = f"Chief {leader.name} called on {world.name} to {what}"
    elif by == "elder":
        text = f"The elder {leader.name} set {world.name} to work: {what}"
    else:
        text = f"{world.name} turned to a new project: {what} ({why})"
        if p.get("fallback"):
            text += f"; chosen by need because {p['fallback']}"
    world.emit("project", text, 4, leader.id if leader else None, leader.x if leader else None,
               leader.y if leader else None, project=p["id"], what=kind, key=key, chosen_by=by,
               fallback=p.get("fallback", ""))
    return p


# ---------------------------------------------------------------------------------------------- the chief's choice
def next_project(world, reason: str = "") -> Optional[Dict[str, Any]]:
    """No project: where chits talk and the chief thinks with a model, the choice is put to it (the Mind sends it
    as a one-letter choice: a model decision, recorded like any other); otherwise the village's need picks."""
    cands = candidates(world)
    if not cands:
        return None
    leader = world.agents.get(getattr(world, "leader", "") or "")
    if leader is not None and leader.brain != "instinct" and world.flags.get("say"):
        world.civic["ask"] = {"leader": leader.id, "tick": world.tick, "sent": False,
                              "options": [{"kind": k, "key": key, "why": why, "extra": dict(ex)}
                                          for _, k, key, why, ex in cands[:ASK_N]]}
        from .. import diag

        diag.chief(world, "asked", world.civic["ask"])
        return None
    return pick(world, reason)


def option_words(o: Dict[str, Any]) -> str:
    """A candidate project as the chief hears it (never an undiscovered thing's name)."""
    return _heard({"kind": o["kind"], "key": o["key"], **o.get("extra", {})})


def answer(world, leader_id: str, index: int) -> Optional[Dict[str, Any]]:
    """The chief's model chose option `index`: start it as the chief's call, if the question still stands and the
    option is still something the village can take on (the world checks; the model only chooses)."""
    ask = world.civic.get("ask")
    if not ask or ask["leader"] != leader_id or world.civic.get("project") or not 0 <= index < len(ask["options"]):
        return None  # (the Mind logs this as "stale on arrival")
    o = ask["options"][index]
    world.civic["ask"] = None
    if (o["kind"], o["key"]) not in {(c[1], c[2]) for c in candidates(world)}:
        return pick(world, "the chief's choice could no longer be done")
    return start(world, o["kind"], o["key"], o["why"], world.agents.get(leader_id), "chief", o.get("extra"))


def _expire_ask(world) -> None:
    """A question the chief never answered (no model reply, a new chief, or the chief died): need decides."""
    ask = world.civic.get("ask")
    if ask and (world.tick - ask["tick"] > ASK_DAYS * TICKS_PER_DAY or ask["leader"] not in world.agents
                or getattr(world, "leader", "") != ask["leader"]):
        world.civic["ask"] = None
        why = ("the chief changed before choosing" if ask["leader"] not in world.agents
               or getattr(world, "leader", "") != ask["leader"]
               else "the chief's mind didn't answer" if ask.get("sent") else "the chief's mind was never asked (unavailable)")
        from .. import diag

        diag.chief(world, "expired: " + why, ask, end=True)
        if world.civic.get("project") is None:
            pick(world, why)


def ideas(world, n: int = 3) -> List[str]:
    """What a chief could name as the next project, in the words chits use."""
    return [_heard({"kind": kind, "key": key, **extra}) for _, kind, key, _, extra in candidates(world)[:n]]


def name_project(world, a: Agent, text: Any) -> bool:
    """A model chief names the village's project in its reflection. It must be something the village could take
    on now (one of the candidates): named by its building or item, or in the words of ``ideas``."""
    if a.id != getattr(world, "leader", "") or not world.flags.get("say"):
        return False
    norm = lambda s: " ".join("".join(c if c.isalnum() or c in " _-" else " " for c in str(s or "").lower()).split())
    said = norm(text)
    raw = said
    for p in ("build a ", "build an ", "build the ", "build ", "raise a ", "discover how to make ", "discover ",
              "make a ", "make ", "find ", "a ", "an ", "the "):
        if raw.startswith(p):
            raw = raw[len(p):]
            break
    d = normalize_design(raw)
    k = world.norm_item(raw) if hasattr(world, "norm_item") else None
    for _, kind, key, why, extra in candidates(world):
        words = norm(_heard({"kind": kind, "key": key, **extra}))
        # an undiscovered thing is named only in the riddle's words: its real name would be the model's prior
        # knowledge choosing for the village (audit F4); what is built or made is known, so its name will do
        if said == words or (kind == "build" and key == d) or (kind == "make" and key == k):
            cur = world.civic.get("project")
            if cur and cur["kind"] == kind and cur["key"] == key:
                return False
            start(world, kind, key, why, a, "chief", extra)
            return True
    return False


# ---------------------------------------------------------------------------------------------- progress
def _site(world, p: Dict[str, Any]):
    s = world.structures.get(p.get("site") or "")
    if s is not None and s.design == p["key"]:
        return s
    sites = [x for x in world.structures.values() if x.design == p["key"] and not x.complete]
    if not sites:
        return None
    s = max(sites, key=lambda x: (sum(x.builders.values()), x.work_done))
    p["site"], p["seen"] = s.id, {}
    return s


def _moved(p: Dict[str, Any], counts: Dict[str, int], field: str, world) -> int:
    """How much a per-chit counter rose since the last look; who moved it counts as helping."""
    seen = p.setdefault(field, {})
    total = 0
    for aid, n in counts.items():
        if n > seen.get(aid, 0):
            total += n - seen.get(aid, 0)
            p["last_progress"] = world.tick
            a = world.agents.get(aid)
            if a is not None and knows(world, a, p):  # (an experiment by a chit that never heard of it isn't help)
                p["helpers"][aid] = world.tick
        seen[aid] = n
    return total


def _track(world) -> None:
    p = world.civic.get("project")
    if not p:
        return
    t = world.tick
    if p["kind"] == "build":
        done = next((s for s in world.structures.values() if s.design == p["key"] and s.functional
                     and s.completed >= p["tick"]), None)
        if done is not None:
            return complete(world, done)
        s = _site(world, p)
        if s is not None:
            _moved(p, dict(s.builders), "seen", world)
    elif p["kind"] == "make":
        _moved(p, {a.id: made(a, p["key"]) for a in world.agents.values()}, "made", world)
        have = stock(world, p["key"], p.get("for"))
        if have > p.get("best", 0):
            p["best"], p["last_progress"] = have, t
        if have >= p["n"]:
            return complete(world, None)
    elif p["kind"] == "find":
        if any(p["key"] in a.familiar for a in imaginers(world, DESIGNS[p["for"]])):
            return complete(world, None)
        p["attempts"] += _moved(p, {a.id: a.stats.get("explored", 0) for a in world.agents.values()}, "went", world)
    else:
        if any(a.knows_recipe(p["key"]) for a in world.agents.values()):
            return complete(world, None)
        p["attempts"] += _moved(p, {a.id: a.stats.get("experiments", 0) for a in world.agents.values()}, "exp", world)
    # a discovery (or a search) is "moved on" by every try, so it also has a limit: it may not be possible here yet
    too_long = p["kind"] in ("discover", "find") and t - p["tick"] > DISCOVER_DAYS * TICKS_PER_DAY
    if too_long or t - p["last_progress"] > STALL_DAYS * TICKS_PER_DAY:
        world.civic["skip"][f"{p['kind']}:{p['key']}"] = t + SKIP_DAYS * TICKS_PER_DAY
        world.civic["project"] = None
        world.emit("project", f"{world.name} set aside its project to {title(p)}: nobody could move it on",
                   2, project=p["id"], abandoned=True)


def helpers(world, p: Dict[str, Any]) -> List[str]:
    """Chits working on the project now: planning a step for it, or who moved it on in the last day."""
    t = world.tick
    ids = {aid for aid, when in p.get("helpers", {}).items() if t - when <= TICKS_PER_DAY and aid in world.agents}
    ids |= {a.id for a in world.agents.values() if any(s.get("_proj") == p["id"] for s in a.plan)}
    return sorted(ids)


def complete(world, structure) -> None:
    from . import wants
    from .world import _join_names

    p = world.civic["project"]
    t = world.tick
    x = y = actor = None

    def knew(aid: str) -> bool:
        return aid in world.agents and knows(world, world.agents[aid], p)

    if p["kind"] == "build":
        contrib = {aid: n for aid, n in (structure.builders if structure else {}).items() if aid in world.agents}
        total = sum(contrib.values()) or 1.0
        for aid, n in contrib.items():
            wants.add_renown(world, world.agents[aid], 1.0 + 3.0 * n / total)
        names = [world.agents[aid].name for aid, _ in sorted(contrib.items(), key=lambda kv: -kv[1])]
        text = f"Village project done: {_join_names(names) or 'the village'} built the {DESIGNS[p['key']].name}"
        x, y = structure.center() if structure else (None, None)
        actor = max(contrib, key=contrib.get) if contrib else None
    elif p["kind"] == "make":
        made = {aid: n - p.get("made0", {}).get(aid, 0) for aid, n in p.get("made", {}).items()}
        contrib = {aid: 1.0 for aid in p.get("helpers", {}) if knew(aid)}
        for aid in contrib:
            wants.add_renown(world, world.agents[aid], 1.0)
        names = [world.agents[aid].name for aid in sorted(contrib, key=lambda i: -made.get(i, 0))]
        text = (f"Village project done: {p['n']} {item_name(p['key'])} are ready "
                + (f"for the {DESIGNS[p['for']].name}" if p.get("for") in DESIGNS else "to try for something new")
                + (f", made by {_join_names(names)}" if names else ""))
        actor = max(contrib, key=lambda i: made.get(i, 0)) if contrib else None
    elif p["kind"] == "find":
        finders = [a for a in imaginers(world, DESIGNS[p["for"]]) if p["key"] in a.familiar]
        finder = next((a for a in finders if a.id in p.get("helpers", {})), finders[0] if finders else None)
        contrib = {aid: 1.0 for aid in p.get("helpers", {}) if knew(aid)}
        if finder is not None and knew(finder.id):
            contrib[finder.id] = 3.0
            wants.add_renown(world, finder, 3.0)
        who = finder.name if finder else "someone"
        text = f"Village project done: {who} found {item_name(p['key'])}, what a {DESIGNS[p['for']].name} is made from"
        x, y = (finder.x, finder.y) if finder else (None, None)
        actor = finder.id if finder else None
    else:
        kk = f"recipe:{p['key']}"
        finder = min((a for a in world.agents.values() if kk in a.knows), key=lambda a: a.knows[kk]["tick"], default=None)
        contrib = {aid: 1.0 for aid in p.get("helpers", {}) if knew(aid)}
        if finder is not None and knew(finder.id):
            contrib[finder.id] = 4.0
            wants.add_renown(world, finder, 3.0)
        for aid in contrib:
            if finder is None or aid != finder.id:
                wants.add_renown(world, world.agents[aid], 0.5)
        who = finder.name if finder else "someone"
        how = {"discovered": "discovered", "read": "read on an old tablet"}.get(finder.knows[kk]["how"], "found out") \
            if finder else "found out"
        text = f"Village project done: {who} {how} how to make {item_name(p['key'])}, after {p['attempts']} tries by the village"
        x, y = (finder.x, finder.y) if finder else (None, None)
        actor = finder.id if finder else None
    if p.get("by_name"):
        text += f" ({p['chosen_by']} {p['by_name']}'s call)"
    for aid in contrib:
        a = world.agents[aid]
        a.mood = min(100.0, a.mood + 10)
        a.remember(t, f"Our village's project is done ({title(p)}), and I helped", 4, "project")
    world.emit("project_done", text, 5, actor or None, x, y, project=p["id"], what=p["kind"], key=p["key"],
               helpers=sorted(contrib), chosen_by=p["chosen_by"],
               evidence="multi_contributor" if len(contrib) >= 2 else "")
    world.civic["done"].append({"id": p["id"], "kind": p["kind"], "key": p["key"], "day": t // TICKS_PER_DAY + 1,
                                "started_day": p["tick"] // TICKS_PER_DAY + 1, "text": text, "helpers": len(contrib),
                                "chosen_by": p["chosen_by"], "by_name": p.get("by_name", "")})
    del world.civic["done"][:-DONE_KEEP]
    world.civic["project"] = None
    next_project(world, "done")


# ---------------------------------------------------------------------------------------------- showing it
def status(world, p: Dict[str, Any]) -> Tuple[str, float]:
    """How far along it is, in words, and as 0..1 (for the progress bar)."""
    if p["kind"] == "discover":
        n = p.get("attempts", 0)
        return f"{n} experiment{'s' if n != 1 else ''} so far", min(0.9, n / 40.0)
    if p["kind"] == "make":
        have = stock(world, p["key"], p.get("for"))
        return f"the village has {min(have, p['n'])} of {p['n']}", min(1.0, have / max(1, p["n"]))
    if p["kind"] == "find":
        n = p.get("attempts", 0)
        return f"{n} search{'es' if n != 1 else ''} so far", min(0.9, n / 20.0)
    s = world.structures.get(p.get("site") or "")
    d = DESIGNS[p["key"]]
    total = sum(n for _, n in d.materials)
    if s is None or s.complete:
        need = ", ".join(f"{n} {item_name(k)}" for k, n in d.materials)
        return f"no site yet (needs {need})", 0.0
    left = sum(s.needs.values())
    frac = 0.5 * (1 - left / max(1, total)) + 0.5 * min(1.0, s.work_done / max(1.0, s.work_total))
    if s.needs:
        need = ", ".join(f"{n} more {item_name(k)}" for k, n in s.needs.items())
        return f"site {s.id} at ({s.x},{s.y}) needs {need}", frac
    return f"site {s.id} at ({s.x},{s.y}) has all its materials, {int(100 * s.work_done / max(1, s.work_total))}% built", frac


def knows(world, a: Agent, p: Optional[Dict[str, Any]] = None) -> bool:
    """Who knows the village's project. Where chits talk, word gets round. Where they can't (a culture without
    speech), a project is not a thing that can be told: only the chit that chose it knows it, and anyone who can see
    the site of a building project going up. (Every chit's scene used to carry it, a channel World B doesn't have.)"""
    p = p if p is not None else (getattr(world, "civic", None) or {}).get("project")
    if not p:
        return False
    if world.flags.get("say") or p.get("by") == a.id:
        return True
    if p["kind"] != "build":
        return False
    s = world.structures.get(p.get("site") or "")
    return s is not None and not s.complete and max(abs(s.x - a.x), abs(s.y - a.y)) <= SITE_SIGHT


def scene_line(world, a: Agent) -> str:
    p = (getattr(world, "civic", None) or {}).get("project")
    if not p or not knows(world, a, p):
        return ""
    call = f"{p['chosen_by']} {p['by_name']}'s call" if p.get("by_name") else "chosen by need"
    if p.get("fallback"):
        call += f", because {p['fallback']}"
    if p.get("by") == a.id:
        call = "your call"
    words, _ = status(world, p)
    n = len(helpers(world, p))
    line = f"Village project: {_heard(p)} ({call}) — {words}; {n} chit{'s' if n != 1 else ''} helping."
    from . import food

    if food.short(world, a):
        line += " It waits while the stores run low: food first."
    return line


def view(world) -> Optional[Dict[str, Any]]:
    """The project for the observer (views.progress)."""
    civ = getattr(world, "civic", None) or {}
    p = civ.get("project")
    done = list(reversed(civ.get("done", [])))[:5]
    if not p:
        return {"active": None, "done": done}
    words, frac = status(world, p)
    return {"active": {"id": p["id"], "kind": p["kind"], "key": p["key"], "title": title(p),
                       "why": p["why"], "chosen_by": p["chosen_by"], "by": p.get("by_name", ""),
                       "since_day": p["tick"] // TICKS_PER_DAY + 1, "status": words, "progress": round(frac, 3),
                       "helpers": len(helpers(world, p)), "attempts": p.get("attempts", 0)},
            "done": done}
