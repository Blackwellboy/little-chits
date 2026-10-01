import json
import random

from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.brain.parse import parse_plan
from chits.sim.agent import JOBS
from chits.sim.world import World


def adults(w):
    out = []
    for a in w.agents.values():
        a.born = -240 * 10
        a.skills = {}
        a.stats = {}
        out.append(a)
    return out


def test_auto_jobs_follow_practice():
    w = World("A", "A", 3, "direct", 64, 4)
    evs = []
    w.listeners.append(evs.append)
    a, b, c, d = adults(w)
    a.skills = {"farming": 2.0, "building": 0.5}
    b.skills = {"building": 1.2, "farming": 1.1}  # not specialised enough
    c.skills = {"gathering": 2.0}
    c.stats = {"fish": 12}
    d.skills = {"crafting": 3.0}
    d.stats = {"read": 2, "wrote": 1}
    w.assign_jobs()
    assert (a.job, b.job, c.job, d.job) == ("farmer", "", "fisher", "scholar")
    assert a.job_source == "auto"
    firsts = [e for e in evs if e.kind == "job" and e.importance == 3]
    assert any("first farmer" in e.text for e in firsts)
    assert w.stats()["jobs"].get("farmer") == 1
    assert "You work as a farmer" in P.scene(w, a)


def test_chosen_job_sticks():
    w = World("A", "A", 5, "direct", 64, 2)
    a, b = adults(w)
    plan = parse_plan(json.dumps({"goal": "feed us", "job": "Farmer", "steps": [{"do": "plant"}]}))
    assert plan["job"] == "farmer"
    assert parse_plan(json.dumps({"goal": "x", "role": "wizard", "steps": [{"do": "rest"}]}))["job"] == ""
    a.job, a.job_source = "builder", "chosen"
    a.skills = {"farming": 5.0}
    w.assign_jobs()
    assert a.job == "builder"
    d = json.loads(json.dumps(w.to_dict()))
    assert World.from_dict(d).agents[a.id].job == "builder"
    assert set(JOBS) >= {"farmer", "builder", "crafter", "gatherer", "fisher", "scholar", "explorer"}


def test_jobs_steer_instinct():
    ins = Instinct()

    def share(job, words):
        w = World("A", "A", 11, "direct", 96, 6)
        a = adults(w)[0]
        a.hunger = a.energy = a.warmth = 100.0
        a.job, a.job_source = job, "chosen"
        hits = n = 0
        for t in range(300):
            w.tick = 1000 + t * 7
            a.hunger = a.energy = a.warmth = 100.0
            p = ins._progress(w, a, random.Random(t))
            if p:
                n += 1
                hits += any(k in p["goal"] for k in words)
        return hits / max(1, n)

    assert share("explorer", ("explore",)) > share("", ("explore",)) + 0.1
