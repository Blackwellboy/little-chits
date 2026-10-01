import json

import pytest

from chits.sim.world import SNAPSHOT_SCHEMA, World, migrate_snapshot


def test_uuid_epoch_and_fork():
    w = World("A", "A", 3, "direct", 64, 2)
    w2 = World("A", "A", 3, "direct", 64, 2)
    assert len(w.uuid) == 32 and w.uuid != w2.uuid and w.epoch
    assert w.epochs[0]["epoch"] == w.epoch and w.epochs[0]["parent"] is None
    for _ in range(10):
        w.step()
    old = w.epoch
    new = w.fork_epoch("restored a save point")
    assert new == w.epoch != old
    assert w.epochs[-1] == {**w.epochs[-1], "epoch": new, "parent": old, "from_tick": 10}
    assert any(e.kind == "timeline" for e in w.events)


def test_versioned_snapshots():
    w = World("A", "A", 5, "direct", 64, 2)
    d = json.loads(json.dumps(w.to_dict()))
    assert d["schema"] == SNAPSHOT_SCHEMA == 2 and d["uuid"] == w.uuid and d["epoch"] == w.epoch and "build" in d
    back = World.from_dict(d)
    assert back.uuid == w.uuid and back.epoch == w.epoch and back.epochs == w.epochs
    old = dict(d)
    for k in ("schema", "uuid", "epoch", "epochs", "build"):
        old.pop(k, None)
    m = World.from_dict(migrate_snapshot(old))
    assert len(m.uuid) == 32 and m.epoch
    future = dict(d, schema=SNAPSHOT_SCHEMA + 1)
    with pytest.raises(ValueError):
        World.from_dict(future)


def test_events_are_scoped_to_their_timeline(tmp_path):
    from chits.store import Store

    s = Store(tmp_path / "x.sqlite")
    w = World("A", "A", 7, "direct", 64, 2)
    e1 = w.emit("note", "before the fork", 3)
    s.append_events(w, [e1])
    first = w.epoch
    w.fork_epoch("test")
    e2 = w.emit("note", "after the fork", 3)
    s.append_events(w, [e2])
    now = s.events("A", epoch=w.epoch, limit=50)
    assert [e["text"] for e in now] == ["after the fork"]
    then = s.events("A", epoch=first, limit=50)
    assert [e["text"] for e in then] == ["before the fork"]
    assert len(s.events("A", limit=50)) == 2
