"""F24: recording media is bounded without touching the clip currently being filmed."""

import asyncio
import json
import os
import time

from chits import diag
from chits.runtime import Runtime


def close(rt):
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def run_dir(root, name, started, clip_bytes):
    d = root / name
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"run": name, "started": started}))
    (d / "day-001.mp4").write_bytes(b"x" * clip_bytes)
    (d / "day-001.md").write_text("# evidence stays with an archived run\n")
    return d


def test_retention_removes_oldest_completed_run_before_current(tmp_path):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    old = run_dir(rec.dir, "old-run", 1, 120)
    new = run_dir(rec.dir, "new-run", 2, 120)
    active = run_dir(rec.dir, rt.run_id, 3, 120)

    keep = rec._dir_bytes(new) + rec._dir_bytes(active) + 5
    st = rec.prune_storage(limit_bytes=keep)

    assert not old.exists()
    assert new.exists() and active.exists()
    assert st["run_bytes"] <= keep
    assert rec.last_pruned_bytes > 0
    close(rt)


def test_one_long_active_run_rolls_off_only_old_finalized_video(tmp_path):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    active = rec.run_dir()
    active.mkdir(parents=True, exist_ok=True)
    (active / "run.json").write_text(json.dumps({"run": rt.run_id, "started": 1}))
    first, second = active / "day-001.mp4", active / "day-002.mp4"
    first.write_bytes(b"a" * 160)
    second.write_bytes(b"b" * 160)
    now = time.time()
    os.utime(first, (now - 100, now - 100))
    os.utime(second, (now, now))
    (active / "day-001.md").write_text("keep textual evidence")
    (active / "day-002.md").write_text("keep textual evidence")

    before = rec._dir_bytes(active)
    rec.prune_storage(limit_bytes=before - 100)

    assert not first.exists() and second.exists()
    assert (active / "day-001.md").exists()
    close(rt)


def test_retention_never_touches_live_scratch_frames(tmp_path):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    rec.frames.mkdir(parents=True, exist_ok=True)
    frame = rec.frames / "123.jpg"
    frame.write_bytes(b"frame" * 100)
    active = rec.run_dir()
    active.mkdir(parents=True, exist_ok=True)
    (active / "run.json").write_text(json.dumps({"run": rt.run_id, "started": 1}))

    rec.prune_storage(limit_bytes=1)
    assert frame.exists()
    assert rec.storage_status(force=True)["frames_bytes"] == frame.stat().st_size
    close(rt)


def test_recorder_disk_warning_is_visible_in_diagnostics(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    monkeypatch.setattr(rt.recorder, "storage_status",
                        lambda force=False: {"warning": "low disk space: 1.2 GiB free", "bytes": 123})
    report = diag.report(rt)
    assert any("Recorder: low disk space" in w for w in report["warnings"])
    assert report["recordings"]["bytes"] == 123
    close(rt)


def test_an_archive_held_at_its_cap_is_not_a_warning_but_one_past_it_is(tmp_path):
    # pruning holds the archive at its cap, so at the cap is normal; live, "20.0/20.0 GiB" warned for good
    rt = Runtime(tmp_path)
    rec = rt.recorder
    run_dir(rec.dir, "old-run", 1, 1000)
    gib = 1024 ** 3
    total = rec.storage_status(force=True)["run_bytes"]
    rec.settings["retention_gb"] = total / gib  # exactly at the cap
    assert "recording archive" not in rec.storage_status(force=True)["warning"]
    rec.settings["retention_gb"] = total / gib / 1.5  # half as much again over it: pruning isn't keeping up
    assert "recording archive" in rec.storage_status(force=True)["warning"]
    close(rt)
