"""One-token elections and trades (sim/ballots.py): a model-minded chit's own mind casts its vote and accepts or refuses
an offer with one letter; the world checks every answer, and without one the simulator's rule decides."""

import asyncio

from chits.brain import prompt as P
from chits.brain.mind import Mind
from chits.sim import ballots
from chits.sim.actions import RUNNING, _do_trade
from chits.sim.world import World


def _town(n=5, brain="some-model"):
    w = World("A", "A", 3, "direct", 64, n)
    ags = sorted(w.agents.values(), key=lambda a: a.born)
    for a in ags:
        a.brain = brain
        a.affinity.clear()
    w.leader = ""
    return w, ags


def _likes(voter, *others):
    for o in others:
        voter.affinity[o.id] = 20.0


def test_an_instinct_town_elects_at_once_as_before():
    w, (a, b, c, d, e) = _town(brain="instinct")
    for v in (b, c, d, e):
        _likes(v, a)
    w.choose_leader("test")
    assert w.leader == a.id and not ballots.poll(w)


def test_model_minds_cast_the_votes_and_the_ballot_beats_approval():
    w, (a, b, c, d, e) = _town()
    for v in (b, c, d, e):
        _likes(v, a)  # by approval, a wins 4-1
    _likes(a, b)
    w.choose_leader("test")
    p = ballots.poll(w)
    assert p and w.leader == "" and set(p["voters"]) == {x.id for x in (a, b, c, d, e)}
    assert p["candidates"][0] == a.id and b.id in p["candidates"]
    # the world checks a ballot: nobody backs itself or someone off the ballot, and votes once
    assert not ballots.cast(w, a.id, a.id) and not ballots.cast(w, a.id, "a999")
    assert ballots.cast(w, a.id, b.id) and not ballots.cast(w, a.id, b.id)
    for v in (c, d, e):
        assert ballots.cast(w, v.id, b.id)
    w.choose_leader("again")  # an election under way isn't restarted
    assert ballots.poll(w) is p
    ballots.skip(w, b.id)  # b's mind can't answer: b backs everyone it likes (a)
    ballots.tick(w)
    assert ballots.poll(w) is None and w.leader == b.id
    ev = [x for x in w.events if x.kind == "election"][-1]
    assert ev.data["votes"] == 4 and ev.data["ballots"] == 4


def test_voters_whose_minds_never_answer_vote_by_approval_when_the_poll_closes():
    w, (a, b, c, d, e) = _town()
    for v in (b, c, d, e):
        _likes(v, a)
    w.choose_leader("test")
    ballots.cast(w, b.id, a.id)
    ballots.tick(w)
    assert ballots.poll(w) is not None and w.leader == ""  # still open: others haven't answered
    w.tick += ballots.POLL_TICKS
    ballots.tick(w)
    assert ballots.poll(w) is None and w.leader == a.id


def test_the_sitting_chief_is_always_on_the_ballot():
    w, ags = _town(8)
    chief = ags[-1]
    w.leader = chief.id
    for i, v in enumerate(ags[:-1]):
        _likes(v, *[o for o in ags[:4] if o is not v])
    w.choose_leader("scheduled")
    p = ballots.poll(w)
    assert chief.id in p["candidates"] and len(p["candidates"]) == ballots.POLL_N


def _trade_pair(brain="some-model"):
    w, (a, b, *_) = _town(brain=brain)
    a.x, a.y, b.x, b.y = 10, 10, 11, 10
    a.inventory.clear()
    b.inventory.clear()
    a.inventory["wood"] = 5
    b.inventory["stone"] = 5
    b.activity = "idle"
    step = {"do": "trade", "to": b.name, "give": {"wood": 1}, "get": {"stone": 4}}  # a poor deal for b by value
    return w, a, b, step


def _run(w, a, step, s, n=10):
    r = RUNNING
    for _ in range(n):
        r = _do_trade(w, a, step, s)
        w.tick += 1
        if r != RUNNING:
            break
    return r


def test_a_model_minded_partners_mind_accepts_a_deal_its_value_rule_would_refuse():
    w, a, b, step = _trade_pair()
    assert not w.accepts_trade(b, a, {"wood": 1}, {"stone": 4})
    s = {}
    assert _run(w, a, step, s) == RUNNING  # waiting for b's answer
    o = ballots.pending_offer(w, b.id)
    assert o["from"] == a.id and o["give"] == {"wood": 1}
    assert not ballots.answer_offer(w, b.id, o["tick"] + 1, True)  # an answer to another offer is ignored
    assert ballots.answer_offer(w, b.id, o["tick"], True)
    r = _run(w, a, step, s)
    assert r != RUNNING and a.inventory.get("stone") == 4 and b.inventory.get("wood") == 1


def test_a_refusal_stands_and_no_answer_falls_back_to_value():
    w, a, b, step = _trade_pair()
    step["get"] = {"stone": 1}
    step["give"] = {"wood": 3}  # a good deal for b by value
    assert w.accepts_trade(b, a, {"wood": 3}, {"stone": 1})
    s = {}
    _run(w, a, step, s)
    ballots.answer_offer(w, b.id, ballots.pending_offer(w, b.id)["tick"], False)
    assert "didn't want" in _run(w, a, step, s) and a.inventory.get("stone", 0) == 0
    # asked again, and the mind never answers: b judges by value once the offer's time is up
    s = {}
    _run(w, a, step, s, ballots.OFFER_TICKS)
    assert ballots.pending_offer(w, b.id) is not None
    _run(w, a, step, s, 5)
    assert a.inventory.get("stone") == 1 and ballots.pending_offer(w, b.id) is None


def test_an_instinct_partner_is_never_asked():
    w, a, b, step = _trade_pair("instinct")
    s = {}
    assert "didn't want" in _run(w, a, step, s) and not (w.civic.get("offers") or {})


def test_the_mind_asks_each_voter_and_the_partner_with_one_token():
    w, (a, b, c, d, e) = _town()
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "choose"})
    m.assign(w, "test")
    for v in (b, c, d, e):
        _likes(v, a)
    _likes(a, b)
    w.choose_leader("test")
    seen = []

    async def reply(messages, **kw):
        msgs = messages() if callable(messages) else messages
        seen.append((msgs, kw))
        body = msgs[1]["content"]
        if "offers you" in body:
            return {"text": "A", "latency_ms": 5, "tokens_in": 40, "tokens_out": 1, "top_logprobs": {"A": -0.2, "B": -1.9}}
        rows = [ln for ln in body.splitlines() if ln[:3] in ("A) ", "B) ", "C) ", "D) ")]
        pick = next((ln[0] for ln in rows if b.name in ln), "A")  # every voter backs b where it can
        return {"text": pick, "latency_ms": 5, "tokens_in": 40, "tokens_out": 1, "top_logprobs": {pick: -0.1}}

    m.brains["test"].chat = reply
    w2, ta, tb, step = _trade_pair()
    for x in (ta, tb):
        x.brain = "test"
    s = {}
    _run(w2, ta, step, s, 6)

    async def run():
        for v in (a, b, c, d, e):
            m.hook(w, v)
        m.hook(w2, tb)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()

    asyncio.run(run())
    asks = [(ms, k) for ms, k in seen if ms[0]["content"] in (P.VOTE_SYSTEM, P.TRADE_SYSTEM)]
    assert len(asks) == 6 and all(k["max_tokens"] == 1 for _, k in asks)
    p = ballots.poll(w)
    assert p["ballots"] == {**{x.id: b.id for x in (a, c, d, e)}, b.id: a.id}  # (b can't back itself)
    ballots.tick(w)
    assert w.leader == b.id
    recs = [r for r in m.decisions if r["style"] in ("vote", "trade-offer")]
    assert len(recs) == 6 and all(r["outcome"] == "adopted" for r in recs if r["style"] == "trade-offer")
    assert _run(w2, ta, step, s) != RUNNING and ta.inventory.get("stone") == 4


def test_in_an_experiment_elections_and_trades_stay_the_simulators():
    # F1: nothing may silently replace a model's decision. A poll or an offer that went unanswered would fall back to
    # the simulator's rule, so in an experiment the model isn't asked and the simulator decides, as before (Codex, #48)
    w, (a, b, c, d, e) = _town()
    w.__dict__["_mind_strict"] = True
    for v in (b, c, d, e):
        _likes(v, a)
    w.choose_leader("test")
    assert not ballots.poll(w) and w.leader == a.id
    w, ta, tb, step = _trade_pair()
    w.__dict__["_mind_strict"] = True
    assert "didn't want" in _run(w, ta, step, {}) and not (w.civic.get("offers") or {})


def test_an_offer_left_behind_is_cleared_or_replaced():
    # the partner fell asleep while the trader waited: its pending offer went with the trade, or a reply arriving later
    # sat there unread and every other trader's offer to it skipped its mind (Codex, #48)
    w, a, b, step = _trade_pair()
    s = {}
    _run(w, a, step, s, 6)
    assert ballots.pending_offer(w, b.id)
    b.activity = "sleeping"
    assert "didn't want" in _run(w, a, step, s) and not w.civic["offers"]
    # an offer whose trader went away is replaced once its time is up
    b.activity = "idle"
    _run(w, a, step, {}, 6)
    c = next(o for o in w.agents.values() if o not in (a, b))
    c.x, c.y = b.x + 1, b.y
    c.inventory["wood"] = 5
    t0 = ballots.pending_offer(w, b.id)["tick"]
    assert ballots.offer_verdict(w, c, b, {"wood": 1}, {"stone": 4}, {}) is False  # someone else's is being weighed
    w.tick = t0 + ballots.OFFER_TICKS
    s2 = {}
    assert ballots.offer_verdict(w, c, b, {"wood": 1}, {"stone": 4}, s2) is None
    assert ballots.pending_offer(w, b.id)["from"] == c.id
