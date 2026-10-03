"""Size the world to the model: a new game started with 18 chits whatever the model's speed, and a 5-second model
with 4 slots answered a few percent of its world's decisions without the user learning why.

- a brain's "keeps up with about N chits" comes from diag.py's estimate, on its live replies or a short probe;
- the probe runs only when asked for, on a client of its own;
- the New game advice is the slowest chosen model's number (halved when it drives both worlds); instinct has no limit;
- the `little-chits` command's first run prints the same hint;
- nothing here resizes a running world.
"""

import asyncio
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from chits import sizing
from chits.brain.llm import BrainConfig, LLMBrain
from chits.brain.mind import Mind
from chits.diag import keeps_up_with, speed_rating


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def fake():
    import uvicorn
    import fake_llm as F

    old = dict(F.STATE)
    F.STATE.update(latency=0.05, garbage_rate=0.0)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1", F.STATE
    server.should_exit = True
    th.join(timeout=5)
    F.STATE.clear()
    F.STATE.update(old)


@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "8")
    return tmp_path


def _brain(slots=4, latencies=(), **cfg):
    b = LLMBrain(BrainConfig(id=cfg.pop("id", "m"), base_url="http://127.0.0.1:9/v1", max_concurrency=slots, **cfg))
    b.latencies.extend(latencies)
    return b


def test_the_number_is_the_diagnostics_estimate():
    assert keeps_up_with(4, 5000) == 12 and keeps_up_with(8, 2000) == 60 and keeps_up_with(4, 0) == 0
    assert speed_rating(4, 26000, 50)["capacity"] == keeps_up_with(4, 26000) == 2


def test_a_brain_says_how_many_chits_it_keeps_up_with_from_its_live_replies():
    cap = sizing.capacity(_brain(4, [4000, 5000, 5000, 6000, 30000]))
    assert cap["chits"] == 12 and cap["source"] == "live" and cap["text"] == "Keeps up with about 12 chits."
    assert cap["latency_ms"] == 5000 and cap["slots"] == 4
    none = sizing.capacity(_brain(4))
    assert none["chits"] is None and none["source"] is None and none["text"] == "Speed not measured yet."
    assert sizing.capacity(_brain(1, [60000] * 3))["text"] == "Too slow to keep up with even one chit."


async def test_a_brain_with_no_replies_yet_is_measured_by_a_short_probe_of_real_decisions(fake):
    url, state = fake
    b = LLMBrain(BrainConfig(id="f", base_url=url, max_concurrency=4))
    before = state["calls"]
    cap = await sizing.measure(b)
    assert state["calls"] - before == sizing.PROBE_SAMPLES  # a handful of requests, and only now
    assert cap["source"] == "probe" and cap["chits"] == keeps_up_with(4, cap["latency_ms"]) > 0
    assert 20 <= cap["latency_ms"] <= 2000
    assert b.stats.requests == 0 and not b.latencies  # the brain's own record is left alone
    assert sizing.capacity(b) == cap  # remembered: asking again costs nothing
    # a brain with live replies is not probed
    b.latencies.extend([1000, 1000, 1000])
    before = state["calls"]
    assert (await sizing.measure(b))["source"] == "live" and state["calls"] == before


async def test_a_choosing_brain_is_measured_by_one_token_choices(fake):
    url, state = fake
    state["letters"] = True
    try:
        b = LLMBrain(BrainConfig(id="c", base_url=url, max_concurrency=2, prompt_style="choose"))
        cap = await sizing.measure(b)
        assert cap["source"] == "probe" and cap["chits"] > 0 and b.probe["valid"] == sizing.PROBE_SAMPLES
        # a cascade writes a full plan for a share of its choices: its number is the smaller one
        c = LLMBrain(BrainConfig(id="c2", base_url=url, max_concurrency=2, prompt_style="cascade", escalate_share=1.0))
        before = state["calls"]
        await sizing.measure(c)
        assert state["calls"] - before == sizing.PROBE_SAMPLES + sizing.PROBE_SAMPLES // 2
    finally:
        state.pop("letters")


def test_a_cascade_brains_live_number_counts_the_full_plans_it_writes():
    # one-token choices are the many, so the median of all replies was a choice's time and the plans (17-56 s on
    # a live 9B model) went uncounted: /api/sizing advised far more chits than the model served (Codex review)
    b = _brain(8, prompt_style="cascade", escalate_share=0.3)
    for ms in [200] * 30 + [20000] * 5:
        b.latencies.append(ms)
        (b.choice_latencies if ms == 200 else b.plan_latencies).append(ms)
    cap = sizing.capacity(b)
    assert cap["source"] == "live" and cap["latency_ms"] == 200 + 0.3 * 20000 == 6200
    assert cap["chits"] == keeps_up_with(8, 6200) == 19  # (the mixed median said 200 ms: 600 chits)
    # until it has written a plan its choices alone do not say how fast it is: not measured, so a probe is due
    fresh = _brain(8, prompt_style="cascade")
    fresh.latencies.extend([200] * 30)
    fresh.choice_latencies.extend([200] * 30)
    assert sizing.capacity(fresh)["source"] is None and sizing.capacity(fresh)["chits"] is None
    # a brain that only chooses, or only writes plans, is read as before
    for style in ("choose", "full"):
        assert sizing.capacity(_brain(8, [200] * 30, prompt_style=style))["chits"] == 600


async def test_a_cascade_brain_with_only_choices_so_far_is_probed_and_replies_are_kept_apart(fake):
    import httpx

    url, state = fake
    state["letters"] = True
    try:
        b = LLMBrain(BrainConfig(id="c3", base_url=url, max_concurrency=2, prompt_style="cascade", json_mode=False))
        await b.chat([{"role": "user", "content": "A or B?"}], max_tokens=1, json_reply=False)
        await b.chat([{"role": "user", "content": "A or B?"}], max_tokens=1, json_reply=False)
        await b.chat([{"role": "user", "content": "A or B?"}], max_tokens=1, json_reply=False)
        assert len(b.choice_latencies) == 3 and not b.plan_latencies and len(b.latencies) == 3
        before = state["calls"]
        cap = await sizing.measure(b)
        assert cap["source"] == "probe" and state["calls"] > before  # (three live replies used to bypass the probe)
        await b.chat([{"role": "user", "content": "What do you do next?"}])
        assert len(b.plan_latencies) == 1 and sizing.capacity(b)["source"] == "live"
        await b.close()
    finally:
        state.pop("letters")


async def test_a_probe_that_gets_no_answer_says_so():
    b = LLMBrain(BrainConfig(id="dead", base_url=f"http://127.0.0.1:{_free_port()}/v1", timeout=2))
    cap = await sizing.measure(b, samples=1)
    assert cap["chits"] is None and cap["source"] is None and cap["text"].startswith("Could not measure its speed:")


def _mind(tmp_path, **brains):
    m = Mind(tmp_path / "brains.json")
    for bid, (slots, ms) in brains.items():
        m.upsert({"id": bid, "label": bid.title(), "base_url": "http://127.0.0.1:9/v1", "max_concurrency": slots})
        m.brains[bid].latencies.extend([ms] * 3 if ms else [])
    return m


def test_a_new_game_is_sized_to_the_slowest_model_and_instinct_has_no_limit(tmp_path):
    m = _mind(tmp_path, fast=(8, 2000), slow=(4, 5000), unknown=(4, 0), huge=(16, 500))
    r = sizing.recommend(m, {"A": "slow"})
    assert r["chits"] == 12 and r["text"] == "Slow keeps up with about 12 chits."
    assert sizing.recommend(m, {"A": "fast", "B": "slow"})["chits"] == 12
    both = sizing.recommend(m, {"A": "slow", "B": "slow"})  # one model for two worlds: half each
    assert both["chits"] == 6 and both["text"] == "Slow keeps up with about 12 chits, shared by 2 worlds: about 6 each."
    assert sizing.recommend(m, {"A": "huge"})["chits"] == 60  # (a new game takes 2..60)
    for brains in ({"A": "instinct", "B": "instinct"}, {}):
        r = sizing.recommend(m, brains)
        assert r["chits"] is None and "no limit" in r["text"] and r["unmeasured"] == []
    assert sizing.recommend(m, {"A": "instinct", "B": "slow"})["chits"] == 12
    r = sizing.recommend(m, {"A": "fast", "B": "unknown"})
    assert r["chits"] is None and r["unmeasured"] == ["unknown"] and "not measured" in r["text"]


def test_the_new_game_dialog_gets_its_advice_and_a_running_world_is_never_resized(env, fake):
    from fastapi.testclient import TestClient

    from chits.app import R, app

    url, state = fake
    with TestClient(app) as c:
        rt = R()
        assert c.post("/api/brains", json={"id": "m1", "label": "M1", "base_url": url, "max_concurrency": 2}).status_code == 200
        c.post("/api/worlds/A/brain", json={"brain": "m1"})
        row = c.get("/api/brains").json()["brains"][0]
        assert row["capacity"]["chits"] is None and row["capacity"]["text"] == "Speed not measured yet."
        before = state["calls"]
        r = c.post("/api/sizing", json={"brains": {"A": "m1", "B": "instinct"}}).json()
        assert r["chits"] is None and r["unmeasured"] == ["m1"] and state["calls"] == before  # (asking costs nothing)
        r = c.post("/api/sizing", json={"brains": {"A": "m1", "B": "instinct"}, "measure": True}).json()
        cap = c.get("/api/brains").json()["brains"][0]["capacity"]
        assert cap["source"] == "probe" and cap["chits"] > 0 and cap["text"].startswith("Keeps up with about ")
        assert r["chits"] == max(2, min(60, cap["chits"])) and r["limited_by"] == "m1" and r["text"].startswith("M1 keeps up")
        assert c.post("/api/sizing", json={"brains": {"A": "instinct"}}).json()["chits"] is None
        # the Brains dialog's own button
        again = c.post("/api/brains/m1/capacity").json()
        assert again["source"] == "probe" and again["chits"] > 0
        assert c.post("/api/brains/nobody/capacity").status_code == 404
        # advice only: the worlds are as they were
        assert {wid: len(w.agents) for wid, w in rt.worlds.items()} == {"A": 8, "B": 8}
        assert rt.mind.world_brain["A"] == "m1" and all(w.tick == 0 for w in rt.worlds.values())


def test_the_sizing_routes_need_the_access_token_like_every_private_route(env, monkeypatch):
    from fastapi.testclient import TestClient

    from chits.app import app

    monkeypatch.setenv("CHITS_TOKEN", "sesame")
    with TestClient(app) as c:
        assert c.post("/api/sizing", json={"brains": {}}).status_code == 401
        assert c.post("/api/brains/m1/capacity").status_code == 401
        ok = {"Authorization": "Bearer sesame"}
        assert c.post("/api/sizing", json={"brains": {}}, headers=ok).status_code == 200
        assert c.post("/api/brains/m1/capacity", headers=ok).status_code == 404


def test_the_hint_says_whether_the_model_keeps_up_and_what_size_it_could_drive(env):
    from chits.runtime import Runtime

    rt = Runtime()
    assert sizing.hint_lines(rt) == []  # instinct: nothing to say
    rt.mind.upsert({"id": "m1", "label": "M1", "base_url": "http://127.0.0.1:9/v1", "max_concurrency": 4})
    rt.mind.assign(rt.worlds["A"], "m1")
    assert sizing.hint_lines(rt) == ["M1: Speed not measured yet."]
    rt.mind.brains["m1"].latencies.extend([10000] * 3)  # 4 slots × 15 s ÷ 10 s = 6 chits, and it drives 8
    [line] = sizing.hint_lines(rt)
    assert line.startswith("M1 keeps up with about 6 chits, but it drives 8: most moves will be instinct.")
    assert 'start a new game with 6 chits per world (New game, then "Use 6 chits")' in line
    rt.mind.brains["m1"].latencies.clear()
    rt.mind.brains["m1"].latencies.extend([2000] * 3)
    assert sizing.hint_lines(rt) == ["M1 keeps up with about 30 chits. It drives 8."]
    assert len(rt.worlds["A"].agents) == 8  # (a hint, nothing more)


def test_the_little_chits_command_prints_the_hint_on_its_first_run(env, fake, monkeypatch, capsys):
    import uvicorn
    from fastapi.testclient import TestClient

    from chits import cli
    from chits.app import R, app

    url, _ = fake
    started = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: started.append(a))
    for key in ("CHITS_FIRST_RUN_HINT", "CHITS_MODEL_URL", "CHITS_MODE"):
        monkeypatch.setenv(key, "")  # (the command sets these for its server: put back after the test)
    assert cli.main(["--no-browser", "--no-scan", "--data", str(env), "--model", url, "--mode", "single"]) == 0
    assert started and os.environ["CHITS_FIRST_RUN_HINT"] == "1"
    with TestClient(app) as c:
        for _ in range(200):
            if c.get("/api/brains").json()["brains"][0]["capacity"]["source"]:
                break
            time.sleep(0.05)
        time.sleep(0.1)
        out = capsys.readouterr().out
        assert "keeps up with about" in out and "It drives 8." in out, out
        assert len(R().worlds["A"].agents) == 8


def test_no_hint_and_no_probe_without_the_command(env, fake, monkeypatch, capsys):
    from fastapi.testclient import TestClient

    from chits.app import app

    url, state = fake
    monkeypatch.setenv("CHITS_MODEL_URL", url)
    before = state["calls"]
    with TestClient(app) as c:
        time.sleep(0.3)
        assert c.get("/api/brains").json()["brains"][0]["capacity"]["source"] is None
    assert state["calls"] == before and "keeps up" not in capsys.readouterr().out
