"""A model server that dies under a queue. The brain backs off after 3 failures in a row, but requests already
queued for a slot still went out one by one into the same hang: live, with the 3090's server gone, 111 queued
requests each waited their turn to time out (90 s each) while their chits sat on instinct."""

import asyncio

import httpx
import pytest

from chits.brain.llm import BrainConfig, LLMBrain, ModelCoolingDown


def test_queued_requests_are_given_up_once_the_server_is_known_to_be_down():
    sent = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(1)
        await asyncio.sleep(0.01)
        raise httpx.ReadTimeout("dead server", request=request)

    async def go():
        b = LLMBrain(BrainConfig(id="t", base_url="http://model.test/v1", model="m", max_concurrency=1))
        b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        msg = [{"role": "user", "content": "hi"}]
        calls = [asyncio.create_task(b.chat(msg, max_tokens=50)) for _ in range(10)]
        res = await asyncio.gather(*calls, return_exceptions=True)
        await b.close()
        return b, res

    b, res = asyncio.run(go())
    assert len(sent) == 3  # three real failures start the back-off...
    assert sum(isinstance(r, ModelCoolingDown) for r in res) == 7  # ...and the other seven are not sent at all
    assert b.stats.skipped == 7 and b.stats.failed == 3


def test_the_test_button_asks_a_switched_off_or_cooling_brain():
    # the health gate kept the Test button from ever reaching the server of a brain that was off or backing off,
    # which is when you want to know whether it's back (Codex, #28)
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true, "word": "chit"}'},
                                                       "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 9, "completion_tokens": 9}})

    async def go(off: bool):
        b = LLMBrain(BrainConfig(id="t", base_url="http://model.test/v1", model="m", enabled=not off))
        b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        if not off:
            b.cooldown_until = time.monotonic() + 60
        res = await b.test()
        with pytest.raises(ModelCoolingDown, match="switched off" if off else "cooling down"):
            await b.chat([{"role": "user", "content": "hi"}], max_tokens=5)  # (play still waits)
        await b.close()
        return res

    for off in (True, False):
        res = asyncio.run(go(off))
        assert res["ok"], res
