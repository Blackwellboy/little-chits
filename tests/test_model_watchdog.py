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


def _said(w):
    return [e.text for e in w.events if e.kind == "mind"]


async def test_a_model_that_stops_answering_is_told_once_and_again_when_it_answers(tmp_path):
    mind = Mind(tmp_path / "brains.json")
    b = mind.upsert({"id": "env", "label": "env", "base_url": f"http://127.0.0.1:{_free_port()}/v1", "timeout": 1})
    w = World("A", "A", 22, "direct", 96, 6)
    mind.assign(w, "env")
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
    assert mind.down_state("A") == {"down": False, "failing_since": None}
    await mind.close()


def test_a_short_outage_a_switched_off_brain_or_another_brain_is_not_news(tmp_path):
    mind = Mind(tmp_path / "brains.json")
    b = mind.upsert({"id": "m", "label": "m", "base_url": "http://127.0.0.1:9/v1"})
    mind.upsert({"id": "n", "label": "n", "base_url": "http://127.0.0.1:9/v1"})
    w = World("A", "A", 3, "direct", 64, 3)
    mind.assign(w, "m")

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
