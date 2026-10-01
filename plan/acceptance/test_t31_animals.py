import json

from chits.brain import prompt as P
from chits.sim.items import ITEMS, RECIPES, DESIGNS
from chits.sim.world import World


def world(seed=3, n=2, size=96):
    w = World("A", "A", seed, "direct", size, n)
    ags = list(w.agents.values())
    for a in ags:
        a.hunger = a.energy = a.warmth = a.health = 100.0
        a.inventory.clear()
        a.plan = []
        a.born = -2400
    return w, ags


def run(w, a, step, limit=300):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_spawning_and_items():
    w, _ = world()
    kinds = [x["kind"] for x in w.animals.values()]
    assert kinds.count("deer") >= 2 and kinds.count("sheep") >= 1 and kinds.count("wolf") == 0
    for k in ("meat", "cooked_meat", "wool", "cloth", "cloak"):
        assert k in ITEMS
    assert RECIPES["cooked_meat"].station == "fire" and "pen" in DESIGNS
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.animals == w.animals


def test_hunting_needs_a_spear():
    w, (a, b) = world(5)
    deer = next(x for x in w.animals.values() if x["kind"] == "deer")
    a.x, a.y = deer["x"], deer["y"]
    assert "spear" in run(w, a, {"do": "hunt", "what": "deer"}).lower()
    a.add("spear", 1)
    got = 0
    for _ in range(6):
        run(w, a, {"do": "hunt", "what": "deer"}, limit=400)
        got = a.inventory.get("meat", 0)
        if got:
            break
    assert got == 3, a.last_result
    assert "hunt" in P.verb_guide(w)


def test_wolves_bite_outdoors_but_not_at_home():
    w, (a, b) = world(7)
    pos = w.find_site("hut", a.x, a.y)
    hut = w.place_site("hut", pos[0], pos[1], a)
    w.complete_structure(hut, a)
    w.tick = 240 * 20 + 5  # just after midnight (no day boundary in the next 30 ticks)
    assert w.is_night
    b.x, b.y = hut.x, hut.y  # b sleeps safe at home
    ax, ay = (hut.x + 12, hut.y) if w.passable(hut.x + 12, hut.y) else (hut.x - 12, hut.y)
    a.x, a.y = ax, ay
    for c in (a, b):
        c.plan = [{"do": "rest", "qty": 120, "_reflex": True}]
    w.animals["wolfA"] = {"id": "wolfA", "kind": "wolf", "x": a.x + 1, "y": a.y, "hp": 10, "tame": False, "pen": ""}
    w.animals["wolfB"] = {"id": "wolfB", "kind": "wolf", "x": b.x + 1, "y": b.y, "hp": 10, "tame": False, "pen": ""}
    for _ in range(30):
        w.step()
        for c in (a, b):
            c.hunger = c.warmth = 100.0
    assert a.health < 99 and a.health > 10
    assert b.health >= 99
    assert any(e.kind == "wolf" and a.name in e.text for e in w.events)


def test_taming_and_wool():
    w, (a, b) = world(9)
    pos = w.find_site("pen", a.x, a.y)
    pen = w.place_site("pen", pos[0], pos[1], a)
    w.complete_structure(pen, a)
    sheep = next(x for x in w.animals.values() if x["kind"] == "sheep")
    sheep["x"], sheep["y"] = a.x + 1, a.y
    a.add("grain", 4)
    for _ in range(4):
        run(w, a, {"do": "tame"})
        if sheep["tame"]:
            break
    assert sheep["tame"] and sheep["pen"] == pen.id, a.last_result
    assert any(e.kind == "tamed" for e in w.events)
    w.tick = (w.tick // 240 + 1) * 240 - 1
    w.step()
    assert pen.storage.get("wool", 0) >= 1
