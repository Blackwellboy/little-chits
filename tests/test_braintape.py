"""BrainTape (research plan R2): a model run recorded, then replayed without the model server, reproduces exactly."""

import asyncio
import json
import socket
import threading
import time

import pytest

from chits.brain.llm import BrainConfig
from chits.brain.tape import BrainTape, TapeMiss, request_key


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def fake_llm():
    import uvicorn
    import fake_llm as F

    F.STATE["latency"] = 0.01
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True


def _facts(out):
    s = json.loads((out / "summary.json").read_text())
    ev = {w: [(e["tick"], e["kind"], e["text"]) for e in map(json.loads, (out / f"events_{w}.jsonl").read_text().splitlines())]
          for w in ("A", "B")}
    return {w: (s["worlds"][w]["stats"]["population"], s["worlds"][w]["stats"]["discoveries"],
                s["worlds"][w]["stats"]["structures"], s["worlds"][w]["decisions"]) for w in ("A", "B")}, ev


def test_a_recorded_model_run_replays_exactly_without_the_model_server(fake_llm, tmp_path):
    from chits.tools.experiment import run_experiment

    def brains(url):
        return {w: BrainConfig(id=f"m{w}", label="Fake", base_url=url, model="fake", max_concurrency=8) for w in ("A", "B")}

    import fake_llm as F

    F.STATE["calls"] = 111  # (the fake's replies follow its call count: this one puts calls on the last tick)
    rec = BrainTape(tmp_path / "tape.jsonl", "record")
    asyncio.run(run_experiment(brains(fake_llm), 1.0, tmp_path / "rec", chits=4, seed=7, mode="versus", tape=rec,
                               max_wall_s=240))
    assert rec.recorded > 10
    play = BrainTape(tmp_path / "tape.jsonl", "replay")
    dead = "http://127.0.0.1:9/v1"  # nothing listens here: every answer must come from the tape
    asyncio.run(run_experiment(brains(dead), 1.0, tmp_path / "play", chits=4, seed=7, mode="versus", tape=play,
                               max_wall_s=240))
    assert play.misses == 0 and play.played == rec.recorded and play.remaining() == 0
    (a_stats, a_events), (b_stats, b_events) = _facts(tmp_path / "rec"), _facts(tmp_path / "play")
    assert a_stats == b_stats
    assert a_events == b_events  # every event, at the same tick, in the same words


def test_a_question_that_isnt_on_the_tape_is_a_divergence_not_an_answer(tmp_path):
    t = BrainTape(tmp_path / "t.jsonl", "record")
    k = request_key("m", [{"role": "user", "content": "hi"}], None, None, None, True)
    t.record(k, "m", {"text": "{}", "latency_ms": 5})
    p = BrainTape(tmp_path / "t.jsonl", "replay")
    assert p.play(k)["text"] == "{}"
    with pytest.raises(TapeMiss):
        p.play(k)  # each recorded answer is used once
    other = request_key("m", [{"role": "user", "content": "hello"}], None, None, None, True)
    with pytest.raises(TapeMiss):
        p.play(other)
    assert p.misses == 2


def test_each_question_gets_its_own_answer_whatever_the_order(tmp_path):
    t = BrainTape(tmp_path / "t.jsonl", "record")
    ka = request_key("m", [{"role": "user", "content": "hungry?"}], None, None, None, True)
    kb = request_key("m", [{"role": "user", "content": "cold?"}], None, None, None, True)
    t.record(ka, "m", {"text": "eat"})
    t.record(kb, "m", {"text": "sleep"})
    p = BrainTape(tmp_path / "t.jsonl", "replay")
    assert p.play(kb)["text"] == "sleep" and p.play(ka)["text"] == "eat"


def test_a_request_that_failed_when_recorded_fails_the_same_way_on_replay(tmp_path):
    import httpx

    from chits.brain.llm import LLMBrain
    from chits.brain.tape import RecordedFailure

    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, text="overloaded")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    rec = BrainTape(tmp_path / "t.jsonl", "record")
    b = LLMBrain(BrainConfig(id="m", base_url="http://model.test/v1", model="m"))
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    b.tape = rec
    msgs = [{"role": "user", "content": "hi"}]
    with pytest.raises(Exception):
        asyncio.run(b.chat(msgs))
    assert asyncio.run(b.chat(msgs))["text"] == "ok" and rec.recorded == 2
    play = BrainTape(tmp_path / "t.jsonl", "replay")
    p = LLMBrain(BrainConfig(id="m", base_url="http://127.0.0.1:9/v1", model="m"))
    p.tape = play
    with pytest.raises(RecordedFailure):
        asyncio.run(p.chat(msgs))
    assert p.stats.failed == 1
    assert asyncio.run(p.chat(msgs))["text"] == "ok" and play.misses == 0 and play.remaining() == 0


def test_an_experiment_repairs_only_when_declared_and_says_so(fake_llm, tmp_path):
    from chits.tools.experiment import run_experiment

    brains = {w: BrainConfig(id=f"m{w}", label="Fake", base_url=fake_llm, model="fake", max_concurrency=8) for w in ("A", "B")}
    import fake_llm as F

    for repair in (False, True):
        F.STATE["calls"] = 0  # (the fake's replies follow its call count: fixed, so failures and repairs happen here)
        out = tmp_path / str(repair)
        asyncio.run(run_experiment(brains, 1.0, out, chits=4, seed=7, mode="versus", repair=repair, max_wall_s=240))
        assert json.loads((out / "manifest.json").read_text())["repair"] is repair
        recs = [json.loads(x) for x in (out / "decisions.jsonl").read_text().splitlines()]
        repairs = [r for r in recs if r.get("style") == "repair"]
        if not repair:
            assert not repairs
        else:
            assert repairs and all(r["repair_reason"] for r in repairs)
        cost = json.loads((out / "summary.json").read_text())["worlds"]["A"]["compute"]  # (item 29, end to end)
        assert cost["tokens"] > 0 and cost["requests"] > 0 and cost["decisions_adopted"] > 0
        assert (cost["repair_rate"] > 0) is repair or not [r for r in repairs if r["world"] == "A"]
        md = (out / "summary.md").read_text()
        assert "## What the thinking cost" in md and "both can talk" in md  # (a versus run)


def test_an_experiment_sends_request_seeds_unless_told_not_to(fake_llm, tmp_path):
    import fake_llm as F
    from chits.tools.experiment import run_experiment

    brains = {w: BrainConfig(id=f"m{w}", label="Fake", base_url=fake_llm, model="fake", max_concurrency=8) for w in ("A", "B")}
    for seeds in (True, False):
        before = F.STATE["seeded"]
        out = tmp_path / str(seeds)
        asyncio.run(run_experiment(brains, 0.25, out, chits=4, seed=7, mode="versus", request_seeds=seeds, max_wall_s=240))
        assert json.loads((out / "manifest.json").read_text())["request_seeds"] is seeds
        assert (F.STATE["seeded"] > before) is seeds
