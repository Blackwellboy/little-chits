"""Model-server errors, reported by a tester running the game against LM Studio (issues #61-#65):

- #61: a server that refuses JSON mode (LM Studio answers 422: json_schema or text only) got every request refused,
  because the fallback only knew 400 and only tried once. Each refused optional feature is now dropped in turn.
- #65 (and #61): an error read "Client error '422 ...' For more information check: <a page about status codes>":
  the server's own message was lost. Errors now say what the server said.
- #62: an old error stayed on a brain's card forever. It clears after a run of good replies, and says when it happened.
- #64: a save left in experiment mode refused every brain swap with no way back. It can now be ended into play.
"""

import asyncio
import os

import httpx
import pytest

from chits.brain import llm as L
from chits.brain.llm import BrainConfig, LLMBrain

OK = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 5, "completion_tokens": 3}}


def _brain(handler, **cfg):
    b = LLMBrain(BrainConfig(id="t", base_url="http://model.test/v1", model="m", **cfg))
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    b.cooldown = False
    return b


def _run(b, n=1, **kw):
    async def go():
        out = []
        for _ in range(n):
            try:
                out.append(await b.chat([{"role": "user", "content": "hi"}], max_tokens=20, **kw))
            except Exception as e:  # (recorded in the stats)
                out.append(e)
        await b.close()
        return out
    return asyncio.run(go())


def test_a_server_that_refuses_json_mode_with_422_still_gets_answered():
    sent = []

    def lm_studio(request):
        body = __import__("json").loads(request.content)
        sent.append(sorted(body))
        if body.get("response_format", {}).get("type") == "json_object":
            return httpx.Response(422, json={"error": {"message": "'response_format.type' must be 'json_schema' or 'text'"}})
        return httpx.Response(200, json=OK)

    b = _brain(lm_studio)
    [res] = _run(b)
    assert res["text"] == '{"ok": true}' and not b._json_ok and b.stats.ok_streak == 1 and b.stats.failed == 0
    assert "response_format" in sent[0] and "response_format" not in sent[1]


def test_each_refused_feature_is_dropped_in_turn():
    # JSON mode refused, then logprobs: one retry used to leave the second refusal standing
    def picky(request):
        body = __import__("json").loads(request.content)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format is not supported"})
        if "logprobs" in body:
            return httpx.Response(400, json={"error": "logprobs are not supported by this model"})
        return httpx.Response(200, json=OK)

    b = _brain(picky)
    [res] = _run(b, extra={"logprobs": True, "top_logprobs": 5})
    assert not isinstance(res, Exception) and not b._json_ok and not b._logprobs_ok


def test_an_error_says_what_the_server_said_and_clears_once_the_brain_is_well_again():
    state = {"down": True}

    def flaky(request):
        if state["down"]:
            return httpx.Response(500, json={"error": {"message": "model crashed while loading"}})
        return httpx.Response(200, json=OK)

    b = _brain(flaky)
    _run(b)
    assert b.stats.last_error == "HTTP 500: model crashed while loading" and b.stats.last_error_at > 0
    assert "mozilla" not in b.stats.last_error.lower()
    state["down"] = False
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(flaky))
    _run(b, L.RECOVERED_AFTER - 1)
    assert b.stats.last_error  # (a few good replies: still news)
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(flaky))
    _run(b)
    assert b.stats.last_error == "" and b.stats.failed == 1  # (history now; the count stays a count)


def test_the_test_button_reports_the_servers_own_words():
    def no_models(request):
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    b = _brain(no_models)

    async def go():
        r = await b.test()
        await b.close()
        return r
    r = asyncio.run(go())
    assert not r["ok"] and "HTTP 401: invalid api key" in r["error"] and "mozilla" not in r["error"].lower()


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


def test_an_experiment_can_be_ended_into_play_and_brains_swapped_again(env):
    from fastapi.testclient import TestClient

    from chits.app import R, app

    with TestClient(app) as c:
        rt = R()
        c.post("/api/brains", json={"id": "m1", "base_url": "http://127.0.0.1:9/v1"})
        assert c.post("/api/experiment/end").status_code == 409  # (not an experiment)
        rt.contract, rt.mind.strict, rt.pace_to_brain = "experiment", True, True
        rt.store.set_meta("contract", "experiment")
        assert c.post("/api/worlds/A/brain", json={"brain": "m1"}).status_code == 409
        ctl = c.post("/api/experiment/end").json()
        assert ctl["contract"] == "play" and not rt.mind.strict and rt.store.get_meta("contract") == "play"
        assert any(e.kind == "contract" for e in rt.worlds["A"].events)
        assert c.post("/api/worlds/A/brain", json={"brain": "m1"}).status_code == 200
