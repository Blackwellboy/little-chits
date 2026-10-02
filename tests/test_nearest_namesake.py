"""Namesakes. Old worlds named many chits alike ("Chit2154" four times in one live world), and a name always meant
whichever chit came first: chits walked off after a namesake across the map and failed "couldn't find X to talk
to" 36-48 times in ten days. A name now means the nearest chit of that name; an id still means exactly that chit."""

from chits.sim import actions
from chits.sim.world import World


def test_a_name_means_the_nearest_chit_of_that_name():
    w = World("A", "A", 5, "direct", 96, 4)
    a, near, far, _ = list(w.agents.values())
    for o in (a, near, far):
        o.hunger = o.energy = o.warmth = o.health = 95.0
    near.name = far.name = "Chit2154"
    far.x, far.y = a.x + 60, a.y
    near.x, near.y = a.x + 2, a.y
    # (the far one comes first in the world's order)
    w.agents = {k: v for k, v in sorted(w.agents.items(), key=lambda kv: kv[1] is not far)}
    assert w.agent_by_name("Chit2154") is far  # with nobody asking, as before
    assert w.agent_by_name("Chit2154", near=a) is near
    assert w.agent_by_name(far.id, near=a) is far  # an id is exact
    step = {"do": "say", "to": "Chit2154", "text": "Morning!"}
    s = {"ticks": 0}
    res = actions.RUNNING
    for _ in range(60):
        w.tick += 1
        s["ticks"] += 1
        res = actions._do_say(w, a, step, s)
        if res != actions.RUNNING:
            break
    assert res == actions.DONE, res
    assert near.spoken_to.get("id") == a.id


def test_a_chit_never_means_itself_by_a_name_it_shares():
    w = World("A", "A", 5, "direct", 96, 3)
    a, other, _ = list(w.agents.values())
    a.name = other.name = "Chit2154"  # (the asker shares the name: "watch Chit2154" means the other one)
    other.x, other.y = a.x + 10, a.y
    assert w.agent_by_name("Chit2154", near=a) is other
