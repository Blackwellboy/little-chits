"""Run one instinct world with the space programme switched off and print what it came to, for comparing this tree
with main before the programme (tests/test_space_programme.py). Each day three chits study an alien ship and a radio
(each teaches a recipe drawn from those nobody has found), on day 1 one opens a treasure chest and a time capsule,
and on day 3 a launch pad stands, built by three of them: the draws, the pad's launch and what follows are all main's.

    python space_off_runner.py SEED DAYS
"""

import json
import sys

from identity_runner import digest, normal


def main(argv):
    seed, days = (int(x) for x in argv[:2])
    from chits.brain.instinct import Instinct
    from chits.sim import artifacts
    from chits.sim import world as W
    from chits.sim.agent import TICKS_PER_DAY
    from chits.sim.world import World

    if hasattr(W, "SPACE_PROGRAMME"):
        W.SPACE_PROGRAMME = False
    # (the switches that came after the base tree, off too: this compares the programme's off path, not theirs)
    from chits.sim import actions
    for mod, name in ((actions, "STARVING_STORES"), (actions, "TRANSPORT"), (W, "CITY_GROWTH")):
        if hasattr(mod, name):
            setattr(mod, name, False)
    try:
        from chits.brain import inventor
    except ImportError:
        inventor = None
    if hasattr(inventor, "INSTINCT_INVENTS"):
        inventor.INSTINCT_INVENTS = False
    w = World("A", "A", seed, "direct", 128, 18)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal, a.plan_source = p["steps"], p["goal"], "instinct"

    daily, notes = [], []
    for day in range(days):
        chits = sorted(w.agents.values(), key=lambda a: a.id)[:3]
        for a in chits:
            for key in ("alien_ship", "radio"):
                notes.append(artifacts.on_inspect(w, a, key, {}))
        if day == 1:
            a = chits[0]
            for key in ("treasure_chest", "time_capsule"):
                notes.append(artifacts.on_pickup(w, a, key, f"{a.x},{a.y}"))
        if day == 3:
            a = chits[0]
            xy = w.find_site("launch_pad", a.x + 4, a.y, 20)
            s = w.place_site("launch_pad", xy[0], xy[1], a)
            s.builders.update({c.id: 10.0 - i for i, c in enumerate(chits)})
            w.complete_structure(s, a)
        for _ in range(TICKS_PER_DAY):
            w.step(hook)
        daily.append(digest(normal(w.to_dict()))[:16])
    print(json.dumps({"daily": daily, "hash": digest(normal(w.to_dict())), "notes": notes,
                      "launches": sum(1 for e in w.events if e.kind == "launch"), "tree": W.__file__}))


if __name__ == "__main__":
    main(sys.argv[1:])
