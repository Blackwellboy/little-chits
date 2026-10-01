"""The storyteller: a challenge every few days, the same one for both worlds, announced to the chits."""

from chits.sim import storyteller as S
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def test_the_schedule_is_the_same_for_both_worlds_and_about_every_five_days():
    days = [d for d in range(200) if S.today(1234, d)]
    assert 25 <= len(days) <= 60 and min(days) >= S.FIRST_DAY
    assert S.today(1234, days[0]) == S.today(1234, days[0])


def _world_on(day, season_day=None):
    w = World("A", "A", 1234, "direct", 96, 12)
    for _ in range(200):
        w.step(lambda world, a: None)
    w.tick = day * TICKS_PER_DAY
    return w


def test_a_challenge_is_announced_and_shown_to_chits():
    from chits.brain import prompt as P

    d = next(d for d in range(20, 400) if S.today(1234, d))
    w = _world_on(d)
    kind = S.daily(w)
    assert kind and w.challenge["kind"] == kind
    assert any(e.kind == "storyteller" for e in w.events)
    a = next(iter(w.agents.values()))
    assert "NEWS: " + w.challenge["text"] in P.scene(w, a)
    w.tick += 2 * TICKS_PER_DAY + 1
    S.daily(w)
    assert not w.challenge or w.challenge["day"] != d


def test_each_challenge_does_what_it_says():
    import random
    w = _world_on(30)
    rng = random.Random(1)
    before = sum(a.health for a in w.agents.values())
    assert S.sickness(w, rng) and sum(a.health for a in w.agents.values()) < before
    w.tick = 30 * TICKS_PER_DAY
    txt = S.meteorite(w, rng)
    assert txt and any("meteorite" in p for p in w.ground.values())
    for d in range(30, 50):  # a winter day
        w.tick = d * TICKS_PER_DAY + 60
        if w.season == "winter":
            break
    assert w.season == "winter"
    w.cold_until = w.tick + 10
    cold = w.temperature()
    w.cold_until = -1
    assert cold < w.temperature()


def test_no_storyteller_in_an_experiment(tmp_path):
    import asyncio
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=1234, mode="single", contract="experiment")
    w = rt.worlds["A"]
    for _ in range(240 * 12):
        rt.step_worlds()
    assert not any(e.kind == "storyteller" for e in w.events)
    asyncio.run(rt.mind.close())


def test_a_traveller_teaches_only_what_the_village_can_make():
    import random
    w = _world_on(40)
    for a in w.agents.values():
        a.familiar |= {"charcoal", "pot", "copper"}  # rocket fuel and wire need a factory it doesn't have
    for i in range(20):
        w2 = w
        txt = S.stranger(w2, random.Random(i))
        if txt:
            assert "rocket fuel" not in txt and "wire" not in txt
