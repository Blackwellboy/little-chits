import json

from chits.brain import prompt as P
from chits.brain.mind import apply_reflection
from chits.brain.parse import parse_reflection
from chits.sim.world import World

EMBER = {"lessons": ["fire keeps us alive"], "belief": {"name": "The Ember Way", "tenet": "The fire remembers those who feed it"}}


def fresh(wid="A", culture="direct", seed=3, n=4):
    w = World(wid, wid, seed, culture, 64, n)
    ags = list(w.agents.values())
    for a in ags:
        a.hunger = a.energy = a.warmth = a.health = 100.0
        a.plan = []
        a.inventory.clear()
    return w, ags


def run(w, a, step, limit=300):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_parse_reflection_belief_shapes():
    r = parse_reflection(json.dumps(EMBER))
    assert r["belief"] == {"name": "The Ember Way", "tenet": "The fire remembers those who feed it"}
    r = parse_reflection(json.dumps({"lessons": [], "belief": "The sea gives and the sea takes"}))
    assert r["belief"]["name"] == "" and r["belief"]["tenet"].startswith("The sea")
    r = parse_reflection(json.dumps({"lessons": ["x y z w"]}))
    assert r["belief"] is None


def test_founding_from_reflection():
    w, (a, b, c, d) = fresh()
    evs = []
    w.listeners.append(evs.append)
    apply_reflection(w, a, json.dumps(EMBER))
    assert len(w.beliefs) == 1
    bid, bel = next(iter(w.beliefs.items()))
    assert a.belief == bid and bel["name"] == "The Ember Way" and a.id in bel["followers"]
    assert bel["founder"] == a.id
    assert any(e.kind == "belief" and e.importance == 5 and "The Ember Way" in e.text for e in evs)
    assert a.knows_design("shrine")
    # one belief per chit; unnamed beliefs get a name
    apply_reflection(w, a, json.dumps({"lessons": [], "belief": {"name": "Other", "tenet": "Something else entirely"}}))
    assert len(w.beliefs) == 1
    apply_reflection(w, b, json.dumps({"lessons": [], "belief": "The sea gives and the sea takes"}))
    assert len(w.beliefs) == 2 and w.beliefs[b.belief]["name"] == f"The Way of {b.name}"
    assert w.found_belief(c, "The Ember Way", "copying a name is not allowed here") is None
    assert w.found_belief(c, "Tiny", "short") is None


def test_preaching_spreads_in_world_a_only():
    w, (a, b, c, d) = fresh(seed=5)
    apply_reflection(w, a, json.dumps(EMBER))
    for o in (b, c):
        o.x, o.y = a.x, a.y
        a.affinity[o.id] = o.affinity[a.id] = 100.0
    for _ in range(6):
        run(w, a, {"do": "preach"}, limit=60)
    assert b.belief == a.belief or c.belief == a.belief
    assert a.id in w.beliefs[a.belief]["followers"]
    assert '"do":"preach"' in P.verb_guide(w).replace(" ", "")

    wb, (x, y, *_rest) = fresh("B", "stigmergy", seed=5)
    apply_reflection(wb, x, json.dumps(EMBER))
    msg = run(wb, x, {"do": "preach"}, limit=10)
    assert "talk" in msg.lower() and y.belief == ""
    assert '"do":"preach"' not in P.verb_guide(wb).replace(" ", "")


def test_shrines_spread_belief_silently_in_world_b():
    w, (a, b, c, d) = fresh("B", "stigmergy", seed=9)
    apply_reflection(w, a, json.dumps(EMBER))
    pos = w.find_site("shrine", a.x, a.y)
    s = w.place_site("shrine", pos[0], pos[1], a)
    w.complete_structure(s, a)
    assert s.belief == a.belief and "The Ember Way" in s.name
    mood0 = b.mood
    run(w, b, {"do": "pray"}, limit=300)
    assert b.belief == a.belief, b.last_result
    assert b.mood > mood0
    assert '"do":"pray"' in P.verb_guide(w).replace(" ", "")
    # no shrine anywhere -> an honest failure
    w2, (z, *_r) = fresh("B", "stigmergy", seed=10, n=1)
    assert "shrine" in run(w2, z, {"do": "pray"}, limit=5).lower()


def test_scripture_in_world_a():
    w, (a, b, c, d) = fresh(seed=13)
    evs = []
    w.listeners.append(evs.append)
    apply_reflection(w, a, json.dumps(EMBER))
    a.add("clay_tablet", 3)
    for _ in range(3):
        run(w, a, {"do": "write", "what": "belief"}, limit=60)
    tabs = [t for t in w.tablets.values() if t.knowledge == f"belief:{a.belief}"]
    assert len(tabs) == 3, a.last_result
    assert sum(e.kind == "scripture" for e in evs) == 1


def test_scene_children_death_and_persistence():
    w, (a, b, c, d) = fresh(seed=17)
    apply_reflection(w, a, json.dumps(EMBER))
    assert "YOUR BELIEF: The Ember Way" in P.scene(w, a)
    w.convert(b, a.belief, "preached")
    assert b.belief == a.belief and not w.convert(b, a.belief, "preached")
    d2 = json.loads(json.dumps(w.to_dict()))
    w2 = World.from_dict(d2)
    assert w2.beliefs == w.beliefs and w2.agents[a.id].belief == a.belief
    d2.pop("beliefs", None)
    assert World.from_dict(d2).beliefs == {}
    # death leaves the congregation
    w.kill(b, "illness")
    assert b.id not in w.beliefs[a.belief]["followers"]
