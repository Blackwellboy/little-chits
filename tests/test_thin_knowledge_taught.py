"""What fewest know is taught first. Teaching a friend picked at random from everything the teacher knew, so a chit
who knew 80 things almost never taught the one only it and a friend knew; in late-game runs from the live saves,
World A forgot the engine and magnet and World B the gear within 20 days as their two or three keepers died."""

import random

from chits.brain.instinct import Instinct
from chits.sim.world import World


def test_a_teacher_passes_on_what_fewest_others_know():
    w = World("A", "A", 5, "direct", 64, 6)
    ags = list(w.agents.values())
    a, pupil = ags[0], ags[1]
    for o in ags:
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.learn("recipe:cord", "taught", w.tick)  # (everyone knows cord)
        o.knows.pop("recipe:steel", None)
    a.learn("recipe:steel", "discovered", w.tick)  # (only the teacher knows steel)
    pupil.knows.pop("recipe:cord", None)
    pupil.x, pupil.y = a.x + 1, a.y
    for o in ags[2:]:
        o.x, o.y = a.x + 30, a.y + 30  # (out of reach: the pupil is the only one near)
    ins = Instinct()
    taught = set()
    for s in range(400):
        p = ins._communal(w, a, random.Random(s)) or {}
        if p.get("goal") == f"teach {pupil.name}":
            taught.add(p["steps"][0]["what"])
    assert taught == {"recipe:steel"}, taught
