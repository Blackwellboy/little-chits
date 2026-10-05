"""Run one instinct world and print what it came to, for comparing two trees (tests/test_village_identity.py).

Self-contained on purpose: it runs unchanged against this tree and against an older one (``git archive``), from that
tree's ``server`` directory. It hashes the saved world each day without the uuid labels and the ``build`` field, and
with the civic keys that F32 renamed (``projects``/``skips``) put back in their old shape (``project``/``skip``), so
a world that stays one village must come out the same on both.

    python identity_runner.py SEED DAYS SIZE CHITS MAKE_FIRST(0|1) [CULTURE]
"""

import hashlib
import json
import sys


def normal(d):
    d = dict(d)
    for k in ("uuid", "epoch", "epochs", "build"):
        d.pop(k, None)
    civ = dict(d.get("civic") or {})
    if "projects" in civ:  # the per-village shape, for a world with one project at most: back to the old keys
        live = [p for p in civ.pop("projects").values() if p]
        skip = {}
        for m in civ.pop("skips", {}).values():
            skip.update(m)
        civ["project"], civ["skip"] = (live[0] if len(live) == 1 else live or None), skip
    d["civic"] = civ
    return _unlabel(d)


def _unlabel(x):
    """Without the uuid4 labels a plan's steps carry (``_step_id``): they name a step, and differ on every run."""
    if isinstance(x, dict):
        return {k: _unlabel(v) for k, v in x.items() if k != "_step_id"}
    return [_unlabel(v) for v in x] if isinstance(x, (list, tuple)) else x


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def main(argv):
    seed, days, size, chits, make_first = (int(x) for x in argv[:5])
    culture = argv[5] if len(argv) > 5 else "direct"
    from chits.brain.instinct import Instinct
    from chits.sim import pioneers, projects
    from chits.sim.agent import TICKS_PER_DAY
    from chits.sim.world import World

    if hasattr(projects, "MAKE_FIRST"):
        projects.MAKE_FIRST = bool(make_first)
    from chits.brain import instinct as instinct_rules
    from chits.sim import actions

    # later changes to what a one-village world does, switched off
    if hasattr(instinct_rules, "HUNGER_REACH"):
        instinct_rules.HUNGER_REACH = False
    if hasattr(actions, "STARVING_FETCH"):
        actions.STARVING_FETCH = False
    if hasattr(actions, "HUNGER_MARGIN"):  # (food by the ticks left against the walk, not by fixed hunger numbers)
        actions.HUNGER_MARGIN = False
    if hasattr(actions, "PLENTY"):  # the readings of the village's stock (F33) change a one-village world too: off
        actions.PLENTY = bool(make_first)  # with MAKE_FIRST, for the comparison with the tree before either
    from chits.sim import buildings
    for switch in ("NEED_SITING", "TOWN_GATE"):  # (F32's dead zones and town rank: off, as before them)
        if hasattr(buildings, switch):
            setattr(buildings, switch, False)
    from chits.sim import items
    if hasattr(items, "ITEM_USES"):
        items.ITEM_USES = False  # F35's item uses change a one-village run; they have tests of their own
    from chits.sim import world as world_mod
    if hasattr(world_mod, "RNG_STREAMS"):  # streams per system, chit and tick: off, the running streams of old trees
        world_mod.RNG_STREAMS = False
    min_adults = getattr(projects, "PROJECT_MIN_ADULTS", 4)
    w = World("A", "A", seed, culture, size, chits)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal, a.plan_source = p["steps"], p["goal"], "instinct"

    daily, events, last, most, carrying = [], hashlib.sha256(), 0, 0, 0
    first_two = None
    for day in range(days):
        for _ in range(TICKS_PER_DAY):
            w.step(hook)
        for e in w.events:
            if e.seq > last:
                events.update(json.dumps(e.to_dict(), sort_keys=True, default=str).encode())
        last = max((e.seq for e in w.events), default=last)
        vs = pioneers.villages(w)
        groups = []  # (settlements nearer than pioneers.APART are one village, as projects._villages takes them)
        for v in vs:
            near = [g for g in groups if any(max(abs(v.x - o.x), abs(v.y - o.y)) < pioneers.APART for o in g)]
            groups = [g for g in groups if g not in near] + [[v] + [o for g in near for o in g]]
        adults = lambda g: sum(1 for v in g for i in v.residents if i in w.agents and not w.agents[i].is_child(w.tick))
        grown = [g for g in groups if adults(g) >= min_adults]
        most, carrying = max(most, len(vs)), max(carrying, len(grown))
        if first_two is None and len(grown) > 1:
            first_two = day + 1
        daily.append(digest(normal(w.to_dict()))[:16])
    out = {"seed": seed, "days": days, "hash": digest(normal(w.to_dict())), "events": events.hexdigest(), "daily": daily,
           "villages_most": most, "carrying_most": carrying, "first_day_with_two": first_two,
           "projects_done": len(w.civic.get("done", [])), "population": len(w.agents), "era": w.era()[0],
           "discoveries": w.stats().get("discoveries"), "tree": projects.__file__}
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1:])
