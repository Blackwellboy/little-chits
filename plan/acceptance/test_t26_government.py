import json

from chits.brain import prompt as P
from chits.brain.mind import apply_reflection
from chits.brain.parse import parse_reflection
from chits.sim.world import World


def village(wid="A", culture="direct", seed=3, n=5):
    w = World(wid, wid, seed, culture, 64, n)
    ags = list(w.agents.values())
    for i, a in enumerate(ags):
        a.born = -240 * (10 + i)  # adults; later ones are older
        a.affinity = {}
    return w, ags


def test_election_in_world_a():
    w, (a, b, c, d, e) = village()
    evs = []
    w.listeners.append(evs.append)
    for voter in (a, c, d, e):
        voter.affinity[b.id] = 40.0
    b.affinity[a.id] = 30.0
    w.choose_leader("test")
    assert w.leader == b.id and w.leader_since == w.tick
    ev = [x for x in evs if x.kind == "election"]
    assert ev and "4 of 5" in ev[0].text and ev[0].importance == 4
    assert f"Your chief is {b.name}" in P.scene(w, a)
    n = len(evs)
    w.choose_leader("again")  # same result: no new event
    assert len(evs) == n


def test_elder_in_world_b():
    w, (a, b, c, d, e) = village("B", "stigmergy")
    evs = []
    w.listeners.append(evs.append)
    for o in (a, b, d, e):
        o.affinity[c.id] = 20.0
    w.choose_leader("test")
    assert w.leader == c.id
    assert any(x.kind == "elder" for x in evs) and not any(x.kind == "election" for x in evs)
    assert "elder" in P.scene(w, a)


def test_decrees():
    w, (a, b, c, d, e) = village()
    for voter in (a, c, d, e):
        voter.affinity[b.id] = 40.0
    w.choose_leader("test")
    r = parse_reflection(json.dumps({"lessons": [], "decree": "Nobody takes the last bread from the stockpile"}))
    assert r["decree"].startswith("Nobody")
    assert parse_reflection(json.dumps({"lessons": [], "law": "no"}))["decree"] == ""
    apply_reflection(w, a, json.dumps({"lessons": [], "decree": "Everyone must bow to Pip forever"}))
    assert w.laws == []  # only the chief can decree
    apply_reflection(w, b, json.dumps({"lessons": [], "decree": "Nobody takes the last bread from the stockpile"}))
    assert len(w.laws) == 1 and w.laws[0]["by"] == b.id
    assert "LAW (by" in P.scene(w, c) and "last bread" in P.scene(w, c)
    for i in range(12):
        apply_reflection(w, b, json.dumps({"lessons": [], "decree": f"Rule number {i} is important"}))
    assert len(w.laws) == 10
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.leader == b.id and len(w2.laws) == 10


def test_no_decrees_in_the_silent_world_and_succession():
    w, (a, b, c, d, e) = village("B", "stigmergy")
    for o in (a, b, d, e):
        o.affinity[c.id] = 20.0
    w.choose_leader("test")
    apply_reflection(w, c, json.dumps({"lessons": [], "decree": "Store food before the snows come"}))
    assert w.laws == []
    for o in (a, b, e):
        o.affinity[d.id] = 50.0
    w.kill(c, "old age")
    for _ in range(240):
        w.step()
    assert w.leader == d.id
