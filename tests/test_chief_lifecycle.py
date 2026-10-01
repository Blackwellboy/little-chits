"""The chief's choice, instrumented through its whole life (audit F12) before anything about it changes: on the live
run most projects fell to need ("never asked", "didn't answer", "chief changed"), and the fix depends on which."""

import asyncio

from chits import diag
from chits.brain.mind import Mind
from chits.sim import projects as PJ
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def setup(monkeypatch=None):
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 95.0
    w.tick = TICKS_PER_DAY + 30
    w.leader = a.id
    w.flags["say"] = True
    m = Mind(None)
    m.upsert({"id": "chief", "model": "fake", "base_url": "http://127.0.0.1:9/v1"})
    m.assign(w, "chief")
    spawned = []
    m._spawn = lambda coro: spawned.append(coro)
    m._ask = lambda world, agent, brain: None
    if monkeypatch is not None:
        monkeypatch.setattr(PJ, "candidates", lambda world: [(1.0, "build", "stockpile", "why", {}),
                                                            (0.5, "build", "well", "why", {})])
    return w, a, m, m.brains["chief"], spawned


def fake_reply(brain, letter="A"):
    async def chat(msgs, **kw):
        return {"text": letter, "top_logprobs": {letter: -0.05}, "latency_ms": 1234.0, "queue_ms": 56.0}
    brain.chat = chat


def test_asked_sent_answered_adopted(monkeypatch):
    w, a, m, b, spawned = setup(monkeypatch)
    PJ.next_project(w)
    assert diag.of(w).chief["asked"] == 1
    m.hook(w, a)
    assert diag.of(w).chief["sent"] == 1 and len(spawned) == 1
    fake_reply(b)
    asyncio.run(spawned[0])
    d = diag.of(w)
    assert d.chief["answered"] == 1 and d.chief["adopted"] == 1 and w.civic["project"]["key"] == "stockpile"
    log = d.chief_log[-1]
    assert log["ended"] == "adopted" and log["queue_ms"] == 56 and log["latency_ms"] == 1234
    assert log["sent"] >= log["asked"]
    s = diag.chief_summary(w)
    assert s["ended"] == {"adopted": 1} and s["latency_ms"] == 1234


def test_a_chief_whose_brain_is_down_is_never_asked(monkeypatch):
    w, a, m, b, spawned = setup(monkeypatch)
    b.cfg.enabled = False
    PJ.next_project(w)
    m.hook(w, a)
    assert not spawned and diag.of(w).chief["blocked: the chief's brain unavailable"] == 1
    w.tick += PJ.ASK_DAYS * TICKS_PER_DAY + 1
    PJ._expire_ask(w)
    assert diag.of(w).chief_log[-1]["ended"] == "expired: the chief's mind was never asked (unavailable)"
    assert w.civic["project"]["chosen_by"] != "chief"  # (need decided)


def test_each_way_a_question_expires_is_told_apart(monkeypatch):
    w, a, m, b, spawned = setup(monkeypatch)
    PJ.next_project(w)
    m.hook(w, a)  # sent, never answered
    w.tick += PJ.ASK_DAYS * TICKS_PER_DAY + 1
    PJ._expire_ask(w)
    assert diag.of(w).chief_log[-1]["ended"] == "expired: the chief's mind didn't answer"
    w.civic["project"] = None
    PJ.next_project(w)
    w.leader = list(w.agents)[1]  # a new chief before the old one answered
    PJ._expire_ask(w)
    assert diag.of(w).chief_log[-1]["ended"] == "expired: the chief changed before choosing"


def test_an_answer_after_the_question_expired_is_stale_on_arrival(monkeypatch):
    w, a, m, b, spawned = setup(monkeypatch)
    PJ.next_project(w)
    m.hook(w, a)
    w.tick += PJ.ASK_DAYS * TICKS_PER_DAY + 1
    PJ._expire_ask(w)
    fake_reply(b)
    asyncio.run(spawned[0])
    d = diag.of(w)
    assert d.chief["answered"] == 1 and d.chief["stale on arrival"] == 1
    assert d.chief_log[-1]["ended"].startswith("expired")  # (the first ending stands; the late answer is counted)


def test_leader_changes_are_counted():
    w = World("A", "A", 3, "direct", 64, 8)
    adults = list(w.agents.values())
    w.leader = adults[0].id
    for v in adults:
        for o in adults:
            if o is not v:
                v.affinity[o.id] = 20.0 if o is adults[1] else 0.0
    w.choose_leader("scheduled")
    assert w.leader == adults[1].id and diag.of(w).chief["leader changed"] == 1
