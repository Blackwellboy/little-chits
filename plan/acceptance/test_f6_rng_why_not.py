import json

from chits import diag
from chits.sim.world import World


def test_streams_are_independent_and_persist():
    a = World("A", "A", 21, "direct", 96, 0)
    b = World("B", "B", 21, "direct", 96, 0)
    for _ in range(50):
        a.rng_for("combat").random()  # extra rolls in one world only
    for _ in range(240 * 3):
        a.step()
        b.step()
    assert a.res_amt == b.res_amt, "regrowth must not depend on unrelated dice rolls"
    assert a.rng_for("weather").random() == b.rng_for("weather").random()
    assert a.rng_for("births") is a.rng_for("births")
    x = World.from_dict(json.loads(json.dumps(a.to_dict())))
    assert x.rng_for("regrow").random() == a.rng_for("regrow").random()


def test_opportunities():
    w = World("A", "A", 5, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    a.inventory.clear()
    b.inventory.clear()
    a.learn("design:kiln", "taught", w.tick, None)
    op = diag.opportunities(w)["design:kiln"]
    assert op["known_by"] == 1 and op["affordable_by"] == 0 and op["sites_started"] == 0
    a.add("clay", 8)
    a.add("stone", 4)
    assert diag.opportunities(w)["design:kiln"]["affordable_by"] == 1
    a.familiar |= {"fiber"}
    rec = diag.opportunities(w)["recipe:cord"]
    assert rec["inputs_handled_by"] >= 1
