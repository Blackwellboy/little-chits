"""F19: the live world cannot outrun durable state after a checkpoint failure."""

import asyncio
import json

import pytest

from chits.runtime import Runtime


def close_without_saving(rt):
    """Simulate a hard process loss: close handles without Runtime.stop(), which intentionally saves."""
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_restart_returns_to_the_last_committed_tick(tmp_path):
    rt = Runtime(tmp_path)
    a = rt.worlds["A"]
    person = next(iter(a.agents.values()))

    # Runtime made tick 0 durable. Establish a later explicit boundary with an identifiable state.
    for _ in range(17):
        rt.step_worlds()
    person.mood = 77.0
    rt.save_all()
    committed = a.tick
    assert committed == a._durable_tick

    # This suffix exists only in memory. A hard process loss must not invent it on restart.
    for _ in range(11):
        rt.step_worlds()
    next(iter(a.agents.values())).mood = 12.0
    assert a.tick > committed
    close_without_saving(rt)

    rt2 = Runtime(tmp_path)
    restored = rt2.worlds["A"]
    assert restored.tick == committed
    assert next(iter(restored.agents.values())).mood == pytest.approx(77.0)
    assert restored._durable_tick == committed
    close_without_saving(rt2)


def test_failed_checkpoint_freezes_play_until_an_explicit_retry(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    w = rt.worlds["A"]
    assert w._durable_tick == 0
    w.tick = 60

    real = rt.store.save_world

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(rt.store, "save_world", boom)
    with pytest.raises(OSError, match="disk full"):
        rt._checkpoint(w)

    assert rt.paused is True
    assert "A" in rt.save_errors and "disk full" in rt.save_errors["A"]
    assert w._durable_tick == 0
    state = rt.control_state()
    assert state["durable_tick"]["A"] == 0 and state["save_errors"]["A"]

    # A successful explicit retry makes the current state durable, but does not silently unpause the game.
    monkeypatch.setattr(rt.store, "save_world", real)
    rt.save_all()
    assert not rt.save_errors
    assert w._durable_tick == 60
    assert rt.paused is True
    close_without_saving(rt)


def test_durability_failure_permanently_invalidates_an_experiment(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    rt.contract = "experiment"
    rt.mind.strict = True
    w = rt.worlds["A"]
    w.tick = 60
    real = rt.store.save_world

    def boom(*args, **kwargs):
        raise OSError("I/O fault")

    monkeypatch.setattr(rt.store, "save_world", boom)
    with pytest.raises(OSError):
        rt._checkpoint(w)
    assert rt.paused and rt.invalid_reason
    assert "durability failure" in rt.invalid_reason
    m = rt.manifest()
    assert m["valid"] is False and m["invalid_reason"] == rt.invalid_reason

    # Preserving the state later does not turn the experiment back into a result.
    monkeypatch.setattr(rt.store, "save_world", real)
    rt.save_all()
    assert not rt.save_errors
    assert rt.invalid_reason
    assert rt.manifest()["valid"] is False
    close_without_saving(rt)


def test_new_match_has_a_tick_zero_durability_boundary(tmp_path):
    rt = Runtime(tmp_path)
    assert {w._durable_tick for w in rt.worlds.values()} == {0}
    rt.reset(seed=91, chits=4, size=64)
    assert {w.tick for w in rt.worlds.values()} == {0}
    assert {w._durable_tick for w in rt.worlds.values()} == {0}
    for w in rt.worlds.values():
        active = json.loads(rt.store.get_meta("active_snapshot:" + w.id))
        assert active[2] == 0
    close_without_saving(rt)
