"""Lighter saves: a dead chit's record keeps who it was and what it knew, not its whole life's log (the dead were
70% of every checkpoint on a 512 map at day 600)."""

import json

from chits.sim.agent import DEAD_BONDS, DEAD_LESSONS, DEAD_MEMORIES
from chits.sim.world import World


def _full_life(w, a):
    for i in range(60):
        a.remember(w.tick + i, f"a day of my life number {i}", 2, "event")
    a.affinity = {f"a{100 + i}": float(i) for i in range(40)}
    a.lessons = [f"lesson {i}: fire needs wood" for i in range(10)]
    a.lesson_sources = {t: [1, a.memories[-1].id] for t in a.lessons}
    a.failed_experiments = [f"{i} wood at the fire" for i in range(30)]
    a.plan = [{"do": "rest"}] * 5
    a.last_choice = {"options": [{"letter": "A", "goal": "x", "p": 0.5}] * 6}
    a.learn("recipe:cord", "discovered", w.tick)
    a.bump("gathered_wood", 50)


def test_a_dead_chits_record_keeps_who_it_was_and_what_it_knew():
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    _full_life(w, a)
    name, parents, knows, stats = a.name, a.parents, dict(a.knows), dict(a.stats)
    last = [m.text for m in a.memories[-DEAD_MEMORIES:]]
    w.kill(a, "old age")
    d = w.dead[a.id]
    assert (d.name, d.parents, d.knows, d.stats, d.cause_of_death) == (name, parents, knows, stats, "old age")
    assert [m.text for m in d.memories] == last
    assert len(d.affinity) == DEAD_BONDS and max(d.affinity.values()) == 39.0
    assert d.lessons == [f"lesson {i}: fire needs wood" for i in range(10)][-DEAD_LESSONS:]
    assert set(d.lesson_sources) == set(d.lessons)
    assert all(v == [d.memories[-1].id] for v in d.lesson_sources.values())  # no memory it no longer has
    assert not d.failed_experiments and not d.plan and not d.last_choice
    # it survives a save and a load unchanged
    b = World.from_dict(json.loads(json.dumps(w.to_dict()))).dead[a.id]
    assert ([m.text for m in b.memories], b.affinity, b.lessons, b.lesson_sources) == (
        [m.text for m in d.memories], d.affinity, d.lessons, d.lesson_sources)


def test_an_older_save_is_trimmed_when_it_loads_and_the_checkpoint_shrinks():
    w = World("A", "A", 3, "direct", 64, 6)
    for a in list(w.agents.values())[:5]:
        _full_life(w, a)
        w.kill(a, "old age")
    small = w.to_dict()
    old = json.loads(json.dumps(small))
    for i, a in enumerate(old["dead"]):  # a record from before obituaries: every memory, every bond
        a["memories"] = [{"tick": j, "text": f"an old memory {j}", "importance": 2, "kind": "event", "id": j + 1}
                         for j in range(60)]
        a["affinity"] = {f"a{100 + j}": float(j) for j in range(40)}
    back = World.from_dict(old)
    assert all(len(a.memories) == DEAD_MEMORIES and len(a.affinity) == DEAD_BONDS for a in back.dead.values())
    size = lambda d: len(json.dumps(d, separators=(",", ":")))  # what a checkpoint serialises
    assert size(back.to_dict()["dead"]) < 0.5 * size(old["dead"])
