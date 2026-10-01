import pytest

from chits.brain.instinct import Instinct
from chits.sim.world import World

RESULTS = {}


def run(seed):
    if seed in RESULTS:
        return RESULTS[seed]
    w = World("A", "A", seed, "direct", 128, 18)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    low = 99
    for t in range(240 * 30):
        w.step(hook)
        if t % 240 == 0:
            low = min(low, len(w.agents))
    st = w.stats()
    st["lowest"] = min(low, len(w.agents))
    RESULTS[seed] = st
    return st


@pytest.mark.parametrize("seed", [42, 7, 99])
def test_thriving_without_spam(seed):
    st = run(seed)
    b = st["by_design"]
    pop = st["population"]
    assert pop >= 12 and st["lowest"] > 0, st
    assert st["discoveries"] >= 14, st
    assert b.get("stockpile", 0) <= 6, b
    assert b.get("kiln", 0) <= 4, b
    assert b.get("campfire", 0) <= 10, b
    assert b.get("farm", 0) <= pop / 2 + 2, (b, pop)
    assert b.get("hut", 0) + b.get("brick_house", 0) <= pop / 2 + 4, (b, pop)


def test_advanced_crafting_reached():
    have = sum(1 for s in (42, 7, 99) if run(s)["by_design"].get("workshop") or run(s)["by_design"].get("furnace"))
    assert have >= 2
