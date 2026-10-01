import json

from chits.brain.parse import normalize_step, parse_plan
from chits.brain import prompt as P
from chits.sim import actions
from chits.sim.world import World
from chits import views


def run_step(w, a, step, max_ticks=400):
    a.plan = [step]
    for _ in range(max_ticks):
        if not a.plan:
            break
        w.tick += 1
        actions.run(w, a)


def setup():
    w = World("A", "A", 1234, "direct", 96, 4)
    a, b = list(w.agents.values())[:2]
    for c in (a, b):
        c.hunger = c.energy = c.warmth = 100
    return w, a, b


def test_sanitize():
    s = actions.sanitize_name
    assert s("  Pointy   Rock!! ") == "Pointy Rock"
    assert s("x" * 40) == "x" * 24
    assert s("🔥🔥") is None and s("") is None and s(None) is None and s("1234") is None
    assert s("Rock-Knife's") == "Rock-Knife's"


def test_parse_keeps_name():
    st = normalize_step({"do": "experiment", "with": ["stone", "stone"], "name": "Pointy"})
    assert st["name"] == "Pointy" and st["with"] == ["stone", "stone"]
    st = normalize_step({"do": "experiment", "with": ["stone", "stone"], "called": "Flake"})
    assert st["name"] == "Flake"
    assert normalize_step({"do": "give", "name": "Pip", "what": "wood"})["to"] == "Pip"
    p = parse_plan('{"plan":[{"do":"experiment","with":["fiber","fiber"],"name":"Twisty"}]}')
    assert p["steps"][0]["name"] == "Twisty"


def test_first_discoverer_names_it():
    w, a, b = setup()
    evs = []
    w.listeners.append(evs.append)
    a.inventory = {"stone": 2}
    run_step(w, a, {"do": "experiment", "with": ["stone", "stone"], "name": "Pointy Rock!!"})
    assert w.culture_names["recipe:sharp_stone"] == "Pointy Rock"
    disc = [e for e in evs if e.kind == "discovery"]
    assert disc and '"Pointy Rock"' in disc[0].text and disc[0].data.get("local_name") == "Pointy Rock"
    b.inventory = {"stone": 2}
    run_step(w, b, {"do": "experiment", "with": ["stone", "stone"], "name": "Other"})
    assert w.culture_names["recipe:sharp_stone"] == "Pointy Rock"


def test_prompt_and_views_and_persistence():
    w, a, b = setup()
    a.inventory = {"stone": 2}
    run_step(w, a, {"do": "experiment", "with": ["stone", "stone"], "name": "Flakey"})
    assert 'called "Flakey" here' in P.scene(w, a)
    assert '"name"' in P.verb_guide(w)
    row = next(r for r in views.knowledge_table([w]) if r["key"] == "recipe:sharp_stone")
    assert row["worlds"]["A"]["local_name"] == "Flakey"
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.culture_names == {"recipe:sharp_stone": "Flakey"}
    d = w.to_dict()
    d.pop("culture_names")
    assert World.from_dict(json.loads(json.dumps(d))).culture_names == {}
