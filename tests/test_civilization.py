"""A long headless run: with only instinct, a civilisation must survive, discover and grow."""

from chits.brain.instinct import Instinct
from chits.sim.world import World


def test_instinct_civilization_progresses():
    w = World("A", "A", 7, "direct", 128, 16)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    for _ in range(240 * 14):  # two weeks, including a winter
        w.step(hook)
    st = w.stats()
    assert st["population"] >= 8, st
    assert st["discoveries"] >= 8, st
    built = st["by_design"]
    # huts built, counting those since rebuilt bigger where they stand (a hut can become a longhouse)
    huts = built.get("hut", 0) + sum(1 for e in w.events if e.kind == "built" and e.data.get("upgraded_from") == "hut")
    assert huts >= 3 and built.get("campfire", 0) >= 1, built
    assert len(built) >= 4, built
    kinds = {e.kind for e in w.events}
    assert {"built", "learned"} <= kinds
    # knowledge spread socially, not just by discovery
    hows = {v["how"] for a in w.agents.values() for v in a.knows.values()}
    assert hows & {"taught", "observed", "inspected"}
