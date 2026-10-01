"""A model chief chooses the village's next project (one token, scored by logprobs, recorded as a decision); the
world checks the answer, and without one the village's need decides."""

import asyncio

from chits.brain.mind import Mind
from chits.sim import projects
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def _village(culture="direct"):
    w = World("A", "A", 3, culture, 64, 4)
    a = next(iter(w.agents.values()))
    w.first["design:campfire"] = {"tick": 1, "by": a.id, "name": a.name}  # a stone axe is next: cord, sharp stone
    for k in ("design:stockpile", "design:kiln"):
        a.learn(k, "insight", w.tick)
    a.learn("recipe:cord", "discovered", w.tick)
    w.leader = a.id
    return w, a


def test_a_model_chief_is_asked_and_an_instinct_chief_is_not():
    w, a = _village()
    a.brain = "instinct"
    assert projects.next_project(w)["chosen_by"] == "need" and not w.civic.get("ask")
    w.civic["project"] = None
    a.brain = "some-model"
    assert projects.next_project(w) is None
    ask = w.civic["ask"]
    assert ask["leader"] == a.id and 2 <= len(ask["options"]) <= projects.ASK_N
    # the world checks the answer: another chit's, or a choice out of range, is ignored
    assert projects.answer(w, "a999", 0) is None and projects.answer(w, a.id, 99) is None
    p = projects.answer(w, a.id, 1)
    o = ask["options"][1]
    assert (p["kind"], p["key"], p["chosen_by"], p["by"]) == (o["kind"], o["key"], "chief", a.id)
    assert w.civic.get("ask") is None


def test_where_chits_cant_talk_there_is_no_chief_to_ask():
    w, a = _village("stigmergy")
    a.brain = "some-model"
    assert projects.next_project(w)["chosen_by"] == "need"


def test_an_unanswered_question_expires_and_need_decides_and_says_why():
    w, a = _village()
    a.brain = "some-model"
    projects.next_project(w)
    w.tick += projects.ASK_DAYS * TICKS_PER_DAY + 1
    projects.tick(w)
    p = w.civic["project"]
    assert w.civic.get("ask") is None and p["chosen_by"] == "need"
    assert p["fallback"] == "the chief's mind was never asked (unavailable)" and w.civic["fallbacks"] == 1
    ev = [e for e in w.events if e.kind == "project"][-1]
    assert ev.data["fallback"] == p["fallback"] and "chosen by need because" in ev.text
    assert "because the chief's mind was never asked" in projects.scene_line(w, a)
    # asked, but no answer came
    w.civic["project"] = None
    projects.next_project(w)
    w.civic["ask"]["sent"] = True
    w.tick += projects.ASK_DAYS * TICKS_PER_DAY + 1
    projects.tick(w)
    assert w.civic["project"]["fallback"] == "the chief's mind didn't answer"
    # a need pick with no chief to ask is plain need
    w.civic["project"] = None
    a.brain = "instinct"
    assert "fallback" not in projects.next_project(w)


def test_the_mind_puts_the_question_to_the_chiefs_model():
    w, a = _village()
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "choose"})
    m.assign(w, "test")
    brain = m.brains["test"]
    seen = []

    async def reply(messages, **kw):
        msgs = messages() if callable(messages) else messages
        seen.append((msgs, kw))
        return {"text": "B", "latency_ms": 5, "tokens_in": 50, "tokens_out": 1, "top_logprobs": {"B": -0.1, "A": -2.5}}

    brain.chat = reply
    projects.next_project(w)
    ask = w.civic["ask"]

    async def run():
        m.hook(w, a)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()

    asyncio.run(run())
    msgs, kw = next((m_, k) for m_, k in seen if "chief of" in m_[1]["content"])
    assert kw["max_tokens"] == 1 and "B) " in msgs[1]["content"]
    p = w.civic["project"]
    assert p["chosen_by"] == "chief" and p["key"] == ask["options"][1]["key"]
    rec = next(r for r in m.decisions if r["style"] == "chief-project")
    assert rec["outcome"] == "adopted" and rec["choice"]["requested"] == "B"
