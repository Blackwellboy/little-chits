"""A world's model that stops answering is said to be down, in the world's own events and the brain status the UI
shows (Mind.watch). Live, World A's model stopped at day 806 ("cooling down" re-armed forever) and its chits ran
~1,100 days on instinct with nobody told."""

import asyncio
import socket

from chits.brain import mind as M
from chits.brain.mind import Mind
from chits.runtime import Runtime
from chits.sim.world import World


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Clock:
    """The watch's wall clock, by hand: `step` seconds pass each time it is read (one read per failing tick)."""

    def __init__(self, step=1.0):
        self.t, self.step = 1000.0, step

    def __call__(self):
        self.t += self.step
        return self.t


def _said(w):
    return [e.text for e in w.events if e.kind == "mind"]


async def test_a_model_that_stops_answering_is_told_once_and_again_when_it_answers(tmp_path):
    mind = Mind(tmp_path / "brains.json")
    b = mind.upsert({"id": "env", "label": "env", "base_url": f"http://127.0.0.1:{_free_port()}/v1", "timeout": 1})
    w = World("A", "A", 22, "direct", 96, 6)
    mind.assign(w, "env")
    mind.clock = Clock()  # (a second a tick: a day of failing is minutes of it)
    for _ in range(M.DOWN_AFTER_TICKS + 40):
        w.step(mind.hook)
        mind.watch(w)
        await asyncio.sleep(0.002)
    assert b.stats.failed > 0 and b.stats.ok == 0
    assert _said(w) == ["World A's mind env has stopped answering; the chits are running on instinct"]  # once
    st = mind.down_state("A")
    assert st["down"] and st["failing_since"] is not None and w.tick - st["failing_since"] >= M.DOWN_AFTER_TICKS
    b.stats.consecutive_fail = 0  # (what a reply does: llm.py)
    w.step(mind.hook)
    mind.watch(w)
    assert _said(w)[1:] == ["World A's mind env is answering again"]
    assert mind.down_state("A") == {"down": False, "failing_since": None, "chits_wait": False}
    await mind.close()


def test_a_short_outage_a_switched_off_brain_or_another_brain_is_not_news(tmp_path):
    mind = Mind(tmp_path / "brains.json")
    b = mind.upsert({"id": "m", "label": "m", "base_url": "http://127.0.0.1:9/v1"})
    mind.upsert({"id": "n", "label": "n", "base_url": "http://127.0.0.1:9/v1"})
    w = World("A", "A", 3, "direct", 64, 3)
    mind.assign(w, "m")
    mind.clock = Clock()

    def run(ticks):
        for _ in range(ticks):
            w.tick += 1
            mind.watch(w)

    b.stats.consecutive_fail = 3
    run(M.DOWN_AFTER_TICKS - 5)
    b.stats.consecutive_fail = 0  # it answered before a day was out
    run(10)
    assert _said(w) == [] and not mind.down_state("A")["down"]
    b.stats.consecutive_fail = 3
    b.cfg.enabled = False  # switched off by the player: the chits are on instinct by choice
    run(M.DOWN_AFTER_TICKS + 5)
    assert _said(w) == [] and not mind.down_state("A")["down"]
    b.cfg.enabled = True
    run(M.DOWN_AFTER_TICKS + 5)
    assert len(_said(w)) == 1 and mind.down_state("A")["down"]
    mind.assign(w, "n")  # the player picked another brain: the old one's outage ends without "answering again"
    run(3)
    assert len(_said(w)) == 1 and not mind.down_state("A")["down"]


def test_the_brain_status_says_a_world_is_on_instinct_because_its_model_is_down(tmp_path):
    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    b = rt.mind.upsert({"id": "env", "label": "env", "base_url": "http://127.0.0.1:9/v1"})
    rt.mind.assign(w, "env")
    rt.mind.clock = Clock()
    assert rt.brain_summary()[w.id]["down"] is False
    b.stats.consecutive_fail = 5
    for _ in range(M.DOWN_AFTER_TICKS + 1):
        w.tick += 1
        rt.mind.watch(w)
    s = rt.brain_summary()[w.id]
    assert s["down"] is True and s["failing_since"] is not None and s["label"] == "env"
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_the_runtime_watches_every_world_as_it_steps(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    seen = []
    monkeypatch.setattr(rt.mind, "watch", lambda w: seen.append(w.id))
    rt.step_worlds(2)
    assert sorted(seen) == sorted(list(rt.worlds) * 2)
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_a_hiccup_at_high_speed_is_not_news(tmp_path):
    """At 100x a game day is 0.6 s: one timeout, then a slow good reply, said "stopped answering" and "answering
    again". Down takes a game day AND DOWN_AFTER_S of wall time AND DOWN_AFTER_FAILS failed requests in a row."""
    mind = Mind(tmp_path / "brains.json")
    b = mind.upsert({"id": "m", "label": "m", "base_url": "http://127.0.0.1:9/v1"})
    w = World("A", "A", 3, "direct", 64, 3)
    mind.assign(w, "m")

    def outage(ticks, seconds, fails):
        mind.clock = Clock(seconds / ticks)
        b.stats.consecutive_fail = fails
        for _ in range(ticks):
            w.tick += 1
            mind.watch(w)
        down = mind.down_state("A")["down"]
        b.stats.consecutive_fail = 0  # (it answered)
        w.tick += 1
        mind.watch(w)
        return down

    day = M.DOWN_AFTER_TICKS + 10
    assert not outage(day, 0.6, 1)  # one timeout, at 100x
    assert not outage(day, 0.6, 5)  # five, but over less than a second
    assert not outage(day, 2 * M.DOWN_AFTER_S, M.DOWN_AFTER_FAILS - 1)  # long enough, but too few requests failed
    assert not outage(M.DOWN_AFTER_TICKS // 2, 2 * M.DOWN_AFTER_S, 9)  # long and many, but under a game day
    assert _said(w) == []
    assert outage(day, 2 * M.DOWN_AFTER_S, M.DOWN_AFTER_FAILS)  # all three: down
    assert _said(w) == ["World A's mind m has stopped answering; the chits are running on instinct",
                        "World A's mind m is answering again"]


def test_a_loaded_save_starts_the_watch_again(tmp_path):
    """A save from later in the game, loaded while the model was failing, kept the old world's failing_since: its
    model was "down" from its first tick (review of #170). Another world or timeline starts a new watch."""
    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    b = rt.mind.upsert({"id": "env", "label": "env", "base_url": "http://127.0.0.1:9/v1"})
    rt.mind.assign(w, "env")
    rt.mind.clock = Clock()
    w.tick = 5000
    sid = rt.save_point("later")["id"]  # (as if the save came from later in the game than where the world is now)
    w.tick = 10
    b.stats.consecutive_fail = 5
    for _ in range(M.DOWN_AFTER_TICKS + 1):
        w.tick += 1
        rt.mind.watch(w)
    assert rt.mind.down_state(w.id)["down"]
    assert rt.restore_point(sid)
    w2 = rt.worlds[w.id]
    assert w2.tick >= 5000
    rt.mind.watch(w2)
    assert rt.mind.down_state(w.id) == {"down": False, "failing_since": w2.tick, "chits_wait": False}  # still failing, but only from now
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_where_no_instinct_stands_in_the_status_says_the_chits_wait(tmp_path):
    """Model-led, model-only and experiment runs never put a model's chits on instinct: they wait for it. The event
    said so already; the status the UI words its pill and chip from says so too."""
    mind = Mind(tmp_path / "brains.json")
    b = mind.upsert({"id": "m", "label": "m", "base_url": "http://127.0.0.1:9/v1"})
    w = World("A", "A", 3, "direct", 64, 3)
    mind.assign(w, "m")
    mind.clock = Clock()
    mind.model_led = True
    b.stats.consecutive_fail = 5
    for _ in range(M.DOWN_AFTER_TICKS + 1):
        w.tick += 1
        mind.watch(w)
    assert _said(w) == ["World A's mind m has stopped answering; the chits wait for it"]
    assert mind.down_state("A")["down"] and mind.down_state("A")["chits_wait"] is True
    mind.model_led = False
    assert mind.down_state("A")["chits_wait"] is False
