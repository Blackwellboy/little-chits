"""A model far behind. 85 chits asked a model that keeps up with about 16, and the requests queued: 229 behind the
3090's 8 slots, waiting 65 s each, and 311 plans came back stale (the world had moved on). Past three waiting per
slot, a chit that needs a plan takes instinct's at once and asks again next time; the queue serves fresh requests."""

from chits.brain import mind as M
from chits.brain.mind import Mind
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def _setup():
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 90.0
    w.tick = TICKS_PER_DAY + 60
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "max_concurrency": 2})
    m.assign(w, "test")
    b = m.brains["test"]
    asked = []
    m._ask = lambda world, agent, brain: asked.append(agent.id)
    a.plan = []
    return w, a, m, b, asked


def test_a_chit_asks_its_model_while_the_queue_is_short():
    w, a, m, b, asked = _setup()
    b.stats.queued = M.QUEUE_PER_SLOT * 2 - 1
    m.hook(w, a)
    assert asked == [a.id]


def test_past_three_waiting_per_slot_a_chit_takes_instinct_now():
    w, a, m, b, asked = _setup()
    b.stats.queued = M.QUEUE_PER_SLOT * 2
    m.hook(w, a)
    assert asked == [] and a.plan and not a.thinking


def test_plans_shed_for_a_full_queue_dont_count_against_the_models_share(tmp_path):
    # counted with the rest, the live share read 2.1% at the same 47 adopted plans a day as before
    from chits import diag
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    d = diag.of(w)
    d.plans.clear()
    d.plans.update({"model": 40, "filler": 10, "shed": 5000})
    wd = diag.report(rt)["worlds"][w.id]
    assert wd["model_share_pct"] == 80.0
    rt.store.db.close()


import pytest


@pytest.mark.parametrize("style", ["full", "cascade"])
def test_one_tick_cant_overfill_the_queue(style):
    # the brain's own queue count rises only once a request's task first runs, after the whole tick: before the
    # count was taken at the request, every chit in a tick saw the same short queue and all of them asked (Codex, #29)
    import asyncio

    w = World("A", "A", 1, "direct", 64, 30)
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 90.0
        o.plan = []
    w.tick = TICKS_PER_DAY + 60
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "max_concurrency": 2,
              "prompt_style": style})
    m.assign(w, "test")
    gate = asyncio.Event()

    async def chat(messages, **kw):
        await gate.wait()
        raise RuntimeError("no model")

    m.brains["test"].chat = chat

    async def run():
        for o in list(w.agents.values()):
            m.hook(w, o)
        n = m.plans_out["test"]
        gate.set()
        while m._tasks:
            await asyncio.gather(*list(m._tasks), return_exceptions=True)
        await m.close()
        return n

    assert asyncio.run(run()) == (M.QUEUE_PER_SLOT + 1) * 2
    assert m.plans_out["test"] == 0  # each one counted back in when it finished


def test_a_shed_plan_is_counted_once_as_shed():
    # counted as instinct as well as shed, a shed plan still diluted the model's share (Codex, #29)
    from chits import diag

    w, a, m, b, asked = _setup()
    b.stats.queued = M.QUEUE_PER_SLOT * 2
    d = diag.of(w)
    d.plans.clear()
    m.hook(w, a)
    assert asked == [] and a.plan and dict(d.plans) == {"shed": 1}
