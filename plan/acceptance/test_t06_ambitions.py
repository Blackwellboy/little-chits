import json

from chits.brain import prompt as P
from chits.brain.parse import parse_lessons, parse_reflection
from chits.sim.agent import Agent
from chits.sim.world import World
from chits import views


def test_parse_reflection():
    r = parse_reflection('{"lessons":["Store food before winter."],"ambition":"  Build the first monument  "}')
    assert {k: r[k] for k in ("lessons", "ambition")} == {"lessons": ["Store food before winter."], "ambition": "Build the first monument"}
    assert parse_reflection('{"lessons":["Fires need wood."],"dream":"' + "x" * 300 + '"}')["ambition"] == "x" * 120
    assert parse_reflection('{"lessons":["Fires need wood."]}')["ambition"] == ""
    assert parse_reflection('{"lessons":[],"ambition":"eh"}')["ambition"] == ""
    assert parse_lessons('{"lessons":["Fires need wood."],"ambition":"Be kind"}') == ["Fires need wood."]


def test_apply_reflection_sets_and_announces():
    from chits.brain.mind import apply_reflection

    w = World("A", "A", 3, "direct", 96, 4)
    a = next(iter(w.agents.values()))
    evs = []
    w.listeners.append(evs.append)
    w.tick = 500
    apply_reflection(w, a, '{"lessons":["Bread is filling."],"ambition":"Invent copper tools"}')
    assert a.ambition == "Invent copper tools" and a.ambition_since == 500
    assert "Bread is filling." in a.lessons
    amb = [e for e in evs if e.kind == "ambition"]
    assert len(amb) == 1 and amb[0].importance == 3 and "Invent copper tools" in amb[0].text
    apply_reflection(w, a, '{"lessons":[],"ambition":"invent COPPER tools"}')  # same ambition: no new event
    assert len([e for e in evs if e.kind == "ambition"]) == 1
    for i in range(10):
        apply_reflection(w, a, json.dumps({"lessons": [f"Lesson number {i}."]}))
    assert len(a.lessons) <= 6


def test_prompt_and_views_and_persistence():
    w = World("A", "A", 3, "direct", 96, 4)
    a = next(iter(w.agents.values()))
    a.ambition = "Build a library"
    assert "YOUR AMBITION: Build a library" in P.scene(w, a)
    sys_ = P.reflection_messages(w, a)[0]["content"] + P.reflection_messages(w, a)[1]["content"]
    assert '"ambition"' in sys_ and "Build a library" in sys_
    assert views.agent_detail(w, a)["ambition"] == "Build a library"
    d = a.to_dict()
    assert Agent.from_dict(json.loads(json.dumps(d))).ambition == "Build a library"
    d.pop("ambition")
    d.pop("ambition_since")
    assert Agent.from_dict(d).ambition == ""


def test_fake_llm_dreams():
    import fake_llm

    src = open(fake_llm.__file__).read()
    assert '"ambition"' in src
