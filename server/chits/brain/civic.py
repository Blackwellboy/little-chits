"""Instinct's side of village life: help the village's project, study at the library, try the scholars' hint, lean
towards what you want, and imitate the village's most renowned chit.

``extend`` adds weighted options to (and reweighs) the list instinct's ``_progress`` draws from. Like everything
instinct does, it only uses what the chit could know: its own village's project (``projects.current``) where it knows
of it (``projects.knows``: word of mouth where chits talk, the site in sight where they can't), hints as ``research.active_hints`` allows, and a hint
names properties, so the chit matches them against things it has handled.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..sim import research, wants
from ..sim.agent import Agent
from ..sim.actions import STATION_NEAR, STATION_REACH
from ..sim.items import DESIGNS, STATIONS, item_name

Opt = Tuple[float, Dict[str, Any]]

PROJECT_W = 3.0  # helping the village's project, before the chit's own nature
STUDY_W = 0.6
HINT_W = 3.0
WANT_BIAS = 1.6
IMITATE_BIAS = 1.4
DUTY = 0.2  # how often the project comes before idle talk, before diligence
FOOD_FIRST = 0.3  # a project's weight while the stores near a chit run low (sim/food.py)


def extend(ins, world, a: Agent, rng, opts: List[Opt]) -> List[Opt]:
    from ..sim import food

    if not hasattr(world, "civic"):
        return opts
    project = project_options(ins, world, a, rng)
    if project and food.short(world, a):
        project = [(w * FOOD_FIRST, o) for w, o in project]  # the project waits while the stores run low
    opts = opts + project + research_options(ins, world, a, rng) + lore_options(ins, world, a, rng)
    return imitation_bias(world, a, want_bias(world, a, opts))


def _tag(plan: Optional[Dict[str, Any]], pid: str) -> Optional[Dict[str, Any]]:
    if plan:
        plan["steps"] = [dict(s, _proj=pid) for s in plan["steps"] if s]
    return plan


def project_options(ins, world, a: Agent, rng) -> List[Opt]:
    from .instinct import _need_steps, _reachable

    from ..sim import projects

    p = projects.current(world, a)
    if not p or a.is_child(world.tick) or not projects.knows(world, a, p):
        return []
    tr = a.traits
    if p["kind"] == "build":
        name = DESIGNS[p["key"]].name
        site = world.structures.get(p.get("site") or "")
        if site is not None and not site.complete:
            if not _reachable(world, a, site) or not ins._can_supply(world, a, site):
                return []
            plan = ins._help_site(a, site, f"help build the village's {name}", f"The whole village is raising a {name}. I'll do my part.")
            return [(PROJECT_W + 1.5 * tr.get("diligence", 0.5), _tag(plan, p["id"]))]
        if not a.knows_design(p["key"]) or a.reflex_rest.get("nobuild:" + p["key"], 0) > world.tick:
            return []
        mats = DESIGNS[p["key"]].material_map
        steps = _need_steps(a, mats, world)
        if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
            return []  # can't source the materials
        plan = {"goal": f"start the village's {name}", "thought": f"We agreed on a {name}. Someone has to start it.",
                "steps": steps[:4] + [dict({"do": "build", "what": p["key"]}, **({"near": p["near"]} if p.get("near") else {}))]}
        return [(PROJECT_W, _tag(plan, p["id"]))]
    if p["kind"] == "make":
        plan = make_plan(world, a, p)
        if not plan:
            return []
        w = PROJECT_W + 1.5 * tr.get("diligence", 0.5) if a.knows_recipe(p["key"]) else 1.0 + tr.get("diligence", 0.5)
        return [(w, _tag(plan, p["id"]))]
    if p["kind"] == "find":
        plan = find_plan(world, a, p, rng)
        return [(1.5 + 2.0 * tr.get("curiosity", 0.5), _tag(plan, p["id"]))] if plan else []
    exp = project_experiment(ins, world, a, rng, p["key"])
    if not exp:
        return []
    exp["goal"] = "experiment for the village's discovery"
    exp["thought"] = "The village is looking for something new. Maybe this is it."
    return [(1.0 + 2.0 * tr.get("curiosity", 0.5), _tag(exp, p["id"]))]


def duty(ins, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
    """The village's project, ahead of idle talk and odd jobs, some of the time (more for the diligent). Called by
    instinct's communal planner after the winter food store: projects only ever showed up among the options of a
    chit with nothing else to do, and a busy village never got to them (World B made iron once in 300 days)."""
    from ..sim import food, projects

    p = projects.current(world, a)
    if not p or rng.random() > DUTY + 0.3 * a.traits.get("diligence", 0.5) or food.short(world, a):
        return None  # (with the stores running low, filling them comes first)
    opts = project_options(ins, world, a, rng)
    return max(opts, key=lambda o: o[0])[1] if opts else None


def find_plan(world, a: Agent, p: Dict[str, Any], rng) -> Optional[Dict[str, Any]]:
    """Go looking for the raw thing the village needs. Nobody knows what it is, only what it is like, so the search
    is for anything this chit has never handled: one from the stores, one it can see and gather, or new ground. (It
    used to gather the project's hidden item by name, which put "gather 2 ore" in a model's choice menu.)"""
    from ..sim import projects
    from ..sim.items import GATHER_RULES

    thought = "The village needs something nobody here has ever held. Let me look."
    goal = "search for what the village needs"
    mine = any(o is a for o in projects.imaginers(world, DESIGNS[p["for"]], projects.scope_of_project(world, p)))
    new = lambda k: k in GATHER_RULES and k not in a.familiar
    if mine:
        stored = sorted({k for s in world.structures_near(a.x, a.y, 30, "stockpile") if s.functional
                         for k, n in s.storage.items() if n > 0 and new(k)})
        if stored:
            return {"goal": goal, "thought": thought, "steps": [{"do": "take", "what": stored[0], "qty": 1}]}
    seen = []
    for k in sorted(GATHER_RULES):
        rule = GATHER_RULES[k]
        if not new(k) or (rule.get("requires") and not a.best_tool(rule["tool"])):
            continue
        spot = world.nearest_resource(a.x, a.y, k, 26)
        if spot:
            seen.append((max(abs(spot[0] - a.x), abs(spot[1] - a.y)), k))
    if seen:
        k = min(seen)[1]
        store = [] if mine else [{"do": "store", "what": k}]
        return {"goal": goal, "thought": thought, "steps": [{"do": "gather", "what": k, "qty": 2}] + store}
    d = rng.choice(("N", "S", "E", "W", "NE", "NW", "SE", "SW"))
    return {"goal": goal, "thought": thought, "steps": [{"do": "explore", "dir": d}, {"do": "explore", "dir": d}]}


def production_steps(world, a: Agent, key: str, n: int) -> List[Dict[str, Any]]:
    """Steps to make n of a known thing: its inputs, then the making. At a station, the "work" verb (production at
    stations, when this build has it) unless it just failed for this chit; otherwise crafting."""
    from ..sim.actions import VERBS
    from .instinct import _need_steps

    r = world.recipe(key)
    if r is None:
        return []
    need: Dict[str, int] = {}
    for k, m in r.inputs:
        need[k] = need.get(k, 0) + m * n
    steps = _need_steps(a, need, world)  # from the stores first, then gathered, or made
    if not steps and any(a.inventory.get(k, 0) < m for k, m in need.items()):
        return []  # can't source them
    if r.station and "work" in VERBS and not a.last_result.startswith("Could not work"):
        return steps + [{"do": "work", "at": r.station, "what": key, "qty": n}]
    return steps + [{"do": "craft", "what": key, "qty": n}]


def make_plan(world, a: Agent, p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Make the village's material (if this chit knows how) and bring it to the building's site, or to the stores.
    A chit that can't make it fetches what it's made of for those who can."""
    from ..sim import projects
    from ..sim.items import GATHER_RULES
    from .instinct import _reachable

    key, target = p["key"], p.get("for", "")
    sc = projects.scope_of_project(world, p)  # the project's own village: its stores, its chits
    left = p["n"] - projects.stock(world, key, target, sc)
    if left <= 0:
        return None
    # (an ingredient to try for a discovery has no building: with no design to look for, any unfinished site that
    # needed one took it, an engine meant for the dynamo went into a steam pump, Codex #39)
    site = next((s for s in world.structures_near(a.x, a.y, 30, target) if not s.complete and s.needs.get(key)
                 and _reachable(world, a, s)), None) if target in DESIGNS else None
    pile = next((s for s in world.structures_near(a.x, a.y, 25, "stockpile") if s.functional), None)
    what, where = item_name(key), DESIGNS[target].name if target in DESIGNS else "village"
    if a.knows_recipe(key):
        steps = production_steps(world, a, key, 1 if left <= 2 or (world.item(key) and world.item(key).weight > 1) else 2)
        if not steps or len(steps) > 5:
            return None
        deliver = {"do": "help", "site": site.id} if site else {"do": "store", "what": key} if pile else None
        return {"goal": f"make {what} for the village's {where}", "thought": f"The {where} needs {left} more {what}. I know how to make it.",
                "steps": steps + ([deliver] if deliver else [])}
    # what it's made of is word of mouth from those who make it: only where chits talk, and only if someone does
    if not world.flags.get("say") or not any(o.knows_recipe(key) for o in projects.members(world, sc)):
        return None
    r = world.recipe(key)
    raw = [k for k, _ in (r.inputs if r else ()) if k in GATHER_RULES
           and (not GATHER_RULES[k]["requires"] or a.best_tool(GATHER_RULES[k]["tool"]))]  # (iron ore too, Codex #46)
    if not raw or pile is None:
        return None
    k = min(raw, key=lambda x: projects.stock(world, x, sc=sc))  # what the stores are shortest of
    return {"goal": f"collect {item_name(k)} for the village's {what}", "thought": f"Whoever makes the {what} will need {item_name(k)}.",
            "steps": [{"do": "gather", "what": k, "qty": 4}, {"do": "store", "what": k}]}


def _combo(bag: List[str], station: Optional[str]) -> str:
    """An experiment as sim.actions records it ("2 clay + sand at the kiln")."""
    return " + ".join(f"{bag.count(k)} {item_name(k)}" if bag.count(k) > 1 else item_name(k)
                      for k in sorted(set(bag))) + (f" at the {station}" if station else "")


def _handled(world, a: Agent) -> List[str]:
    stocked = {k for s in world.structures_near(a.x, a.y, 25, "stockpile") if s.functional
               for k, n in s.storage.items() if n > 0}
    return sorted(k for k in set(a.familiar) | set(a.inventory) | stocked if world.item(k) and not world.item(k).tool)


# what the thing the village is looking for is like -> where one would try to make it
RIDDLE_STATION = (("metal", "furnace"), ("fired", "kiln"), ("black", "kiln"), ("baked", "fire"), ("hot", "fire"),
                  ("makes lightning", "factory"), ("hauls", "workshop"))
# hunches with counts, for what takes more than three things: "something that makes lightning" is a machine that
# turns, something that pulls iron, and wire to carry it (no hunch could form the dynamo's four-ingredient bag, and a
# random try held at most three); "something that hauls" is a cart with more wheels and iron to hold them
COUNTED_HUNCHES = (
    ("makes lightning", (({"turns wheels"}, 1), ({"pulls iron"}, 1), ({"conducts lightning"}, 2))),
    ("hauls", (({"large"}, 1), ({"round"}, 2), ({"dark"}, 1))),
)
# ...and what it might be made of: one ingredient with any of each set of properties (the last one maybe not)
HUNCHES = (
    ("tool", ({"sturdy", "long"}, {"hard", "sharp"}, {"binding", "strong"})),  # a handle, a hard head, a binding
    ("can be inscribed", ({"moldable", "flexible"}, {"sharp"})),  # something soft, and something to scratch it with
    ("metal", ({"burns very hot"}, {"melts in great heat"})),  # a fierce fuel, and something that melts in it
)


def _hunch(world, rng, props: set, pool: List[str]) -> Optional[List[str]]:
    for p, roles in COUNTED_HUNCHES:
        if p not in props:
            continue
        picks = [[k for k in pool if world.item(k).props and set(world.item(k).props) & r] for r, _ in roles]
        if all(picks):
            return [x for (_, n), ks in zip(roles, picks) for x in [rng.choice(ks)] * n]
    for p, roles in HUNCHES:
        if p not in props:
            continue
        picks = [[k for k in pool if world.item(k).props and set(world.item(k).props) & r] for r in roles]
        if not all(picks[:2]):
            continue
        n = 2 if p == "metal" else 1  # metals are smelted in quantity: one or two of each
        bag = [x for ks in picks[:2] for x in [rng.choice(ks)] * rng.randint(1, n)]
        if len(picks) > 2 and picks[2] and rng.random() < 0.6:
            bag.append(rng.choice(picks[2]))
        return bag
    return None


def project_experiment(ins, world, a: Agent, rng, key: str) -> Optional[Dict[str, Any]]:
    """The village is looking for "something fired", "something metal", "a tool that cuts wood": hunches from what
    it is said to be like. Fired things come out of a kiln and metal out of a furnace, smelted from a fierce fuel
    and something that melts; a tool is a handle and a hard head, maybe bound; and like comes from like (something
    hard, from hard things). Always from things this chit has handled, never a combination that failed here."""
    it = world.item(key)
    props = set(it.props) if it else set()
    st = next((s for p, s in RIDDLE_STATION if p in props and world.nearest_station(a.x, a.y, s, STATION_REACH)), None)
    food = "edible" in props
    pool = [k for k in _handled(world, a) if food or not world.item(k).food]
    kin = [k for k in pool if props & set(world.item(k).props) - {"edible"}]
    # a hunch with no station in mind tries one nearby (the forge was missing from this list)
    stations = [None] + [s for s in STATIONS if world.nearest_station(a.x, a.y, s, STATION_NEAR)]
    failed = set(a.failed_experiments) | set(world.village_failed(a))
    for _ in range(16) if pool else ():
        where = st or rng.choice(stations)
        bag = _hunch(world, rng, props, pool) if rng.random() < 0.8 else None
        if bag is None and kin and st is None:
            first = rng.choice(kin)
            bag = [first] + [first if rng.random() < 0.4 else rng.choice(pool) for _ in range(rng.choice((0, 1, 1, 2)))]
        if bag is None:
            bag = [rng.choice(pool) for _ in range(rng.choice((1, 1, 2, 2, 3)))]
        bag.sort()
        if (len(bag) == 1 and where is None) or _combo(bag, where) in failed:
            continue
        plan = ins._exp_plan(a, bag, where, f"They say it's {' and '.join(sorted(props))}. Maybe like this?")
        if plan:
            return plan
    return ins._experiment(world, a, rng)


LORE_W = 4.0  # an old last keeper passing on what only it knows


def lore_options(ins, world, a: Agent, rng) -> List[Opt]:
    """The last one alive who knows how to make something, and old: pass it on, by what the culture allows."""
    from ..sim import lore
    from .instinct import _craft_steps, _need_steps

    keys = lore.last_of(world, a)
    if not keys:
        return []
    k = keys[0]
    key = k.split(":", 1)[1]
    what = world.item_name(key)
    goal, thought = f"pass on how to make {what}", f"I'm the last who knows how to make {what}. It mustn't die with me."
    if world.flags.get("teach"):
        pupils = [o for o in world.agents_near(a.x, a.y, 12, exclude=a.id) if k not in o.knows]
        if not pupils:
            return []
        pupil = min(pupils, key=lambda o: (-o.born, o.id))  # the youngest has the most years to keep it
        return [(LORE_W, {"goal": goal, "thought": thought,
                          "steps": [{"do": "teach", "to": pupil.name, "what": k},
                                    {"do": "say", "to": pupil.name, "text": f"Remember this: that's how {what} is made."}]})]
    if world.flags.get("write"):
        pre = [] if a.has("clay_tablet") else _need_steps(a, {"clay_tablet": 1}, world)
        if not a.has("clay_tablet") and not pre:
            return []
        return [(LORE_W, {"goal": goal, "thought": thought, "steps": pre[:3] + [{"do": "write", "what": k}]})]
    # no speech, no writing: make it where others can watch (they may learn it by seeing it done)
    crowd = [o for o in world.agents_near(a.x, a.y, 20, exclude=a.id)
             if sum(1 for p in world.agents_near(o.x, o.y, 3)) >= 3]
    steps = _craft_steps(a, key, world=world)
    if not crowd or not steps:
        return []
    spot = min(crowd, key=lambda o: (max(abs(o.x - a.x), abs(o.y - a.y)), o.id))
    return [(LORE_W, {"goal": goal, "thought": thought,
                      "steps": steps[:-1] + [{"do": "go", "to": f"{spot.x},{spot.y}"}, steps[-1]]})]


def _library(world, a: Agent):
    from .instinct import _reachable

    for lib in world.structures_near(a.x, a.y, 25, "library"):
        if lib.functional and any(t in world.tablets for t in lib.shelf) and _reachable(world, a, lib):
            return lib
    return None


def research_options(ins, world, a: Agent, rng) -> List[Opt]:
    from ..sim import projects

    if a.is_child(world.tick):
        return []
    out: List[Opt] = []
    lib = _library(world, a)
    if lib is not None:
        w = STUDY_W + 1.2 * a.traits.get("curiosity", 0.5)
        p = projects.current(world, a)
        if p and p["kind"] == "discover" and projects.knows(world, a, p):
            w *= 1.5  # the village is looking for something: the scholars may find the way
        out.append((w, {"goal": "study at the library", "thought": "The tablets might give us an idea.",
                        "steps": [{"do": "study", "target": lib.id}]}))
    plan = hinted_experiment(ins, world, a, rng)
    if plan:
        out.append((HINT_W, plan))
    return out


def hinted_experiment(ins, world, a: Agent, rng) -> Optional[Dict[str, Any]]:
    """The scholars' hint, matched against things this chit has handled (or can see in the stores): each property
    stands for one of them. A combination that already failed, here or for the neighbours, is not tried again."""
    hints = research.active_hints(world, a)
    if not hints:
        return None
    seen = _handled(world, a)
    failed = set(a.failed_experiments) | set(world.village_failed(a))
    for h in reversed(hints):
        st = h.get("station")
        if st and not world.nearest_station(a.x, a.y, st, STATION_REACH):
            continue
        choices = [[k for k in seen if prop in world.item(k).props] for prop, _ in h["parts"]]
        if not all(choices):
            continue
        for _ in range(6):
            bag: List[str] = []
            for (prop, n), ks in zip(h["parts"], choices):
                bag += [rng.choice(ks)] * int(n)
            if _combo(bag, st) in failed:
                continue
            plan = ins._exp_plan(a, sorted(bag), st, "The scholars had an idea. I think I know which things they mean.")
            if plan:
                plan["goal"] = "try the scholars' idea"
                return plan
    return None


# the words in an option's goal that serve a want
def _want_words(w: Dict[str, Any]) -> Tuple[str, ...]:
    kind, key = w.get("kind"), w.get("key", "")
    if kind == "home":
        return ("brick house",) if key == "brick_house" else ("hut", "home", "brick house")
    if kind == "item":
        return (f"make a {item_name(key)}",)
    if kind == "first":
        return ("experiment", "scholars' idea")
    if kind == "build":
        return (DESIGNS[key].name,) if key in DESIGNS else ()
    if kind == "stat":
        return {"tamed": ("tame", "pen"), "wrote": ("record",), "taught": ("teach",)}.get(key, ())
    return ()


def want_bias(world, a: Agent, opts: List[Opt]) -> List[Opt]:
    words = _want_words(getattr(a, "want", None) or {})
    if not words:
        return opts
    return [(w * WANT_BIAS if any(x in o["goal"] for x in words) else w, o) for w, o in opts]


def _kind(goal: str) -> str:
    return (goal or "").split(" ", 1)[0].lower()


def imitation_bias(world, a: Agent, opts: List[Opt]) -> List[Opt]:
    """Chits near the village's most renowned chit lean a little towards what it is doing now."""
    star = wants.famous(world)
    if star is None or star is a or not star.goal or max(abs(star.x - a.x), abs(star.y - a.y)) > wants.IMITATE_RADIUS:
        return opts
    kind = _kind(star.goal)
    return [(w * IMITATE_BIAS if _kind(o["goal"]) == kind else w, o) for w, o in opts]
