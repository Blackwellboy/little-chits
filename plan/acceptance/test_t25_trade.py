import json

from chits.brain import prompt as P
from chits.sim.items import DESIGNS, base_value
from chits.sim.world import World


def pair(seed=3):
    w = World("B", "World B", seed, "stigmergy", 64, 2)
    a, b = list(w.agents.values())[:2]
    for c in (a, b):
        c.hunger = c.energy = c.warmth = c.health = 100.0
        c.inventory.clear()
        c.plan = []
    b.x, b.y = a.x, a.y
    return w, a, b


def run(w, a, step, limit=80):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_values():
    assert base_value("stone") == 1.0 and base_value("ore") == 2.0
    assert base_value("stone_axe") > base_value("sharp_stone") > base_value("stone")
    assert base_value("copper") > base_value("ore")
    w, a, b = pair()
    full = w.value_for(a, "berries")
    a.hunger = 30.0
    assert w.value_for(a, "berries") > full * 2
    assert w.value_for(a, "stone_axe") >= base_value("stone_axe") * 2  # no axe yet
    a.add("stone", 12)
    assert w.value_for(a, "stone") < 1.0


def test_fair_trade_happens_in_the_silent_world_too():
    w, a, b = pair()
    evs = []
    w.listeners.append(evs.append)
    a.add("berries", 6)
    b.add("stone_axe", 1)
    b.hunger = 30.0  # hungry: berries are worth a lot to b
    run(w, a, {"do": "trade", "to": b.name, "give": {"berries": 5}, "get": "stone_axe"})
    assert a.inventory.get("stone_axe") == 1 and b.inventory.get("berries", 0) >= 5, a.last_result
    assert any(e.kind == "trade" for e in evs)
    assert len(w.trades) == 1 and w.trades[0]["a"] == a.id


def test_bad_deal_is_refused():
    w, a, b = pair(5)
    a.add("fiber", 1)
    b.add("stone_axe", 1)
    msg = run(w, a, {"do": "barter", "to": b.name, "give": "fiber", "get": "stone_axe"})
    assert "didn't want" in msg and b.inventory.get("stone_axe") == 1 and a.inventory.get("fiber") == 1


def test_money_emerges_and_persists():
    w, a, b = pair(7)
    evs = []
    w.listeners.append(evs.append)
    ids = list(w.agents)
    fake = [f"z{i}" for i in range(4)]
    for i in range(10):
        w.trades.append({"tick": w.tick, "a": fake[i % 4], "b": fake[(i + 1) % 4], "give": {"copper": 1}, "get": {["wood", "stone", "fiber", "clay"][i % 4]: 3}})
    w.trades.append({"tick": w.tick, "a": ids[0], "b": ids[1], "give": {"berries": 2}, "get": {"stone": 1}})
    w.update_money()
    assert w.currency == "copper"
    assert any(e.kind == "money" and e.importance == 5 for e in evs)
    assert "Money here: copper" in P.scene(w, a)
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.currency == "copper"
    assert "market" in DESIGNS and DESIGNS["market"].size == (2, 2)
    assert '"do":"trade"' in P.verb_guide(w).replace(" ", "")
