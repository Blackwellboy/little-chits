"""Fixes from an outside code review (2026-09-30): the request merge, cut-off reasoning, `make experiment`'s default,
explicit sampling, and which code ran which days."""

import asyncio
import json

import httpx

from chits.brain.llm import BrainConfig, LLMBrain, _merge


def test_a_users_chat_template_kwargs_add_to_ours_instead_of_dropping_enable_thinking():
    body = {"chat_template_kwargs": {"enable_thinking": False}, "temperature": 0.7}
    _merge(body, {"chat_template_kwargs": {"reasoning_effort": "low"}, "top_k": 40})
    assert body == {"chat_template_kwargs": {"enable_thinking": False, "reasoning_effort": "low"}, "temperature": 0.7, "top_k": 40}
    _merge(body, {"chat_template_kwargs": {"enable_thinking": True}})
    assert body["chat_template_kwargs"]["enable_thinking"] is True  # (only when the user says so)


def _brain(reply, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [reply], "usage": {"completion_tokens": 600, "prompt_tokens": 10}})

    b = LLMBrain(BrainConfig(id="t", base_url="http://model.test/v1", model="m",
                             extra_body={"chat_template_kwargs": {"reasoning_effort": "low"}}))
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return b


def test_reasoning_cut_off_at_the_length_limit_is_not_used_as_the_plan():
    plan = '{"steps":[{"do":"rest"}]}'
    seen = []
    cut = _brain({"message": {"content": "", "reasoning_content": "Let me think... " + plan[:10]},
                  "finish_reason": "length"}, seen)
    r = asyncio.run(cut.chat([{"role": "user", "content": "hi"}]))
    assert r["text"] == "" and r["finish_reason"] == "length" and cut.stats.cut_off == 1
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False, "reasoning_effort": "low"}  # sent merged
    whole = _brain({"message": {"content": "", "reasoning_content": plan}, "finish_reason": "stop"}, [])
    assert asyncio.run(whole.chat([{"role": "user", "content": "hi"}]))["text"] == plan  # a finished answer still counts
    one = _brain({"message": {"content": "B"}, "finish_reason": "length"}, [])
    assert asyncio.run(one.chat([{"role": "user", "content": "hi"}], max_tokens=1))["text"] == "B"  # one-token choices


def test_make_experiment_compares_models_on_one_culture_with_the_same_sampling(tmp_path):
    from chits.tools import experiment as E

    seen = {}

    async def fake_run(brains, days, out, **kw):
        seen.update(kw)
        return {}

    orig = E.run_experiment
    E.run_experiment = fake_run
    try:
        E.main(["--a", "instinct", "--b", "instinct", "--days", "0.01", "--out", str(tmp_path / "x")])
    finally:
        E.run_experiment = orig
    assert seen["mode"] == "versus" and seen["sampling"] == E.SAMPLING
    s = asyncio.run(E.run_experiment({"A": None, "B": None}, 0.05, tmp_path / "v", chits=4, mode="versus"))
    assert s["worlds"]["A"]["culture"] == s["worlds"]["B"]["culture"] == "direct"
    man = json.loads((tmp_path / "v" / "manifest.json").read_text())
    assert man["mode"] == "versus" and man["sampling"] == E.SAMPLING  # recorded with the run


def test_each_start_on_new_code_records_the_commit_and_each_worlds_day(tmp_path, monkeypatch):
    import chits.runtime as RT

    monkeypatch.setattr(RT, "_COMMIT", "aaa1111")
    rt = RT.Runtime(tmp_path)
    try:
        first = rt.record_code_stretch()
        assert [s["commit"] for s in first] == ["aaa1111"] and set(first[0]["day"]) == set(rt.worlds)
        assert len(rt.record_code_stretch()) == 1  # the same code: no new stretch
        monkeypatch.setattr(RT, "_COMMIT", "bbb2222")
        for w in rt.worlds.values():
            w.tick += 5 * 240
        again = rt.record_code_stretch()
        assert [s["commit"] for s in again] == ["aaa1111", "bbb2222"] and all(d >= 6 for d in again[1]["day"].values())
        assert rt.manifest()["code_stretches"][-1]["commit"] == "bbb2222"
    finally:
        rt.store.db.close()
        asyncio.run(rt.mind.close())


def test_an_experiment_seeds_each_request_from_its_seed_and_the_prompt():
    from chits.brain.llm import request_seed

    reply = {"message": {"content": '{"plan":[]}'}, "finish_reason": "stop"}
    q1, q2 = [{"role": "user", "content": "one"}], [{"role": "user", "content": "two"}]
    seen = []
    b = _brain(reply, seen)
    asyncio.run(b.chat(q1))
    assert "seed" not in seen[-1]  # play: no seed
    b.seed_base = 7
    for q in (q1, q1, q2):
        asyncio.run(b.chat(q))
    assert seen[1]["seed"] == seen[2]["seed"] == request_seed(7, q1) != seen[3]["seed"]
    assert request_seed(8, q1) != request_seed(7, q1) and 0 <= request_seed(7, q1) < 2**31
    b.cfg.extra_body = {"seed": 99}  # a brain's own fixed seed wins
    asyncio.run(b.chat(q1))
    assert seen[-1]["seed"] == 99



def test_run_experiment_requires_mode_for_new_callers(tmp_path):
    """F7: no implicit culture confound for ordinary Python callers; frozen T15 keeps its narrow legacy shape."""
    import asyncio
    import pytest
    from chits.tools.experiment import run_experiment

    with pytest.raises(TypeError, match="requires mode"):
        asyncio.run(run_experiment({"A": None, "B": None}, 0.01, tmp_path / "missing", chits=2))

    # An explicit mode is always accepted for the same caller shape.
    s = asyncio.run(run_experiment({"A": None, "B": None}, 0.01, tmp_path / "explicit", chits=2, mode="versus"))
    assert s["mode"] == "versus"
