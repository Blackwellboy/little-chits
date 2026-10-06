"""Decide brains (prompt_style "decide", brains.json only): the drafted menu goes to the SystemOne
decision API; a missing endpoint or a stray answer falls back to the one-token chat vote."""

import asyncio
import json

import httpx
import pytest

from chits.brain import sysone as SYS
from chits.brain.llm import BrainConfig, LLMBrain
from chits.brain.mind import Mind
from chits.sim.world import World


def _brain(handler):
    b = LLMBrain(BrainConfig(id="t", base_url="http://127.0.0.1:9/v1", model="tev1:0.8b"))
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return b


def _sysone_reply(choice, probs, out_tokens=1):
    def handler(request):
        assert request.url.path == "/v1/systemone"
        question = next(iter(json.loads(request.content)["questions"]))
        body = {"model": "tev1:0.8b",
                "answers": {question: {
                    "type": "choice", "choice": choice, "probabilities": probs, "confidence": 0.2}},
                "usage": {"input_tokens": 144, "output_tokens": out_tokens}}
        return httpx.Response(200, json=body)
    return handler


CRITERIA = {"A": "gather berries", "B": "hunt rabbit", "C": "rest"}


def test_vote_maps_criteria_to_choice():
    async def run():
        b = _brain(_sysone_reply("B", {"A": 0.1, "B": 0.7, "C": 0.2}))
        try:
            return await SYS.vote(b, "a hungry chit", CRITERIA)
        finally:
            await b.close()
    v = asyncio.run(run())
    assert v["choice"] == "B" and v["probabilities"]["B"] == 0.7
    assert v["tokens_out"] == 1 and v["text"] == "B"


def test_unknown_answer_key_raises_bad_key():
    async def run():
        b = _brain(_sysone_reply("Z", {"A": 0.5, "B": 0.5}))
        try:
            await SYS.vote(b, "state", {"A": "x", "B": "y"})
        finally:
            await b.close()
    with pytest.raises(SYS.SystemOneBadKey):
        asyncio.run(run())


def test_missing_endpoint_raises_missing():
    async def run():
        b = _brain(lambda request: httpx.Response(404, json={"error": "not found"}))
        try:
            await SYS.vote(b, "state", CRITERIA)
        finally:
            await b.close()
    with pytest.raises(SYS.SystemOneMissing):
        asyncio.run(run())


def _setup(style="decide"):
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 90.0
    m = Mind(None)
    m.upsert({"id": "test", "model": "tev1:0.8b", "base_url": "http://192.168.10.103:11434/v1",
              "prompt_style": style})
    m.assign(w, "test")
    return w, a, m, m.brains["test"]


def _drain(m):
    async def run():
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())


def test_decide_ask_records_decide_style_and_flag(monkeypatch):
    w, a, m, b = _setup()
    seen = []
    monkeypatch.setattr(m, "_choose", lambda *args: seen.append(args) or asyncio.sleep(0))
    async def run():
        m._ask(w, a, b)
    asyncio.run(run())
    asyncio.run(m.close())
    assert len(seen) == 1
    _, _, _, _, rec, sent, _cascade = seen[0]
    assert rec["style"] == "decide" and sent["decide"] is True


def test_decide_vote_executes_the_chosen_draft(monkeypatch):
    w, a, m, b = _setup()
    votes = []

    async def fake_vote(brain, state, criteria):
        votes.append((state, criteria))
        return {"text": "B", "latency_ms": 4, "tokens_in": 100, "tokens_out": 1, "queue_ms": 0,
                "top_logprobs": {}, "finish_reason": "stop", "answered": True,
                "choice": "B", "probabilities": {"A": 0.2, "B": 0.6, "C": 0.2}, "confidence": 0.2}

    async def no_chat(*args, **kwargs):
        raise AssertionError("the chat vote must not run when SystemOne answers")

    monkeypatch.setattr(SYS, "vote", fake_vote)
    monkeypatch.setattr(b, "chat", no_chat)

    async def run():
        m._ask(w, a, b)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())

    assert len(votes) == 1 and set(votes[0][1]) >= {"A", "B"}
    rec = m.decisions[-1]
    assert rec["parse"] == "choice" and rec["choice"]["requested"] == "B"
    assert a.pending_plan is not None


def test_decide_falls_back_to_the_chat_vote(monkeypatch):
    w, a, m, b = _setup()

    async def missing(brain, state, criteria):
        raise SYS.SystemOneMissing("no decision endpoint here")

    async def chat_vote(messages, **kw):
        return {"text": "A", "latency_ms": 6, "tokens_in": 100, "tokens_out": 1, "queue_ms": 0,
                "top_logprobs": {"A": -0.1, "B": -2.0}, "finish_reason": "stop", "answered": False}

    monkeypatch.setattr(SYS, "vote", missing)
    monkeypatch.setattr(b, "chat", chat_vote)

    async def run():
        m._ask(w, a, b)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())

    rec = m.decisions[-1]
    assert rec["parse"] == "choice" and rec["choice"]["requested"] == "A"
    assert a.pending_plan is not None


def _letter_vote(choice, probs):
    async def fake(brain, state, options, question="pick"):
        assert options and state
        return {"text": choice, "latency_ms": 4, "tokens_in": 50, "tokens_out": 1, "queue_ms": 0,
                "top_logprobs": {}, "finish_reason": "stop", "answered": True, "choice": choice,
                "probabilities": probs, "confidence": 0.3}
    return fake


def test_decide_letters_maps_labels_to_a_letter():
    async def run():
        b = _brain(_sysone_reply("B", {"A": 0.3, "B": 0.7}))
        try:
            return await SYS.decide_letters(b, "pick one", ["x", "y"])
        finally:
            await b.close()
    v = asyncio.run(run())
    assert v["choice"] == "B" and v["text"] == "B"


def test_letter_vote_decides_an_election(monkeypatch):
    w, a, m, b = _setup()
    picked = []
    monkeypatch.setattr(SYS, "vote", _letter_vote("B", {"A": 0.3, "B": 0.7}))
    msgs = [{"role": "system", "content": "Back one."},
            {"role": "user", "content": "A) Ann\nB) Bob\nAnswer with one letter."}]

    async def run():
        m._ask_letter(w, a, b, "vote", msgs, 2, picked.append, lambda: picked.append("skipped"),
                      {"options": ["Ann", "Bob"]})
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())

    assert picked == [1]
    rec = m.decisions[-1]
    assert rec["parse"] == "choice" and rec["choice"]["requested"] == "B"
    assert rec["choice"]["confidence"] == 0.7


def test_letter_vote_falls_back_to_chat(monkeypatch):
    w, a, m, b = _setup()
    picked = []

    async def missing(brain, state, options, question="pick"):
        raise SYS.SystemOneMissing("gone")

    async def chat_vote(messages, **kw):
        return {"text": "A", "latency_ms": 5, "tokens_in": 40, "tokens_out": 1, "queue_ms": 0,
                "top_logprobs": {"A": -0.2}, "finish_reason": "stop", "answered": False}

    monkeypatch.setattr(SYS, "decide_letters", missing)
    monkeypatch.setattr(b, "chat", chat_vote)
    msgs = [{"role": "user", "content": "A) yes\nB) no"}]

    async def run():
        m._ask_letter(w, a, b, "trade-offer", msgs, 2, picked.append, lambda: picked.append(None),
                      {"options": ["accept", "refuse"]})
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())

    assert picked == [0]
    assert m.decisions[-1]["choice"]["requested"] == "A"


def test_chief_project_decided(monkeypatch):
    import chits.sim.projects as PJ

    w, a, m, b = _setup()
    monkeypatch.setattr(SYS, "vote", _letter_vote("A", {"A": 0.8, "B": 0.2}))
    monkeypatch.setattr(PJ, "option_words", lambda o: o["key"])
    monkeypatch.setattr(PJ, "answer", lambda world, leader, i: {"chosen_by": "chief"})
    opts = [{"kind": "k", "key": "well", "why": "water", "extra": {}},
            {"kind": "k", "key": "hut", "why": "shelter", "extra": {}}]
    ask = {"options": opts, "leader": a.id, "tick": w.tick}

    async def run():
        m._ask_chief(w, a, b, ask)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())

    rec = m.decisions[-1]
    assert rec["parse"] == "choice" and rec["outcome"] == "adopted"
    assert rec["choice"]["requested"] == "A" and rec["choice"]["confidence"] == 0.8


def test_vote_rejects_a_single_candidate_without_calling():
    async def run():
        b = LLMBrain(BrainConfig(id="t", base_url="http://127.0.0.1:9/v1", model="tev1-8k"))
        try:
            await SYS.vote(b, "state", {"A": "only"})
        finally:
            await b.close()
    with pytest.raises(SYS.SystemOneBadKey):
        asyncio.run(run())


def test_chief_single_candidate_runs_unopposed(monkeypatch):
    import chits.sim.projects as PJ

    w, a, m, b = _setup()

    async def no_vote(*args, **kwargs):
        raise AssertionError("no contest: the model must not be asked")

    monkeypatch.setattr(SYS, "vote", no_vote)
    monkeypatch.setattr(PJ, "option_words", lambda o: o["key"])
    monkeypatch.setattr(PJ, "answer", lambda world, leader, i: {"chosen_by": "chief"})
    ask = {"options": [{"kind": "k", "key": "well", "why": "water", "extra": {}}],
           "leader": a.id, "tick": w.tick}
    m._ask_chief(w, a, b, ask)  # synchronous: no contest needs no request
    rec = m.decisions[-1]
    assert rec["parse"] == "uncontested" and rec["outcome"] == "adopted"
