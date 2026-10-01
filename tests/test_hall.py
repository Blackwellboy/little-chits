"""The hall of ancestors: a short biography for every chit that mattered, from its own record (firsts, inventions,
elections won, laws decreed, teaching, children, its last reflection). Read-only: it never changes the world."""

import json

from chits import views
from chits.sim import hall as HALL
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def _world():
    w = World("A", "A", 5, "direct", 64, 6)
    w.tick = 40 * TICKS_PER_DAY
    return w, list(w.agents.values())


def test_a_chit_that_mattered_gets_a_biography_and_one_that_didnt_does_not():
    w, (a, b, c, d, e, f) = _world()
    w.first["recipe:iron"] = {"tick": w.tick - 100, "by": a.id, "name": a.name}
    w.inventions["berry_wick"] = {"key": "berry_wick", "name": "Berry-Wick", "by": a.id, "by_name": a.name, "tick": 10}
    w.leader = a.id  # (only a chief decrees)
    w.decree(a, "No skill is buried with its keeper.")
    kid = w._make_child(a, b, w.place_site("hut", *w.find_site("hut", a.x, a.y, 6), a))
    a.lessons.append("What we make together outlives us.")
    a.stats["taught"] = 14
    w.kill(a, "starvation")
    w.kill(f, "old age")  # nothing to its name, and young
    hall = views.hall(w)
    assert [x["name"] for x in hall] == [a.name]
    bio = hall[0]
    assert bio["firsts"] == ["make iron"] and bio["inventions"] == ["Berry-Wick"] and bio["children"] == 1
    for bit in ("was the first in", "make iron", "invented the Berry-Wick", 'decreed: "No skill is buried', "taught 14 chits",
                "had 1 child", "died of starvation", 'In its own words: "What we make together outlives us."'):
        assert bit in bio["text"], bit
    assert kid.name not in bio["text"]


def test_elections_and_laws_go_on_a_chits_record_and_survive_death_and_a_save():
    w, ags = _world()
    for o in ags:
        for p in ags:
            if p is not o:
                o.like(p.id, 40 if p is ags[2] else 1)
    w.choose_leader("scheduled")
    chief = w.agents[w.leader]
    assert any("was elected chief" in x for x in chief.deeds)
    for i in range(12):
        w.decree(chief, f"Law number {i} of the village.")
    assert len(chief.deeds) == HALL.DEEDS_MAX and "Law number 11" in chief.deeds[-1]  # the newest are kept
    w.decree(chief, "Everyone carries wood.")
    w.kill(chief, "old age")
    back = World.from_dict(json.loads(json.dumps(w.to_dict()))).dead[chief.id]
    assert back.deeds == chief.deeds and any("Everyone carries wood" in x for x in back.deeds)
    assert len(back.deeds) <= HALL.DEEDS_MAX


def test_the_hall_only_reads():
    w, (a, *_) = _world()
    w.first["design:kiln"] = {"tick": 5, "by": a.id, "name": a.name}
    w.kill(a, "old age")
    before = json.dumps(w.to_dict(), sort_keys=True, default=str)
    assert views.hall(w)
    assert json.dumps(w.to_dict(), sort_keys=True, default=str) == before
