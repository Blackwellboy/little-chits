"""settlements.detect buckets buildings by where they stand instead of comparing every pair. It must find exactly the
settlements the every-pair look found."""

import random
import time

from chits.brain.instinct import Instinct
from chits.sim import settlements as SE
from chits.sim.items import DESIGNS
from chits.sim.world import World


def _every_pair(world):
    """The settlements as the old look grouped them: sorted member ids of each cluster of three or more with two homes."""
    sts = [s for s in world.structures.values() if s.complete and s.durability > 0 and s.design != "road"]
    parent = {s.id: s.id for s in sts}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(sts):
        ax, ay = a.center()
        for b in sts[i + 1:]:
            if b.dist(int(round(ax)), int(round(ay))) <= SE.LINK:
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    parent[ra] = rb
    groups = {}
    for s in sts:
        groups.setdefault(find(s.id), []).append(s)
    out = [sorted((s.id for s in m), key=SE._num) for m in groups.values()
           if len(m) >= 3 and len([s for s in m if s.design in SE.HOMES]) >= 2]
    return sorted(out, key=lambda ids: SE._num(ids[0]))


def test_the_grid_is_wider_than_any_link_can_reach():
    widest = max(max(d.size) for d in DESIGNS.values())
    assert SE._CELL > SE.LINK + widest


def test_the_bucketed_look_finds_the_same_settlements_as_every_pair():
    rng = random.Random(5)
    w = World("A", "A", 5, "direct", 128, 6)
    a = next(iter(w.agents.values()))
    designs = ["hut", "hut", "hut", "brick_house", "stockpile", "farm", "kiln", "workshop", "library", "factory", "aqueduct"]
    placed = 0
    for _ in range(600):
        d = rng.choice(designs)
        bx, by = rng.choice(((22, 22), (100, 24), (26, 100), (98, 98)))  # four places well apart, and a few strays
        x, y = (bx + rng.randrange(-11, 12), by + rng.randrange(-11, 12)) if rng.random() < 0.93 else (rng.randrange(4, 124), rng.randrange(4, 124))
        pos = w.find_site(d, x, y, 2)
        if pos:
            w.complete_structure(w.place_site(d, pos[0], pos[1], a), a)
            placed += 1
    assert placed > 100
    got = [s.structures for s in SE.detect(w)]
    assert got == _every_pair(w) and len(got) >= 2


def test_a_world_that_grows_by_itself_gets_the_same_settlements():
    w = World("A", "A", 7, "direct", 96, 18)
    ins = Instinct()

    def hook(world, c):
        if not c.plan:
            p = ins.plan(world, c)
            c.plan, c.goal = p["steps"], p["goal"]

    for t in range(240 * 12):
        w.step(hook)
        if t % 480 == 0:
            assert [s.structures for s in SE.detect(w)] == _every_pair(w)
    assert [s.structures for s in SE.detect(w)] == _every_pair(w)
