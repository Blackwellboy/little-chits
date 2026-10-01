"""Auto-record: the story of a day, the clip pipeline, moments filmed live, and the recordings API."""

import io
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from chits.recorder import (DAY_CRF, SAFE_NAME, Moments, Recorder, busiest_spot, clip_seconds, clock_of, concat_cmd,
                            day_fps, encode_cmd, frames_between, is_moment, moment_cmd, moment_concat, moment_name,
                            week_cmd, week_speed)
from chits.story.recording import add_moment_line, day_story, how_they_did_it, moment_line

NAMES = {"a1": "Molo", "a2": "Keva", "a3": "Pip", "a4": "Rin"}


def ev(seq, kind, actor, text="", **data):
    return {"seq": seq, "tick": seq, "kind": kind, "importance": 3, "actor": actor, "text": text, "data": data}


def test_how_they_did_it_explains_discoveries_and_their_spread():
    events = [
        ev(1, "discovery", "a1", "Molo discovered bread", knowledge="recipe:bread", how="discovered"),
        ev(2, "learned", "a2", knowledge="recipe:bread", how="taught", source="a1"),
        ev(3, "learned", "a3", knowledge="recipe:bread", how="observed", source="a1"),
        ev(4, "learned", "a4", knowledge="recipe:sharp_stone", how="taught", source="a2"),
        ev(5, "built", "a2", design="kiln", builders=["a2", "a3"], together=True, first=True),
        ev(6, "belief", "a1", name="The Value of Knowledge", tenet="Knowledge must be shared."),
        ev(7, "birth", "a4"),
    ]
    lines = how_they_did_it(events, NAMES)
    text = "\n".join(lines)
    assert "**Molo** worked out bread by experimenting (#1)" in text
    assert "2 more knew it (1 from a teacher, 1 by watching someone do it)" in text
    assert "Sharp stone spread to 1 more chit, mostly from Keva (#4)" in text
    assert "The first kiln went up, built by Keva and Pip (#5)" in text
    assert "Molo founded a belief, *The Value of Knowledge*" in text
    assert lines[-1] == "Life and loss: 1 birth."


def test_day_story_puts_both_worlds_and_the_clip_together():
    worlds = [
        {"name": "World A", "label": "Direct culture", "brain": "RTX 5090", "lines": ["Something happened (#1)."],
         "chronicle": "# World A — Day 3\n\nThe chits gathered wood.\n\n## Highlights\n\n- a fire"},
        {"name": "World B", "label": "", "brain": "", "lines": [], "chronicle": ""},
    ]
    md = day_story(3, worlds, "day-003.mp4")
    assert md.startswith("# Day 3\n") and "[▶ Watch day 3](day-003.mp4)" in md
    assert "## World A (Direct culture · RTX 5090)" in md and "- Something happened (#1)." in md
    assert "The chits gathered wood." in md and "# World A — Day 3" not in md
    assert "#### Highlights" in md  # the chronicle's sections sit under "The day"
    assert "## World B\n" in md and "A quiet day" in md


def test_frames_between_and_ffmpeg_commands(tmp_path):
    for ms in (1000, 2000, 3000, 4000):
        (tmp_path / f"{ms}.jpg").write_bytes(b"x")
    (tmp_path / ".5000.jpg").write_bytes(b"half-written")
    assert [p.name for p in frames_between(tmp_path, 2000, 4000)] == ["2000.jpg", "3000.jpg"]
    cmd = encode_cmd("ffmpeg", "in/f-%06d.jpg", "out.mp4", 24, "9:16")
    assert cmd[cmd.index("-framerate") + 1] == "24" and "scale=1080:1920" in cmd[cmd.index("-vf") + 1]
    assert cmd[-1] == "out.mp4" and "libx264" in cmd and "yuv420p" in cmd
    assert concat_cmd("ffmpeg", "list.txt", "w.mp4")[-1] == "w.mp4"


def _runtime(tmp_path):
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, chits=6, size=64, mode="versus")
    return rt


def test_recordings_api_is_safe_and_lists_days(tmp_path):
    rt = _runtime(tmp_path)
    rec = rt.recorder
    d = rec.run_dir()
    d.mkdir(parents=True)
    (d / "day-001.md").write_text("# Day 1\n")
    (d / "day-001.mp4").write_bytes(b"")
    (d / "day-002.md").write_text("# Day 2\n")
    runs = rec.listing()
    assert runs[0]["current"] and [x["day"] for x in runs[0]["days"]] == [1, 2]
    assert runs[0]["days"][0]["clip"] == "day-001.mp4" and runs[0]["days"][1]["clip"] is None
    assert rec.file(rt.run_id, "day-001.md") is not None
    for run, name in ((rt.run_id, "../chits.sqlite"), ("..", "day-001.md"), ("frames", "1.jpg"), (rt.run_id, "x.sqlite")):
        assert rec.file(run, name) is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_a_finished_day_becomes_a_clip_and_a_story(tmp_path):
    rt = _runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, fps=6)
    rec.frames.mkdir(parents=True)
    rec.segment_start_ms = int(time.time() * 1000) - 5000
    for i in range(6):  # six tiny frames, as if the browser had filmed them
        f = rec.frames / f"{rec.segment_start_ms + 100 + i}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x{i}0{i}0{i}0:s=64x36",
                        "-frames:v", "1", str(f)], check=True)
    rec.day_ended(1)
    for _ in range(100):
        if (rec.run_dir() / "day-001.md").exists() and not rec.encoding:
            break
        time.sleep(0.1)
    clip, story = rec.run_dir() / "day-001.mp4", rec.run_dir() / "day-001.md"
    assert clip.exists() and clip.stat().st_size > 0, rec.last_error
    assert "# Day 1" in story.read_text() and "## World A" in story.read_text() and "## World B" in story.read_text()
    assert not list(rec.frames.glob("*.jpg")), "used frames are cleared"
    assert rec.listing()[0]["days"][0]["clip"] == "day-001.mp4"


def test_recorder_explains_what_is_missing(tmp_path, monkeypatch):
    rt = _runtime(tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr("chits.tools.timelapse.find_ffmpeg", lambda: None)
    st = rt.recorder.configure(enabled=True, url="http://127.0.0.1:1")
    assert not st["recording"] and "Node.js" in st["last_error"] and "ffmpeg" in st["last_error"]
    assert Path(tmp_path / "recordings" / "recorder.json").exists()
    rt.recorder.configure(enabled=False)


# ------------------------------------------------------------------ slower days, a week under a minute
def test_days_play_at_6_to_8x_and_weeks_stay_under_a_minute():
    assert day_fps(240) == 13  # a day at 1x: 240 frames at 500 ms -> ~18 s, ~6.5x real time
    assert 15 <= 240 / day_fps(240) <= 20
    assert day_fps(120) == 8 and day_fps(2000) == 30  # a fast game or a long day stay watchable
    assert day_fps(240, fixed=24) == 24  # a fixed rate still wins
    assert week_speed([18.5] * 7) == pytest.approx(129.5 / 56, abs=0.01)
    assert week_speed([5] * 7) == 1.0  # never slowed down
    fast = week_cmd("ffmpeg", [Path("day-001.mp4"), Path("day-002.mp4")], "w.mp4", speed=2.3)
    graph = fast[fast.index("-filter_complex") + 1]
    assert fast.count("-i") == 2 and "[0:v]fps=24" in graph and "[1:v]fps=24" in graph
    assert "concat=n=2:v=1:a=0,setpts=PTS/2.300,fps=24[out]" in graph and "libx264" in fast and fast[-1] == "w.mp4"
    # 3.5x the frames of the old clips: a higher CRF keeps a day's size about where it was
    day = encode_cmd("ffmpeg", "f-%06d.jpg", "d.mp4", 13, "16:9", DAY_CRF)
    assert day[day.index("-crf") + 1] == "26" and fast[fast.index("-crf") + 1] == "26"
    assert encode_cmd("ffmpeg", "f-%06d.jpg", "d.mp4")[day.index("-crf") + 1] == "23"


def test_old_fast_settings_are_upgraded(tmp_path):
    rt = _runtime(tmp_path)
    (tmp_path / "recordings").mkdir(exist_ok=True)
    (tmp_path / "recordings" / "recorder.json").write_text(json.dumps(
        {"enabled": False, "url": "http://127.0.0.1:8010", "interval_ms": 1000, "fps": 24, "aspect": "9:16"}))
    rec = Recorder(rt)
    s = rec.settings
    assert s["interval_ms"] == 500 and s["fps"] == 0 and s["moments"] is True and s["v"] == 2
    assert s["aspect"] == "9:16" and s["url"] == "http://127.0.0.1:8010"  # the user's own choices stay
    rec.configure(fps=-3, day_seconds=500)
    assert rec.settings["fps"] == 0 and rec.settings["day_seconds"] == 120
    assert Recorder(rt).settings["interval_ms"] == 500  # a v2 file is taken as it is


# ------------------------------------------------------------------ moments: what triggers, how often
def mev(kind, imp=3, tick=0, world="A", **kw):
    return {"world": world, "tick": tick, "kind": kind, "importance": imp, "text": f"{kind} happened", "x": 5, "y": 6, **kw}


def test_what_counts_as_a_big_moment():
    for kind in ("discovery", "invention", "election", "law", "theft", "first", "era", "arrival", "belief"):
        assert is_moment({"kind": kind, "importance": 2}), kind
    assert is_moment({"kind": "storm", "importance": 4}) and is_moment({"kind": "revelation", "importance": 5})
    assert not is_moment({"kind": "learned", "importance": 3}) and not is_moment({"kind": "speech", "importance": 1})
    # every birth is importance 4: only the first child is a moment; a conversion only when a founder converts
    assert not is_moment({"kind": "birth", "importance": 4}) and is_moment({"kind": "birth", "importance": 4}, first_birth=True)
    assert not is_moment({"kind": "convert", "importance": 3}) and is_moment({"kind": "convert", "importance": 3}, founder=True)


def test_moments_are_throttled_per_world_per_hour_and_queued_by_importance():
    q = Moments(queue_max=2, max_wait_s=45)
    assert q.offer(mev("legacy", 4, tick=100), now=0) == "queued"
    assert q.offer(mev("law", 5, tick=105), now=1) == "throttled"  # same world, within the in-game hour
    assert q.offer(mev("law", 5, tick=105, world="B"), now=1) == "queued"  # the other world has its own hour
    assert q.offer(mev("discovery", 5, tick=110), now=2) == "queued"  # an hour (10 ticks) later
    assert [p["kind"] for p in q.pending] == ["law", "discovery"]  # the queue holds 2: the least important went
    first = q.next(now=3)
    assert first["kind"] == "discovery" and first["name"] == "moment-001-A-discovery-1"  # most important first
    assert q.next(now=4) is None  # one at a time
    assert q.offer(mev("era", 5, tick=120), now=5) == "queued"
    assert q.offer(mev("theft", 3, tick=130, world="B"), now=6) == "queue full"
    q.done()
    assert q.next(now=8)["kind"] == "era"
    q.done()
    assert q.next(now=100) is None and not q.pending  # the law waited too long: skipped, not filmed late


def test_moments_are_capped_per_world_per_day_and_numbered_per_kind():
    q = Moments(per_day=2)
    names = []
    for tick in (10, 20):
        assert q.offer(mev("law", 5, tick=tick), now=tick) == "queued"
        names.append(q.next(now=tick)["name"])
        q.done()
    assert names == ["moment-001-A-law-1", "moment-001-A-law-2"]
    assert q.offer(mev("law", 5, tick=40), now=40) == "day full"
    assert q.offer(mev("law", 5, tick=240), now=41) == "queued"  # a new day
    assert q.next(now=41)["name"] == "moment-002-A-law-1"


def test_moment_names_are_safe_and_readable():
    assert moment_name(12, "A", "discovery", 1) == "moment-012-A-discovery-1"
    assert moment_name(3, "B/../x", "Tool Broke!", 2) == "moment-003-Bx-tool_broke-2"
    for n in (moment_name(1, "", "", 0), moment_name(400, "A", "first", 12)):
        assert SAFE_NAME.match(n + ".mp4") and SAFE_NAME.match(n + ".json")
    assert clock_of(0) == "00:00" and clock_of(240 * 3 + 145) == "14:00"
    assert busiest_spot([(0, 0), (50, 50), (51, 50), (52, 51)]) in {(50, 50), (51, 50), (52, 51)}
    assert busiest_spot([]) is None


def test_moment_frames_play_back_at_their_real_timing(tmp_path):
    frames = [tmp_path / f"{ms}.jpg" for ms in (1000, 1100, 1250, 1300, 1700)]
    text = moment_concat(frames, fps=10)
    durs = [float(line.split()[1]) for line in text.splitlines() if line.startswith("duration")]
    assert durs == [0.1, 0.15, 0.05, 0.4, 0.1]  # a slow paint is held on screen, not skipped
    assert text.splitlines()[-1] == f"file '{frames[-1]}'"
    cmd = moment_cmd("ffmpeg", "list.txt", "m.mp4", 10, "16:9")
    assert cmd[cmd.index("-f") + 1] == "concat" and cmd[cmd.index("-vf") + 1].startswith("fps=10,scale=1280:720")


def test_moment_story_lines():
    info = {"world_name": "World A", "clock": "14:00", "caption": "Molo discovered [bread]", "seq": 42,
            "clip": "moment-003-A-discovery-1.mp4"}
    line = moment_line(info)
    assert line == "- 🎬 **World A**, 14:00: Molo discovered (bread) (#42) · [▶ watch it live](moment-003-A-discovery-1.mp4)"
    md = day_story(3, [{"name": "World A", "lines": []}], "day-003.mp4", [info])
    assert md.index("## Moments") < md.index("## World A") and line in md
    later = add_moment_line(day_story(3, [{"name": "World A", "lines": []}]), line)
    assert later.index("## Moments") < later.index("## World A") and line in later
    two = add_moment_line(later, line.replace("#42", "#43"))
    assert two.count("## Moments") == 1 and "#43" in two and add_moment_line(two, line) == two
    assert two.index("#42") < two.index("#43") < two.index("## World A")


# ------------------------------------------------------------------ moments, end to end with a stand-in browser
class FakeBrowser:
    """Stands in for recorder.mjs: always running, reading commands on stdin."""

    def __init__(self):
        self.stdin = io.BytesIO()
        self.returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def commands(self):
        return [json.loads(x) for x in self.stdin.getvalue().decode().splitlines()]


def _filmed(cmd, n=12, step_ms=100):
    """What the browser leaves behind: n frames named by when they were painted, then done.json."""
    d = Path(cmd["dir"])
    for i in range(n):
        (d / f"{1_000_000 + i * step_ms}.jpg").write_bytes(b"jpg")
    (d / "done.json").write_text(json.dumps({"frames": n}))


def test_a_big_event_is_filmed_close_up_and_told_in_the_days_story(tmp_path, monkeypatch):
    rt = _runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, moments=True)
    rec.proc = browser = FakeBrowser()
    encoded = []

    def fake_ffmpeg(cmd, **kw):  # "encodes" by writing the output file
        encoded.append(cmd)
        Path(cmd[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_ffmpeg)
    w = rt.worlds["A"]
    a = next(iter(w.agents.values()))
    w.emit("learned", f"{a.name} learned to fish", 3, a.id, a.x, a.y)  # not big: nothing happens
    assert browser.commands() == []
    w.emit("discovery", f"{a.name} discovered how to make bread — a first for the world!", 5, a.id, 11, 23,
           knowledge="recipe:bread", how="discovered")
    [cmd] = browser.commands()  # the world's own listener handed it straight to the browser
    assert cmd["cmd"] == "moment" and cmd["world"] == "A" and (cmd["x"], cmd["y"]) == (11, 23)
    assert cmd["caption"].startswith(f"{a.name} discovered how to make bread") and cmd["seconds"] == 15
    assert cmd["fps"] == 10 and cmd["zoom"] >= 3.2 and "Day 1" in cmd["label"]
    assert Path(cmd["dir"]).name == "moment-001-A-discovery-1"
    assert rec.status()["filming"].startswith(a.name)
    w.emit("law", 'Chief decreed: "share"', 5, a.id, 3, 4)  # same in-game hour: throttled
    w.tick += 10
    w.emit("era", "World A enters the Stone Age", 5)  # no place of its own: filmed where the chits are
    assert len(browser.commands()) == 1 and len(rec.moments.pending) == 1  # waits its turn

    out = rec.run_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "day-001.md").write_text("# Day 1\n\n## World A\n\n### How they did it\n- A quiet day.\n")
    _filmed(cmd)
    rec._pump()  # sees it finished and encodes it (the next one starts on the next pump)
    for t in list(rec._threads):
        t.join(5)
    clip, info = out / "moment-001-A-discovery-1.mp4", out / "moment-001-A-discovery-1.json"
    assert clip.exists() and info.exists(), rec.last_error
    meta = json.loads(info.read_text())
    assert meta["kind"] == "discovery" and meta["day"] == 1 and meta["frames"] == 12 and meta["seconds"] == 1.1
    assert "concat" in encoded[0] and "fps=10" in encoded[0][encoded[0].index("-vf") + 1]
    story = (out / "day-001.md").read_text()
    assert "## Moments" in story and "[▶ watch it live](moment-001-A-discovery-1.mp4)" in story
    assert not Path(cmd["dir"]).exists(), "used frames are cleared"
    run = rec.listing()[0]
    assert [m["clip"] for m in run["moments"]] == ["moment-001-A-discovery-1.mp4"]
    assert run["moments"][0]["caption"].startswith(a.name)

    rec._pump()
    second = browser.commands()[1]
    assert Path(second["dir"]).name == "moment-001-A-era-1" and second["caption"] == "World A enters the Stone Age"
    xs = [ag.x for ag in w.agents.values()]
    assert min(xs) <= second["x"] <= max(xs)
    rec.proc = None


def test_moments_can_be_switched_off_and_a_restart_never_overwrites_a_clip(tmp_path):
    rt = _runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, moments=False)
    rec.proc = browser = FakeBrowser()
    w = rt.worlds["B"]
    w.emit("law", "Chief decreed", 5, None, 1, 1)
    assert browser.commands() == []
    rec.settings["moments"] = True
    out = rec.run_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "moment-001-B-law-1.mp4").write_bytes(b"")  # filmed before a restart
    w.tick += 10
    w.emit("law", "Chief decreed again", 5, None, 1, 1)
    assert Path(browser.commands()[0]["dir"]).name == "moment-001-B-law-2"
    _filmed(browser.commands()[0], n=3)  # the page never really showed the world
    rec._pump()
    for t in list(rec._threads):
        t.join(5)
    assert not (out / "moment-001-B-law-2.mp4").exists() and "only 3 frames" in rec.last_error
    assert rec.moments.busy is None
    rec.proc = None


def test_only_the_first_child_and_a_founders_conversion_are_filmed(tmp_path):
    rt = _runtime(tmp_path)
    rec = rt.recorder
    rec.settings.update(enabled=True, moments=True)
    rec.proc = browser = FakeBrowser()
    w = rt.worlds["A"]
    kids = list(w.agents.values())[:2]
    kids[0].parents = ("x1", "x2")  # born just now: the island's first child
    w.emit("birth", f"{kids[0].name} was born", 4, kids[0].id, kids[0].x, kids[0].y)
    assert [Path(c["dir"]).name for c in browser.commands()] == ["moment-001-A-birth-1"]
    rec.moments.done()
    kids[1].parents = ("x1", "x2")
    w.tick += 10
    w.emit("birth", f"{kids[1].name} was born", 4, kids[1].id, kids[1].x, kids[1].y)  # the second: not a moment
    assert len(browser.commands()) == 1
    founder = next(a for a in w.agents.values() if a.generation == 0 and not a.parents)
    w.emit("convert", f"{founder.name} came to believe", 3, founder.id, founder.x, founder.y)
    assert Path(browser.commands()[-1]["dir"]).name == "moment-001-A-convert-1"
    rec.proc = None


def test_a_remote_recorder_reads_the_servers_stream():
    from types import SimpleNamespace

    from chits.tools.record_remote import RemoteRuntime

    rt = RemoteRuntime.__new__(RemoteRuntime)
    rt.worlds = {"A": SimpleNamespace(id="A", name="World A", tick=0, agents={}, dead={}, beliefs={})}
    rt._names, rt._brains = {}, {}
    ev = {"seq": 9, "tick": 481, "kind": "law", "importance": 5, "text": "Chief decreed", "x": 3, "y": 4}
    snap = {"type": "snapshot", "world": {"id": "A"}, "clock": {"tick": 480}, "agents": [{"id": "a1", "name": "Molo", "x": 1, "y": 2}],
            "events": [ev]}
    assert rt.take(snap) == []  # history, not news
    assert rt.worlds["A"].tick == 480 and rt.names(rt.worlds["A"]) == {"a1": "Molo"}
    frame = {"type": "frame", "world": "A", "clock": {"tick": 481}, "agents": [{"id": "a2", "name": "Keva", "x": 5, "y": 5}],
             "events": [ev]}
    assert rt.take(frame) == [ev] and rt.worlds["A"].tick == 481
    assert set(rt.worlds["A"].agents) == {"a2"} and rt.names(rt.worlds["A"]) == {"a1": "Molo", "a2": "Keva"}
    assert rt.take({"type": "frame", "world": "Z", "events": [ev]}) == []
    rt.take({"type": "status", "brains": {"A": {"label": "RTX 5090"}}})
    assert rt.brain_summary()["A"]["label"] == "RTX 5090"


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
def test_a_week_reel_of_days_at_different_rates_keeps_their_length(tmp_path):
    days = []
    for n, (secs, fps) in enumerate(((1, 8), (2, 13))):
        p = tmp_path / f"day-{n + 1:03d}.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s=64x36:r={fps}:d={secs}",
                        "-pix_fmt", "yuv420p", str(p)], check=True)
        days.append(p)
    for speed, want in ((1.0, 3.0), (1.5, 2.0)):
        out = tmp_path / f"week-{speed}.mp4"
        subprocess.run(week_cmd("ffmpeg", days, str(out), speed), check=True)
        assert abs(clip_seconds(out) - want) <= 0.1, (speed, clip_seconds(out))


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
def test_a_moment_clip_runs_at_live_speed(tmp_path):
    frames = tmp_path / "f"
    frames.mkdir()
    t = 5_000
    for i in range(20):  # 2 s of painting, unevenly (as a busy CPU delivers them)
        t += 60 if i % 2 else 140
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x{i:02d}{i:02d}{i:02d}:s=64x36",
                        "-frames:v", "1", str(frames / f"{t}.jpg")], check=True)
    shots = sorted(frames.glob("*.jpg"), key=lambda p: int(p.stem))
    lst = tmp_path / "list.txt"
    lst.write_text(moment_concat(shots, 10))
    out = tmp_path / "m.mp4"
    r = subprocess.run(moment_cmd("ffmpeg", str(lst), str(out), 10, "16:9"), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=r_frame_rate,width",
                            "-of", "json", str(out)], capture_output=True, text=True)
    info = json.loads(probe.stdout)
    span = (int(shots[-1].stem) - int(shots[0].stem)) / 1000 + 0.1
    assert abs(float(info["format"]["duration"]) - span) <= 0.15  # as long as it took to happen
    assert info["streams"][0]["r_frame_rate"] == "10/1" and info["streams"][0]["width"] == 1280


def test_quiet_kinds_are_not_filmed_and_the_storyteller_is():
    from chits.recorder import is_moment
    assert not is_moment({"kind": "legacy", "importance": 4})
    assert is_moment({"kind": "storyteller", "importance": 5})
    assert is_moment({"kind": "wolf_driven_off", "importance": 3})
