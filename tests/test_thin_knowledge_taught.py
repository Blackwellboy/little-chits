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


def test_keeper_counts_follow_learning_within_a_tick():
    # counted once a tick, a recipe taught to several watchers mid-tick still looked rare to the next teacher
    # (Codex, #26)
    from chits.brain import instinct as I
    from chits.sim.world import World

    w = World("A", "A", 5, "direct", 64, 4)
    ags = list(w.agents.values())
    before = I._keeper_counts(w).get("recipe:cord", 0)
    new = [o for o in ags[:3] if not o.knows_recipe("cord")]
    assert new
    for o in new:
        o.learn("recipe:cord", "taught", w.tick)  # (the same tick)
    assert I._keeper_counts(w)["recipe:cord"] == before + len(new)
