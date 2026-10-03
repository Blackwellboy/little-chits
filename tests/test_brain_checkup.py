"""A Brains "Test" that explains itself (brain/checkup.py).

The Test said reachable or not. Now it asks one real, tiny decision (a plan through the normal prompt and parser, and
a one-token choice with logprobs, as the cascade does) and says what came back, and for each thing that went wrong a
plain cause and, where there is one, a one-click fix. A brain added without settings starts with the plainest request
and its first Test finds what its server takes.

The classifier is tested on fabricated observations and fabricated server replies; the whole path against the fake
model server.
"""

import asyncio
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from chits.brain import checkup as C
from chits.brain.llm import BrainConfig

PLAN = '{"thought": "Food first.", "goal": "eat", "plan": [{"do": "gather", "what": "berries", "qty": 3}, {"do": "eat"}]}'


def _chat(content, finish="stop", logprobs=None, **message):
    choice = {"index": 0, "message": {"role": "assistant", "content": content, **message}, "finish_reason": finish}
    if logprobs is not None:
        choice["logprobs"] = {"content": [{"token": "A", "logprob": -0.1, "top_logprobs": [
            {"token": k, "logprob": v} for k, v in logprobs.items()]}]}
    return {"choices": [choice], "usage": {"prompt_tokens": 50, "completion_tokens": 9}}


def _server(plan=None, choice=None, models=None, seen=None):
    """A fabricated model server: `plan(body)` and `choice(body)` return a reply (a dict, or an httpx.Response)."""
    plan = plan or (lambda body: _chat(PLAN))
    choice = choice or (lambda body: _chat("A", "length", {"A": -0.1, "B": -2.6}))

    def handle(request):
        if request.url.path.endswith("/models"):
            return models() if models else httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        out = (choice if body.get("max_tokens") == 1 else plan)(body)
        return out if isinstance(out, httpx.Response) else httpx.Response(200, json=out)

    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle))


def _test(server, **cfg):
    cfg.setdefault("json_mode", True)
    cfg.setdefault("disable_thinking", True)
    return asyncio.run(C.diagnose(BrainConfig(id="t", base_url="http://model.test/v1", model="m", timeout=7, **cfg), server()))


def _finding(r, code):
    return next((f for f in r["findings"] if f["code"] == code), None)


def test_a_healthy_brain_shows_its_reply_its_plan_its_choice_and_how_long_it_took():
    seen = []
    r = _test(_server(seen=seen))
    assert r["ok"] and r["findings"] == [] and r["error"] == ""
    assert r["reply"] == PLAN[:200] and r["parsed"] and r["plan"] == {"goal": "eat", "steps": ["gather", "eat"]}
    assert r["logprobs"] is True and r["choice"] == "A"
    assert r["latency_ms"] is not None and r["choice_latency_ms"] is not None and r["model"] == "m"
    # what was asked is what the game asks: the scene with its JSON instruction, then one token with logprobs
    assert len(seen) == 2 and "Reply with the JSON object only" in seen[0]["messages"][-1]["content"]
    assert seen[1]["max_tokens"] == 1 and seen[1]["logprobs"] is True and "YOUR OPTIONS" in seen[1]["messages"][-1]["content"]
    long = _test(_server(plan=lambda b: _chat(PLAN + " " * 50 + "x" * 400)))
    assert len(long["reply"]) == 200


def test_json_mode_refused_offers_to_turn_it_off():
    def lm_studio(body):
        if "response_format" in body:
            return httpx.Response(422, json={"error": {"message": "'response_format.type' must be 'json_schema' or 'text'"}})
        return _chat(PLAN)

    r = _test(_server(plan=lm_studio))
    f = _finding(r, "json_refused")
    assert r["ok"] and r["parsed"]  # (the request is retried without it: the brain works, at a refusal's cost)
    assert f["level"] == "warn" and f["text"].startswith("The server refused JSON mode.")
    assert f["fix"] == {"label": "Turn JSON mode off", "patch": {"json_mode": False}}
    assert _finding(_test(_server(plan=lm_studio), json_mode=False), "json_refused") is None

    # a refusal the client does not retry (not a 400 or 422) fails the Test, with the server's own words
    def hard(body):
        if "response_format" in body:
            return httpx.Response(500, json={"error": {"message": "response_format is not implemented"}})
        return _chat(PLAN)

    r = _test(_server(plan=hard, choice=lambda b: _chat("A", "length", {"A": -0.1})))
    f = _finding(r, "json_refused")
    assert not r["ok"] and f["level"] == "fail" and "HTTP 500: response_format is not implemented" in f["text"]
    assert f["fix"]["patch"] == {"json_mode": False}


def test_a_reply_spent_on_thinking_offers_to_disable_thinking():
    cut = _server(plan=lambda b: _chat("", "length", reasoning_content="Let me think about berries"),
                  choice=lambda b: _chat("", "length", reasoning_content="Hm"))
    r = _test(cut, disable_thinking=False)
    f = _finding(r, "thinking")
    assert not r["ok"] and not r["parsed"] and f["level"] == "fail"
    assert f["text"] == "The model spent its reply thinking and never gave an answer."
    assert f["fix"] == {"label": "Disable thinking", "patch": {"disable_thinking": True}}
    # empty, with reasoning tokens counted in the usage only
    def counted(body):
        out = _chat("", "length")
        out["usage"]["completion_tokens_details"] = {"reasoning_tokens": 600}
        return out
    assert _finding(_test(_server(plan=counted), disable_thinking=False), "thinking")["fix"]["patch"] == {"disable_thinking": True}
    # already asked not to think, and it thinks anyway: room for the answer is the fix left
    f = _finding(_test(cut, disable_thinking=True, max_tokens=600), "thinking")
    assert "thinks even when asked not to" in f["text"] and f["fix"] == {"label": "Raise max tokens to 1200", "patch": {"max_tokens": 1200}}
    # thinking, then a good plan: it works, slowly
    r = _test(_server(plan=lambda b: _chat("<think>berries, probably</think>\n" + PLAN)), disable_thinking=False)
    f = _finding(r, "thinking")
    assert r["ok"] and r["parsed"] and f["level"] == "warn" and f["fix"]["patch"] == {"disable_thinking": True}
    # an empty reply with no thinking is said as it is
    assert _finding(_test(_server(plan=lambda b: _chat(""))), "empty")["text"] == "The model sent an empty reply."


def test_a_valid_letter_without_logprobs_still_decides_and_is_only_noted():
    # the mind falls back to the reply's letter when no logprobs come (mind._choose): the Test must not fail what
    # the game can use, nor send the user to the slower full prompt (Codex review)
    bare = _server(choice=lambda b: _chat("B", "length"))
    for style in ("cascade", "choose", "full"):
        r = _test(bare, prompt_style=style)
        f = _finding(r, "no_logprobs")
        assert r["ok"] and r["logprobs"] is False and r["choice"] == "B", style
        assert f["level"] == "note" and f["fix"] is None and _finding(r, "no_letter") is None
    assert "cannot tell when the model is unsure" in _finding(_test(bare, prompt_style="cascade"), "no_logprobs")["text"]
    # a server that refuses the logprobs field outright is the same case (the client drops it and asks again)
    def refuses(body):
        if "logprobs" in body:
            return httpx.Response(400, json={"error": "logprobs are not supported by this model"})
        return _chat("A", "length")
    r = _test(_server(choice=refuses), prompt_style="cascade")
    assert r["ok"] and r["choice"] == "A" and _finding(r, "no_logprobs")["level"] == "note"


def test_neither_logprobs_nor_a_letter_fails_a_choosing_brain_and_offers_the_full_prompt_style():
    wordy = _server(choice=lambda b: _chat("The", "length"))
    for style in ("cascade", "choose"):
        r = _test(wordy, prompt_style=style)
        f = _finding(r, "no_letter")
        assert not r["ok"] and r["choice"] == "" and f["level"] == "fail" and "no logprobs either" in f["text"]
        assert f["fix"] == {"label": "Switch prompt style to full", "patch": {"prompt_style": "full"}}
    r = _test(wordy, prompt_style="full")  # a brain that writes full plans is told, and not failed
    assert r["ok"] and _finding(r, "no_letter")["level"] == "note" and _finding(r, "no_letter")["fix"] is None


def test_a_timeout_says_how_long_and_what_to_change():
    seen = []

    def slow(body):
        raise httpx.ReadTimeout("timed out")

    r = _test(_server(plan=slow, seen=seen))
    f = _finding(r, "timeout")
    assert not r["ok"] and r["reply"] is None and f["fix"] is None
    assert f["text"] == ("No reply within 7 seconds. The model is too slow or too busy: use fewer chits, or give the "
                         "server more parallel slots.")
    assert len(seen) == 1  # (the choice is not asked: it would only wait as long again)


def test_http_errors_say_what_the_server_said():
    r = _test(_server(models=lambda: httpx.Response(401, json={"error": {"message": "invalid api key"}})))
    assert not r["ok"] and "HTTP 401: invalid api key" in _finding(r, "http")["text"] and "mozilla" not in r["error"].lower()
    r = _test(_server(plan=lambda b: httpx.Response(500, json={"error": {"message": "model crashed while loading"}}),
                      choice=lambda b: httpx.Response(500, json={"error": {"message": "model crashed while loading"}})),
              json_mode=False)
    assert [f["code"] for f in r["findings"]] == ["http"] and "HTTP 500: model crashed while loading" in r["error"]

    def down():
        raise httpx.ConnectError("All connection attempts failed")
    r = _test(_server(models=down))
    assert _finding(r, "unreachable")["text"].startswith("Nothing answered at http://model.test/v1.")


def test_a_reply_that_is_not_a_plan_says_so():
    r = _test(_server(plan=lambda b: _chat("I think I will go and look for some berries, maybe.")))
    f = _finding(r, "unparsed")
    assert not r["ok"] and not r["parsed"] and r["reply"].startswith("I think I will")
    assert f["text"].startswith("The reply was not a plan the game could read") and f["fix"]["patch"] == {"prompt_style": "compact"}
    r = _test(_server(choice=lambda b: _chat("The", "length", {"The": -0.2, " I": -1.9})), prompt_style="choose")
    assert _finding(r, "no_letter")["fix"]["patch"] == {"prompt_style": "full"}


def test_the_classifier_reads_fabricated_observations():
    cfg = BrainConfig(id="t", base_url="http://model.test/v1", prompt_style="cascade", json_mode=True, disable_thinking=False)
    good_plan = {"text": PLAN, "answered": True, "thinking": False, "parsed": {"goal": "eat", "steps": ["eat"]}, "latency_ms": 900}
    good_choice = {"text": "A", "answered": True, "thinking": False, "logprobs": True, "letter": "A", "latency_ms": 120}
    assert C.classify({"plan": good_plan, "choice": good_choice}, cfg) == []
    codes = lambda obs: [(f["code"], f["level"]) for f in C.classify(obs, cfg)]
    assert codes({"plan": {**good_plan, "json_refused": True}, "choice": good_choice}) == [("json_refused", "warn")]
    assert codes({"plan": good_plan, "choice": {**good_choice, "logprobs": False}}) == [("no_logprobs", "note")]
    assert codes({"plan": good_plan, "choice": {**good_choice, "logprobs": False, "letter": ""}}) == [("no_letter", "fail")]
    assert codes({"plan": {"text": "", "answered": False, "thinking": True, "finish_reason": "length"},
                  "choice": {"text": "", "answered": False, "thinking": True, "logprobs": False, "letter": ""}}) \
        == [("thinking", "fail"), ("no_letter", "fail")]
    assert codes({"timeout": 30, "plan": {"error": {"kind": "timeout", "text": "ReadTimeout"}}}) == [("timeout", "fail")]
    assert "within 30 seconds" in C.classify({"timeout": 30, "plan": {"error": {"kind": "timeout", "text": "ReadTimeout"}}}, cfg)[0]["text"]
    assert codes({"error": {"kind": "http", "text": "HTTP 404: model not found"}}) == [("http", "fail")]
    assert codes({"plan": good_plan, "choice": {"error": {"kind": "http", "text": "HTTP 400: max_tokens must be at least 16"}}}) \
        == [("http", "fail")]
    # every fix is a patch of brain settings
    for f in C.classify({"plan": {"text": "", "answered": False, "thinking": True}, "choice": {**good_choice, "letter": ""}}, cfg):
        assert set(f["fix"]["patch"]) <= set(BrainConfig.__dataclass_fields__) and f["fix"]["label"]


def test_a_brain_config_made_in_code_is_what_it_was():
    # (the Lab and the experiment tools build BrainConfigs: nothing they compare or send has changed)
    from chits.lab.spec import FAIR_MODEL_FIELDS

    c = BrainConfig(id="x")
    assert c.json_mode is True and c.disable_thinking is True and c.detect is False
    assert "detect" not in FAIR_MODEL_FIELDS and {"json_mode", "disable_thinking", "prompt_style"} <= set(FAIR_MODEL_FIELDS)


# ------------------------------------------------------------------ against the fake model server
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def fake():
    import uvicorn
    import fake_llm as F

    old = dict(F.STATE)
    F.STATE.update(latency=0.02, garbage_rate=0.0, tidy=True, letters=True)
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
def game(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    from fastapi.testclient import TestClient

    from chits.app import R, app

    with TestClient(app) as c:
        yield c, R()


def _cfg(c, bid):
    return next(b["config"] for b in c.get("/api/brains").json()["brains"] if b["config"]["id"] == bid)


def test_a_new_brain_starts_plain_and_its_first_test_finds_what_the_server_takes(game, fake):
    c, rt = game
    url, state = fake
    made = c.post("/api/brains", json={"id": "m1", "base_url": url}).json()["brain"]
    assert (made["json_mode"], made["disable_thinking"], made["detect"]) == (False, False, True)
    r = c.post("/api/brains/m1/test").json()
    assert r["ok"] and r["parsed"] and r["plan"]["steps"] and r["logprobs"] is True and r["choice"] == "A"
    assert r["reply"].startswith("{") and r["latency_ms"] >= 0 and r["findings"] == []
    assert r["detected"] == {"json_mode": True, "disable_thinking": True}
    cfg = _cfg(c, "m1")
    assert (cfg["json_mode"], cfg["disable_thinking"], cfg["detect"]) == (True, True, False)
    assert json.loads((rt.data_dir / "brains.json").read_text())["brains"][0]["detect"] is False  # (saved)
    assert c.post("/api/brains/m1/test").json()["detected"] is None  # found once
    assert rt.mind.brains["m1"].stats.requests == 0  # (the Test asks on a client of its own)

    # a server that refuses JSON mode: the brain ends up without it, and nothing is left to fix
    state["refuse_json"] = True
    c.post("/api/brains", json={"id": "m2", "base_url": url})
    r = c.post("/api/brains/m2/test").json()
    assert r["ok"] and r["detected"] == {"json_mode": False, "disable_thinking": True} and r["findings"] == []
    assert _cfg(c, "m2")["json_mode"] is False
    state["refuse_switch"] = True
    c.post("/api/brains", json={"id": "m3", "base_url": url})
    assert c.post("/api/brains/m3/test").json()["detected"] == {"json_mode": False, "disable_thinking": False}

    # settings given by hand are kept, and not detected over
    made = c.post("/api/brains", json={"id": "m4", "base_url": url, "json_mode": True}).json()["brain"]
    assert (made["json_mode"], made["disable_thinking"], made["detect"]) == (True, False, False)
    r = c.post("/api/brains/m4/test").json()
    assert r["detected"] is None and _cfg(c, "m4")["json_mode"] is True
    assert [f["code"] for f in r["findings"]] == ["json_refused"]


def test_a_server_that_was_down_leaves_the_brain_to_be_detected_later(game, fake):
    c, rt = game
    c.post("/api/brains", json={"id": "gone", "base_url": f"http://127.0.0.1:{_free_port()}/v1", "timeout": 2})
    r = c.post("/api/brains/gone/test").json()
    assert not r["ok"] and r["detected"] is None and r["findings"][0]["code"] == "unreachable"
    assert _cfg(c, "gone")["detect"] is True


def test_each_fix_is_one_click_and_the_next_test_passes(game, fake):
    c, rt = game
    url, state = fake
    fix = lambda bid, f: c.post("/api/brains", json={"id": bid, "base_url": url, **f["fix"]["patch"]})

    state["thinks"] = True  # a reasoning model, and a brain that does not ask it to skip thinking
    c.post("/api/brains", json={"id": "r1", "base_url": url, "json_mode": False, "disable_thinking": False})
    r = c.post("/api/brains/r1/test").json()
    f = _finding(r, "thinking")
    assert not r["ok"] and f["fix"]["label"] == "Disable thinking"
    assert fix("r1", f).status_code == 200
    r = c.post("/api/brains/r1/test").json()
    assert r["ok"] and r["parsed"] and _finding(r, "thinking") is None
    state["thinks"] = False

    state["logprobs"] = False  # a server with no logprobs: a cascade brain still decides by the letter it replies
    c.post("/api/brains", json={"id": "c1", "base_url": url, "json_mode": False, "disable_thinking": False, "prompt_style": "cascade"})
    r = c.post("/api/brains/c1/test").json()
    assert r["ok"] and r["logprobs"] is False and r["choice"] == "A" and _finding(r, "no_logprobs")["level"] == "note"
    state["letters"] = False  # and one that answers a one-token choice with no letter at all
    r = c.post("/api/brains/c1/test").json()
    f = _finding(r, "no_letter")
    assert not r["ok"] and f["fix"]["label"] == "Switch prompt style to full"
    assert fix("c1", f).status_code == 200 and _cfg(c, "c1")["prompt_style"] == "full"
    r = c.post("/api/brains/c1/test").json()
    assert r["ok"] and _finding(r, "no_letter")["level"] == "note"
    state["logprobs"] = state["letters"] = True

    state["refuse_json"] = True
    c.post("/api/brains", json={"id": "j1", "base_url": url, "json_mode": True, "disable_thinking": False})
    f = _finding(c.post("/api/brains/j1/test").json(), "json_refused")
    assert fix("j1", f).status_code == 200
    assert c.post("/api/brains/j1/test").json()["findings"] == []


def test_a_test_never_changes_a_brain_an_experiment_is_using(game, fake):
    c, rt = game
    url, state = fake
    c.post("/api/brains", json={"id": "m1", "base_url": url})
    c.post("/api/worlds/A/brain", json={"brain": "m1"})
    rt.contract, rt.mind.strict = "experiment", True
    before = dict(_cfg(c, "m1"))
    r = c.post("/api/brains/m1/test").json()
    assert r["ok"] and r["detected"] is None and _cfg(c, "m1") == before and before["detect"] is True
    assert c.post("/api/brains", json={"id": "m1", "base_url": url, "json_mode": True}).status_code == 409  # (a fix too)
    # a brain no world of the experiment uses is free
    c.post("/api/brains", json={"id": "spare", "base_url": url})
    assert c.post("/api/brains/spare/test").json()["detected"] == {"json_mode": True, "disable_thinking": True}


async def test_a_model_found_on_the_first_run_is_settled_by_the_first_run_hint(fake, tmp_path, monkeypatch):
    from chits import sizing
    from chits.runtime import Runtime

    url, state = fake
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SCAN_PORTS", url.rsplit(":", 1)[1].split("/")[0])
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    state["refuse_json"] = True
    rt = Runtime()
    [added] = await rt.autodetect()
    b = rt.mind.brains[added["id"]]
    assert b.cfg.detect and b.cfg.json_mode  # found, not yet tested: the old defaults, with the client's fallbacks
    said = []
    await sizing.first_run_hint(rt, said.append)
    b = rt.mind.brains[added["id"]]
    assert not b.cfg.detect and b.cfg.json_mode is False and b.cfg.disable_thinking is True
    assert len(said) == 1 and "keeps up with about" in said[0]
    await rt.mind.close()
