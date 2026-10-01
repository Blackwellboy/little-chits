"""Issue #3: a one-token decision (a chief's choice, a cascade pick) waits ahead of full plans and reflections. On a
live run 14 of 18 chief answers arrived after the question had expired, stuck behind ~105 queued plan requests."""

import asyncio
import json

import httpx

from chits.brain.llm import DECISION, PLAN, BrainConfig, LLMBrain, PriorityGate


def test_the_gate_serves_decisions_first_then_in_arrival_order():
    async def go():
        gate, order = PriorityGate(1), []
        await gate.acquire(PLAN)  # the one slot is busy

        async def wait(name, pr):
            await gate.acquire(pr)
            order.append(name)
            gate.release()

        tasks = [asyncio.create_task(wait(n, p)) for n, p in
                 (("plan1", PLAN), ("plan2", PLAN), ("chief", DECISION), ("pick", DECISION))]
        await asyncio.sleep(0)
        gate.release()
        await asyncio.gather(*tasks)
        return order

    assert asyncio.run(go()) == ["chief", "pick", "plan1", "plan2"]


def test_a_cancelled_waiter_never_strands_a_slot():
    async def go():
        gate = PriorityGate(1)
        await gate.acquire(PLAN)
        gone = asyncio.create_task(gate.acquire(DECISION))
        after = asyncio.create_task(gate.acquire(PLAN))
        await asyncio.sleep(0)
        gone.cancel()
        await asyncio.sleep(0)
        gate.release()
        await asyncio.wait_for(after, 1)  # the slot went to the next live waiter
        gate.release()
        await asyncio.wait_for(gate.acquire(PLAN), 1)  # and is free again afterwards
        return gate.waiting()

    assert asyncio.run(go()) == 0


def test_a_chiefs_one_token_question_overtakes_queued_plans():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["max_tokens"])
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}, "finish_reason": "stop"}],
                                         "usage": {"completion_tokens": 1, "prompt_tokens": 5}})

    async def go():
        b = LLMBrain(BrainConfig(id="t", base_url="http://model.test/v1", model="m", max_concurrency=1))
        b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        msg = [{"role": "user", "content": "hi"}]
        plans = [asyncio.create_task(b.chat(msg, max_tokens=600)) for _ in range(4)]
        await asyncio.sleep(0)
        chief = asyncio.create_task(b.chat(msg, max_tokens=1, json_reply=False))  # sent last
        await asyncio.gather(*plans, chief)
        await b.close()

    asyncio.run(go())
    assert seen[0] == 600 and seen[1] == 1, seen  # (the first plan was already in flight)
