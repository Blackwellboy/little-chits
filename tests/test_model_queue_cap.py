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
