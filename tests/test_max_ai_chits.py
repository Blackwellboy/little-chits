"""max_ai_chits: a brain may ask only so many living chits at once; the rest keep their brain but stay on instinct.

Pure unit tests: the selector scores agents without touching a model server. Age-gate workers (gatherers, crafters,
builders, farmers, fishers) outrank scholars while the road to the next age is still open; the sole living knower of a
critical road recipe wins a slot; and 0 (the default) leaves everyone eligible.
"""

from chits.brain.llm import BrainConfig, LLMBrain
from chits.brain.mind import Mind, _ai_chit_score, _select_ai_chits
from chits.sim import projects
from chits.sim.world import World

# A road with two unfinished steps: a design (forge) and a recipe (iron). What the selector sees.
FAKE_ROAD = {
    "age": "Iron Age",
    "steps": [
        {"kind": "design", "key": "forge", "name": "forge", "done": False, "needs": ""},
        {"kind": "recipe", "key": "iron", "name": "iron", "done": False, "needs": ""},
    ],
    "text": "Iron Age: forge ✗ · iron ✗",
}


def _brain(cap):
    return LLMBrain(BrainConfig(id="x", base_url="http://x/v1", max_ai_chits=cap))


def _world(n=6):
    w = World("A", "A", 11, "direct", 96, n)
    for a in w.agents.values():
        a.brain = "x"
    return w, list(w.agents.values())


def test_workers_beat_scholars_when_the_road_is_open(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(6)
    agents[0].job = "gatherer"
    agents[1].job = "crafter"
    for a in agents[2:]:
        a.job = "scholar"
    selected = _select_ai_chits(w, _brain(2), agents)
    assert selected == {agents[0].id, agents[1].id}


def test_scholar_is_deprioritized_while_the_road_is_open(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(2)
    agents[0].job = "gatherer"
    agents[1].job = "scholar"
    assert _select_ai_chits(w, _brain(1), agents) == {agents[0].id}


def test_sole_keeper_of_a_road_recipe_wins_a_slot(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(6)
    agents[0].job = "gatherer"
    agents[1].job = "scholar"  # the sole living knower of iron
    agents[1].knows["recipe:iron"] = {"how": "discovered", "tick": 0}
    for a in agents[2:]:
        a.job = "scholar"
    selected = _select_ai_chits(w, _brain(2), agents)
    assert agents[0].id in selected  # the worker
    assert agents[1].id in selected  # the sole keeper, despite being a scholar
    assert agents[2].id not in selected  # the plain scholar loses out


def test_zero_cap_is_unlimited(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(6)
    for a in agents:
        a.job = "scholar"
    assert _select_ai_chits(w, _brain(0), agents) == {a.id for a in agents}


def test_project_helper_is_scored_above_a_plain_agent(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(3)
    agents[0].job = "gatherer"
    agents[1].job = ""  # not a worker, not a scholar: only a helper
    agents[2].job = ""
    # mark the middle agent as working on the open village project
    w.civic["projects"]["p1"] = {"id": "p1", "kind": "build", "key": "forge", "helpers": {agents[1].id: w.tick}}
    selected = _select_ai_chits(w, _brain(2), agents)
    assert agents[1].id in selected
    assert agents[2].id not in selected


def test_ai_eligible_is_sticky_and_refilled_when_a_chit_dies(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(3)
    agents[0].job = "gatherer"
    agents[1].job = "crafter"
    agents[2].job = "scholar"
    m = Mind(None)
    brain = _brain(2)
    assert m._ai_eligible(w, agents[0], brain)
    assert m._ai_eligible(w, agents[1], brain)
    assert not m._ai_eligible(w, agents[2], brain)
    key = (w.id, brain.id)
    assert m._ai_slots[key]["ids"] == {agents[0].id, agents[1].id}
    # a selected worker dies: the scholar takes the freed slot on the next look
    del w.agents[agents[0].id]
    assert m._ai_eligible(w, agents[2], brain)
    assert agents[2].id in m._ai_slots[key]["ids"]


def test_ai_eligible_recomputes_when_the_cap_changes(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(3)
    agents[0].job = "gatherer"
    agents[1].job = "crafter"
    agents[2].job = "scholar"
    m = Mind(None)
    brain = _brain(2)
    assert m._ai_eligible(w, agents[0], brain)
    assert m._ai_eligible(w, agents[1], brain)
    assert not m._ai_eligible(w, agents[2], brain)
    brain.cfg.max_ai_chits = 3
    assert m._ai_eligible(w, agents[2], brain)
