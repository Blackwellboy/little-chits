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


HOWS = ["insight", "insight", "insight", "taught", "raised", "inspected", "read", "observed", "instinct"]


def _graveyard(n):
    """A world with n dead chits, each with a life's knowledge (some proven later), memories, lessons and parents."""
    import random

    from chits.sim.agent import Agent
    from chits.sim.items import DESIGNS, RECIPES

    w = World("A", "A", 3, "direct", 64, 6)
    tmpl = next(iter(w.agents.values())).to_dict()
    rng = random.Random(7)
    keys = [f"recipe:{k}" for k in sorted(RECIPES)[:8]] + [f"design:{k}" for k in sorted(DESIGNS)[:5]]
    ids = []
    for i in range(n):
        a = Agent.from_dict(dict(tmpl, id=f"d{i}", name=f"Dead{i}", knows={}, memories=[], parents=ids[-2:]))
        w.agents[a.id] = a
        for k in rng.sample(keys, 10):
            how = rng.choice(HOWS)
            a.learn(k, how, 1000 + i, None if how in ("insight", "instinct", "read", "inspected") else ids[-1] if ids else None)
            if rng.random() < 0.2:
                a.made_it_work(k, 2000 + i)
        for j in range(60):
            a.remember(100 + j, f"a day of my life number {j}", 2, "event")
        a.lessons = [f"lesson {j}: fire needs wood" for j in range(5)]
        a.stats = {"taught": rng.randint(0, 30), "meals": 100}
        a.renown = float(i % 7)
        ids.append(a.id)
        w.kill(a, "old age")
    return w


def test_the_dead_save_small_and_every_reader_sees_them_as_they_were():
    """A late save was 93% dead chits (live: 39 of 42 MB for 1,929 dead), half of it their knowledge written in full.
    A dead chit's record now leaves out what loading gives back, so the save shrinks and nothing reading the dead
    (the chit panel, family, the hall, the recap, how a thing spread, its lineage, the Lab) can tell."""
    from chits import views
    from chits.lab import propositions
    from chits.story.recap import recap

    w = _graveyard(500)
    size = lambda d: len(json.dumps(d, separators=(",", ":")))
    full = [a.to_dict() for a in w.dead.values()]  # (the whole record, as every dead chit was saved before)
    saved = json.loads(json.dumps(w.to_dict()))
    assert size(saved["dead"]) < 0.6 * size(full)
    w2 = World.from_dict(saved)
    assert [a.to_dict() for a in w2.dead.values()] == full  # nothing lost: each one loads exactly as it was

    def read(x):
        some = [x.dead[f"d{i}"] for i in (0, 1, 250, 499)]
        return {"detail": [views.agent_detail(x, a) for a in some], "family": [views.family(x, a.id) for a in some],
                "hall": views.hall(x), "recap": recap(x), "eras": views.eras(x),
                "spread": [views.spread(x, k) for k in sorted(x.dead["d499"].knows)[:3]],
                "lab": propositions.snapshot(x)}

    assert json.dumps(read(w2), sort_keys=True, default=str) == json.dumps(read(w), sort_keys=True, default=str)


def test_an_old_save_with_whole_records_still_loads_and_comes_out_small():
    w = _graveyard(40)
    full = json.loads(json.dumps(w.to_dict()))
    full["dead"] = [a.to_dict() for a in w.dead.values()]  # a save from before: every field, every knowledge key
    back = World.from_dict(json.loads(json.dumps(full)))
    assert [a.to_dict() for a in back.dead.values()] == full["dead"]
    assert len(json.dumps(back.to_dict()["dead"])) < 0.6 * len(json.dumps(full["dead"]))
