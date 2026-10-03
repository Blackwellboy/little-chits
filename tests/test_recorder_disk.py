"""Recording can't fill the disk.

Live evidence (2026-10-04): the diagnostics said "recording archive 28.3/20.0 GiB: old runs aren't being pruned".
The run folder held one `.day-3106-frames` folder of 204,653 frames (29 GiB): a day that lasted about 28 hours of real
time, whose encode ran out of time, so its frames were left behind. They counted toward the cap, but the cap only
ever deleted finished clips: every new clip was rolled off and the frames stayed. These tests reproduce each link."""

import asyncio
import json
import os
import subprocess

from chits import recorder as R
from chits.runtime import Runtime


def close(rt):
    for t in rt.recorder._threads:
        t.join(timeout=30)
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def active_run(rec, rt):
    out = rec.run_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({"run": rt.run_id, "started": 1}))
    return out


def scratch(rec, n, size=10):
    rec.frames.mkdir(parents=True, exist_ok=True)
    made = []
    for i in range(n):
        p = rec.frames / f"{1000 + i}.jpg"
        p.write_bytes(bytes([i % 251]) * size)
        made.append(p)
    return made


def ffmpeg_that(monkeypatch, behave):
    """Stand in for ffmpeg: `behave(cmd)` sees the command and returns a CompletedProcess or raises."""
    calls = []

    def run(cmd, *a, **k):
        calls.append(cmd)
        return behave(cmd)

    monkeypatch.setattr(R.subprocess, "run", run)
    return calls


def test_frames_stranded_in_the_run_folder_are_pruned_before_any_clip(tmp_path):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    out = active_run(rec, rt)
    stranded = out / ".day-3106-frames"
    stranded.mkdir()
    for i in range(20):
        (stranded / f"f-{i + 1:06d}.jpg").write_bytes(b"j" * 500)
    clip = out / "day-3118.mp4"
    clip.write_bytes(b"v" * 300)
    (out / "day-3118.md").write_text("the story stays")

    st = rec.prune_storage(limit_bytes=1000)  # the clip and the story fit; the 10,000 bytes of frames do not

    assert not stranded.exists(), "frames nobody is encoding must fall under the cap"
    assert clip.exists(), "a finished clip was deleted while stranded frames were kept"
    assert st["run_bytes"] <= 1000 and "recording archive" not in st["warning"]
    close(rt)


def test_frames_being_encoded_right_now_are_not_pruned(tmp_path):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    out = active_run(rec, rt)
    busy = out / ".day-007-frames"
    busy.mkdir()
    (busy / "f-000001.jpg").write_bytes(b"j" * 5000)
    rec.encoding = 1
    rec.prune_storage(limit_bytes=10)
    assert busy.exists()
    rec.encoding = 0
    close(rt)


def test_a_failed_or_timed_out_encode_leaves_no_frames_behind(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    out = active_run(rec, rt)

    def timeout(cmd):
        raise subprocess.TimeoutExpired(cmd, 300)

    ffmpeg_that(monkeypatch, timeout)
    rec._finish_day(out, 5, scratch(rec, 12), {}, 0)
    assert rec.stranded_frames(out) == [] and not list(out.glob("**/*.jpg"))
    assert "day 5" in rec.last_error and rec.encoding == 0

    ffmpeg_that(monkeypatch, lambda cmd: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    rec._finish_day(out, 6, scratch(rec, 12), {}, 0)
    assert rec.stranded_frames(out) == [] and "boom" in rec.last_error
    assert not list(rec.frames.glob("*.jpg"))
    close(rt)


def test_a_very_long_day_is_thinned_evenly_before_it_is_encoded(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MAX_DAY_FRAMES", 50)
    rt = Runtime(tmp_path)
    rec = rt.recorder
    out = active_run(rec, rt)
    frames = scratch(rec, 400)
    first, last = frames[0].read_bytes(), frames[-1].read_bytes()
    seen = {}

    def ffmpeg(cmd):
        tmp = out / ".day-009-frames"
        names = sorted(p.name for p in tmp.glob("f-*.jpg"))
        seen.update(names=names, first=(tmp / names[0]).read_bytes(), last=(tmp / names[-1]).read_bytes())
        (out / "day-009.mp4").write_bytes(b"clip")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ffmpeg_that(monkeypatch, ffmpeg)
    rec._finish_day(out, 9, frames, {}, 0)

    assert seen["names"] == [f"f-{i:06d}.jpg" for i in range(1, 51)]  # 50 frames, numbered without gaps
    assert seen["first"] == first and seen["last"] == last  # the whole day, start to end
    assert (out / "day-009.mp4").exists() and not list(rec.frames.glob("*.jpg"))
    close(rt)


def test_frames_waiting_for_the_day_to_end_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MAX_DAY_FRAMES", 50)
    monkeypatch.setattr(R, "SCRATCH_MAX_FRAMES", 100)
    rt = Runtime(tmp_path)
    rec = rt.recorder
    frames = scratch(rec, 100)
    rec.tend(force=True)
    assert len(list(rec.frames.glob("*.jpg"))) == 100  # at the bound: nothing to do
    frames += [rec.frames / "99999.jpg"]
    frames[-1].write_bytes(b"x")
    moment = rec.frames / "moments" / "moment-001-A-first-1"
    moment.mkdir(parents=True)
    (moment / "123.jpg").write_bytes(b"m")  # a moment being filmed is the browser's: never thinned

    rec.tend(force=True)

    left = sorted(int(p.stem) for p in rec.frames.glob("*.jpg"))
    assert len(left) == 50 and left[0] == 1000 and left[-1] == 99999
    assert (moment / "123.jpg").exists()
    close(rt)


def test_housekeeping_runs_while_the_world_stands_still(tmp_path, monkeypatch):
    # the 29 GiB piled up while no tick ran; watch() is only called from the tick loop
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    rt = Runtime(tmp_path)
    calls = []
    monkeypatch.setattr(rt.recorder, "tend", lambda force=False: calls.append(1))

    async def stand_still():
        ticks = {wid: w.tick for wid, w in rt.worlds.items()}
        await rt.start()
        await asyncio.sleep(0.6)
        for t in (rt._task, rt._bcast):
            t.cancel()
        assert ticks == {wid: w.tick for wid, w in rt.worlds.items()}

    asyncio.run(stand_still())
    assert calls, "nothing bounded the scratch frames while the game was paused"
    close(rt)


def test_recovery_reads_days_past_999_and_does_not_block(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    out = active_run(rec, rt)
    tmp = out / ".day-3106-frames"
    tmp.mkdir()
    for i in range(3):
        (tmp / f"f-{i + 1:06d}.jpg").write_bytes(b"j")
    (out / "day-3106.md").write_text("already told")
    made = []

    def ffmpeg(cmd):
        made.append(cmd[-1])
        open(cmd[-1], "wb").write(b"clip")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ffmpeg_that(monkeypatch, ffmpeg)
    rec.recover()
    for t in rec._threads:
        t.join(timeout=30)
    assert [os.path.basename(m) for m in made] == ["day-3106.mp4"]  # (it used to be read as day 310)
    assert not tmp.exists() and rec._recovering is False
    close(rt)


def test_a_fresh_install_records_nothing_and_caps_low_but_an_existing_one_keeps_its_cap(tmp_path):
    fresh = Runtime(tmp_path / "fresh")
    assert fresh.recorder.settings["enabled"] is False  # recording is opt-in
    assert fresh.recorder.settings["retention_gb"] == 5.0
    assert fresh.recorder.storage_status(force=True)["limit_bytes"] == 5 * 1024 ** 3
    close(fresh)

    # an installation from before this change has a settings file without the key: it ran under 20 GiB, and stays there
    old = tmp_path / "old" / "recordings"
    old.mkdir(parents=True)
    (old / "recorder.json").write_text(json.dumps({"enabled": False, "url": "", "aspect": "16:9"}))
    existing = Runtime(tmp_path / "old")
    assert existing.recorder.settings["retention_gb"] == 20.0
    close(existing)

    chosen = tmp_path / "chosen" / "recordings"
    chosen.mkdir(parents=True)
    (chosen / "recorder.json").write_text(json.dumps({"enabled": False, "retention_gb": 50.0, "v": 2}))
    explicit = Runtime(tmp_path / "chosen")
    assert explicit.recorder.settings["retention_gb"] == 50.0
    explicit.recorder.configure(retention_gb=2.5)
    assert json.loads((chosen / "recorder.json").read_text())["retention_gb"] == 2.5
    assert explicit.recorder.status()["storage"]["limit_bytes"] == int(2.5 * 1024 ** 3)
    close(explicit)


def test_filming_does_not_start_on_a_nearly_full_disk(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, url="http://localhost:1")
    monkeypatch.setattr(rec, "missing", lambda: [])
    monkeypatch.setattr(rec, "free_bytes", lambda: 1024 ** 3)  # 1 GiB left
    started = []
    monkeypatch.setattr(R.subprocess, "Popen", lambda *a, **k: started.append(a))
    rec.start()
    assert not started and "disk" in rec.last_error
    assert rec.storage_status(force=True)["free_bytes"] == 1024 ** 3
    close(rt)


class FakeBrowser:
    """Stands in for the recorder's browser process."""

    def __init__(self):
        self.returncode = None
        self.stdin = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode


def test_filming_starts_again_by_itself_when_the_disk_has_room_even_while_paused(tmp_path, monkeypatch):
    # only tend() is called here, never watch(): that is all a paused game (no ticks) ever runs
    rt = Runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, url="http://localhost:1")
    monkeypatch.setattr(rec, "missing", lambda: [])
    free = {"bytes": 50 * 1024 ** 3}
    monkeypatch.setattr(rec, "free_bytes", lambda: free["bytes"])
    started = []

    def popen(*a, **k):
        started.append(FakeBrowser())
        return started[-1]

    monkeypatch.setattr(R.subprocess, "Popen", popen)
    rec.start()
    assert len(started) == 1 and rec.running()

    free["bytes"] = 1024 ** 3  # the disk fills up
    rec.tend(force=True)
    assert not rec.running() and "Recording is paused" in rec.last_error
    rec.tend(force=True)
    assert len(started) == 1, "it must stay off while the disk is nearly full"

    free["bytes"] = 50 * 1024 ** 3  # space is freed
    rec.tend(force=True)
    assert len(started) == 2 and rec.running(), "the message promises it starts again by itself"
    assert rec.last_error == ""
    rec.tend(force=True)
    assert len(started) == 2  # (and only once)

    # switched off while waiting for room: room coming back must not switch it on
    free["bytes"] = 1024 ** 3
    rec.tend(force=True)
    rec.settings["enabled"] = False
    free["bytes"] = 50 * 1024 ** 3
    rec.tend(force=True)
    assert len(started) == 2 and not rec.running()
    rec.proc = None
    close(rt)


def test_filming_refused_at_the_start_for_a_full_disk_also_starts_once_there_is_room(tmp_path, monkeypatch):
    rt = Runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, url="http://localhost:1")
    monkeypatch.setattr(rec, "missing", lambda: [])
    free = {"bytes": 1024 ** 3}
    monkeypatch.setattr(rec, "free_bytes", lambda: free["bytes"])
    started = []

    def popen(*a, **k):
        started.append(FakeBrowser())
        return started[-1]

    monkeypatch.setattr(R.subprocess, "Popen", popen)
    rec.start()
    assert not started
    free["bytes"] = 50 * 1024 ** 3
    rec.tend(force=True)
    assert len(started) == 1 and rec.running()
    rec.proc = None
    close(rt)


def test_spread_keeps_both_ends():
    assert R.spread(10, 3) == [0, 4, 9] or R.spread(10, 3) == [0, 5, 9]
    assert R.spread(3, 10) == [0, 1, 2] and R.spread(0, 5) == [] and R.spread(7, 1) == [0]
    picked = R.spread(204653, 3600)
    assert len(picked) == 3600 and picked[0] == 0 and picked[-1] == 204652
