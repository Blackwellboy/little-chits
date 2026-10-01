import json

from chits.brain import prompt as P
from chits.sim.world import World


def pair(seed=3):
    w = World("A", "A", seed, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    for c in (a, b):
        c.hunger = c.energy = c.warmth = c.health = 100.0
        c.inventory.clear()
        c.plan = []
    b.x, b.y = a.x, a.y
    return w, a, b


def run(w, a, step, limit=200):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_told_becomes_worked_and_lineage():
    w, a, b = pair()
    w.learned(a, "recipe:cord", "discovered")
    assert a.knows["recipe:cord"]["status"] == "worked"
    run(w, a, {"do": "teach", "to": b.name, "what": "cord"})
    assert b.knows["recipe:cord"]["status"] == "told"
    assert "untried" in P.scene(w, b)
    d = [x for x in w.deliveries if x["channel"] == "teach"]
    assert d and d[-1]["from"] == a.id and d[-1]["to"] == b.id and d[-1]["knowledge"] == "recipe:cord"
    b.add("fiber", 2)
    run(w, b, {"do": "craft", "what": "cord"})
    assert b.knows["recipe:cord"]["status"] == "worked" and b.knows["recipe:cord"]["worked_tick"] >= 0
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.agents[b.id].knows["recipe:cord"]["status"] == "worked" and w2.deliveries


def test_speech_is_recorded_per_listener():
    w, a, b = pair(5)
    run(w, a, {"do": "say", "to": b.name, "text": "Clay is by the river"})
    says = [x for x in w.deliveries if x["channel"] == "say"]
    assert says and says[-1]["to"] == b.id and "river" in says[-1]["message"]


def test_lessons_cite_memories():
    w, a, b = pair(7)
    a.remember(w.tick, "Slept beside a lit campfire and woke up warm", 3, "event")
    a.remember(w.tick, "Warmth recovered by the fire", 3, "event")
    ids = [m.id for m in a.memories]
    assert len(set(ids)) == len(ids) and ids == sorted(ids)
    msgs = P.reflection_messages(w, a)
    assert f"[m{ids[-1]}]" in msgs[-1]["content"]
    from chits.brain.mind import apply_reflection

    apply_reflection(w, a, json.dumps({"lessons": [{"text": "Fire keeps me warm at night", "from": ids[-2:]},
                                                   {"text": "Copper cures sickness", "from": [9999]}]}))
    assert "Fire keeps me warm at night" in a.lessons and "Copper cures sickness" in a.lessons
    assert a.lesson_sources["Fire keeps me warm at night"] == ids[-2:]
    assert a.lesson_sources["Copper cures sickness"] == []
