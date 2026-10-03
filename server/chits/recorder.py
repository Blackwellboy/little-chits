"""Auto-record (🎞): film the observer while the game runs, one clip and one story per in-game day, plus
real-time close-ups of the big moments.

scripts/recorder.mjs (a headless browser in record mode, with the director camera) saves a frame every 500 ms
into recordings/frames/<ms>.jpg: both worlds side by side, or the one world in single mode. When the runtime
finishes a day, the frames taken since the previous day ended become recordings/<run>/day-NNN.mp4 (played back
at about 6-8x, so a day lasts 15-20 s), and day-NNN.md tells what happened and how the chits did it. Every 7 days
the day clips are joined, sped up to under a minute, into week-NN.mp4 beside that week's saga.

Moments: when a world emits a big event (a discovery, an election, a law, a first...), the same browser opens a
second page zoomed in on where it happened and films ~15 s at live speed with the event as the caption:
recordings/<run>/moment-DDD-W-kind-N.mp4, with a .json beside it and a line in that day's story. One is filmed
at a time, at most one per in-game hour per world; extras wait briefly in a short queue or are skipped.

Settings live in recordings/recorder.json, so recording carries on after a restart. Nothing here touches the
simulation: it only watches the page and reads the event stream."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

log = logging.getLogger("chits.recorder")
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "recorder.mjs"
TICKS_PER_DAY = 240
HOUR_TICKS = TICKS_PER_DAY // 24
SETTINGS_VERSION = 2
# fps 0 = automatic: whatever makes a day last about day_seconds (see day_fps)
DEFAULTS: Dict[str, Any] = {"enabled": False, "url": "", "interval_ms": 500, "fps": 0, "aspect": "16:9",
                            "day_seconds": 18, "week_seconds": 56, "moments": True,
                            "retention_gb": 5.0, "v": SETTINGS_VERSION}
# an installation from before the cap could be chosen ran under 20 GiB: it keeps that until its owner changes it
LEGACY_RETENTION_GB = 20.0
# The most frames a day's clip can show: 30 fps for 120 s (the longest day_seconds). A day that took hours of real
# time (a paused game, slow models) is thinned to this many, evenly spaced, before it is encoded: live, one day held
# 204,653 frames (29 GiB), ffmpeg timed out on it, and the frames were stranded outside the reach of the cap.
MAX_DAY_FRAMES = 3600
SCRATCH_MAX_FRAMES = 2 * MAX_DAY_FRAMES  # frames waiting for the day to end: thinned back to MAX_DAY_FRAMES past this
MIN_FREE_BYTES = 2 * 1024 ** 3  # filming stops while the disk has less than this free
DAY_FRAMES_DIR = re.compile(r"^\.day-(\d+)-frames$")
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FILMED = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960)}  # what recorder.mjs captures
SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+(\.(mp4|md|json))?$")

# ------------------------------------------------------------------ moments: what gets filmed close up
MOMENT_KINDS = frozenset({"discovery", "invention", "election", "law", "theft", "first", "era", "arrival", "belief",
                          "storyteller", "wolf_driven_off"})
# importance 4, but not worth filming: "X learned from a tablet left by the late Y" was 6 of the first 11 moments
QUIET_KINDS = frozenset({"legacy", "learned", "reflection"})
KIND_BONUS = {"discovery": 20, "invention": 20, "first": 15, "era": 15, "storyteller": 15, "birth": 15, "belief": 10, "election": 10,
              "law": 10, "arrival": 5, "theft": 5, "convert": 5}
MOMENT_SECONDS = 15
MOMENT_FPS = 10
MOMENT_ZOOM = 3.5  # close enough for names (shown from 3.2), speech bubbles and buildings
MOMENT_TIMEOUT_S = 90  # past its length: the browser never finished it, give up
CAPTION_MAX = 160


def is_moment(ev: Dict[str, Any], first_birth: bool = False, founder: bool = False) -> bool:
    """A big moment worth filming at live speed: the listed kinds, or anything of importance 4+. Births are all
    importance 4, so only the world's first child counts; a conversion counts when a founder converts."""
    kind = ev.get("kind", "")
    if kind in QUIET_KINDS:
        return False
    if kind == "birth":
        return first_birth
    if kind == "convert":
        return founder
    return kind in MOMENT_KINDS or int(ev.get("importance") or 0) >= 4


def moment_score(ev: Dict[str, Any]) -> int:
    return int(ev.get("importance") or 0) * 10 + KIND_BONUS.get(ev.get("kind", ""), 0)


def moment_name(day: int, world: str, kind: str, n: int) -> str:
    """File stem of a moment clip: moment-012-A-discovery-1 (the day, the world, what happened, the how-manieth
    of that kind in that world that day). Always a SAFE_NAME."""
    w = re.sub(r"[^A-Za-z0-9]", "", world) or "W"
    k = re.sub(r"[^a-z0-9]+", "_", kind.lower()).strip("_") or "event"
    return f"moment-{max(0, int(day)):03d}-{w}-{k}-{max(1, int(n))}"


def day_of(tick: int) -> int:
    return int(tick) // TICKS_PER_DAY + 1


def clock_of(tick: int) -> str:
    return f"{(int(tick) % TICKS_PER_DAY) // HOUR_TICKS:02d}:00"


def busiest_spot(points: Sequence[Tuple[float, float]], radius: float = 8.0) -> Optional[Tuple[float, float]]:
    """Where to point the camera for a moment with no place of its own (a new era, a storm): the chit with the
    most others around it."""
    if not points:
        return None
    r2 = radius * radius
    return max(points, key=lambda p: sum(1 for q in points if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= r2))


class Moments:
    """Which big moments get filmed. One at a time (`busy`); at most one per in-game hour per world (by tick);
    a queue of a few, the most important first, where a moment waits at most `max_wait_s`; and a cap per world
    per day so a hectic day can't fill the disk. `now` is a monotonic clock in seconds, passed in for tests."""

    def __init__(self, gap_ticks: int = HOUR_TICKS, queue_max: int = 3, max_wait_s: float = 45.0,
                 per_day: int = 6) -> None:
        self.gap_ticks, self.queue_max, self.max_wait_s, self.per_day = gap_ticks, queue_max, max_wait_s, per_day
        self.pending: List[Dict[str, Any]] = []
        self.busy: Optional[Dict[str, Any]] = None
        self.last_tick: Dict[str, int] = {}
        self.named: Counter = Counter()  # (day, world, kind) -> clips named so far
        self.filmed: Counter = Counter()  # (day, world) -> clips started

    def offer(self, m: Dict[str, Any], now: float) -> str:
        """m: world, tick, kind, importance, text, x, y (and seq). Returns "queued" or why it was skipped."""
        w, tick = m["world"], int(m["tick"])
        last = self.last_tick.get(w)
        if last is not None and 0 <= tick - last < self.gap_ticks:
            return "throttled"
        if self.filmed[(day_of(tick), w)] >= self.per_day:
            return "day full"
        item = {**m, "at": now, "score": moment_score(m)}
        self.pending.append(item)
        self.last_tick[w] = tick
        if len(self.pending) > self.queue_max:
            drop = min(self.pending, key=lambda p: (p["score"], p["tick"]))
            self.pending.remove(drop)
            if drop is item:
                return "queue full"
        return "queued"

    def next(self, now: float) -> Optional[Dict[str, Any]]:
        """The moment to film now (named, and marked busy), or None while one is filming or nothing waits."""
        if self.busy is not None:
            return None
        self.pending = [p for p in self.pending if now - p["at"] <= self.max_wait_s]
        if not self.pending:
            return None
        best = max(self.pending, key=lambda p: (p["score"], p["tick"]))
        self.pending.remove(best)
        day, w = day_of(best["tick"]), best["world"]
        key = (day, w, re.sub(r"[^a-z0-9]+", "_", best["kind"].lower()))
        self.named[key] += 1
        self.filmed[(day, w)] += 1
        best.update(day=day, name=moment_name(day, w, best["kind"], self.named[key]), started=now)
        self.busy = best
        return best

    def done(self) -> None:
        self.busy = None


def moment_concat(frames: Sequence[Path], fps: int = MOMENT_FPS) -> str:
    """An ffconcat list that plays frames named <ms>.jpg for exactly as long as they were apart when filmed, so
    the clip runs at live speed whatever rate the browser managed (the last frame gets one frame's time)."""
    stamps = [int(p.stem) for p in frames]
    lines = ["ffconcat version 1.0"]
    for i, p in enumerate(frames):
        dur = (stamps[i + 1] - stamps[i]) / 1000 if i + 1 < len(frames) else 1 / fps
        lines += [f"file '{p}'", f"duration {max(0.001, dur):.3f}"]
    if frames:
        lines.append(f"file '{frames[-1]}'")  # the concat demuxer ignores the last entry's duration otherwise
    return "\n".join(lines) + "\n"


def moment_cmd(ffmpeg: str, list_file: str, out: str, fps: int = MOMENT_FPS, aspect: str = "16:9") -> List[str]:
    """Frames at their real timing -> a constant-rate clip at the size they were filmed (720p: no upscale)."""
    w, h = FILMED.get(aspect, FILMED["16:9"])
    vf = f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    return [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_file, "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]


def day_fps(frames: int, fixed: int = 0, seconds: float = 18) -> int:
    """Playback rate for a day's frames: `fixed` when set, otherwise whatever makes the day last about `seconds`
    (a day at 1x is 240 frames at 500 ms: 13 fps, ~6.5x real time), kept between 8 and 30 fps."""
    if fixed and fixed > 0:
        return int(fixed)
    return max(8, min(30, round(frames / max(1.0, float(seconds)))))


def week_speed(seconds: Iterable[float], target: float = 56) -> float:
    """How much to speed a week's day clips up so the reel stays under `target` seconds (never slow it down)."""
    total = sum(seconds)
    return round(max(1.0, total / max(1.0, float(target))), 3)


# A day is now ~3.5x as many frames as the old 5 s clips: CRF 26 keeps a day near the old ~4 MB, and pixel art
# and captions stay crisp at it (checked by eye on 1080p frames)
DAY_CRF = 26


def encode_cmd(ffmpeg: str, pattern: str, out: str, fps: int = 24, aspect: str = "16:9", crf: int = 23) -> List[str]:
    w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    return [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", pattern, "-vf", vf, "-c:v", "libx264",
            "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]


def concat_cmd(ffmpeg: str, list_file: str, out: str) -> List[str]:
    return [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy",
            "-movflags", "+faststart", out]


def week_cmd(ffmpeg: str, clips: Sequence[Path], out: str, speed: float = 1.0, aspect: str = "16:9",
             fps: int = 24) -> List[str]:
    """The week reel: the day clips joined and sped up by `speed`. Each day has its own frame rate (fitted to its
    frame count), which the concat demuxer mis-times even when re-encoding (a 3 s pair came out 2.46 s), so every
    day is decoded on its own, brought to one rate and size, then joined with the concat filter."""
    w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for c in clips:
        cmd += ["-i", str(c)]
    each = "".join(f"[{i}:v]fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,"
                   f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,setpts=PTS-STARTPTS[v{i}];"
                   for i in range(len(clips)))
    join = "".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0," \
           f"setpts=PTS/{speed:.3f},fps={fps}[out]"
    return cmd + ["-filter_complex", each + join, "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "veryfast",
                  "-crf", str(DAY_CRF), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]


def clip_seconds(path: Path, ffmpeg: str = "ffmpeg") -> Optional[float]:
    """A clip's length from ffprobe (next to ffmpeg, or on PATH), or None."""
    probe = Path(ffmpeg).with_name("ffprobe")
    exe = str(probe) if probe.exists() else (shutil.which("ffprobe") or "")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------------------------- the director's cut
CUT_N = 8  # moments in a week's cut
CUT_PER_KIND = 3  # at most this many of one kind, so a cut isn't eight elections


def week_of(day: int) -> int:
    return (max(1, int(day)) - 1) // 7 + 1


def cut_plan(moments: Sequence[Dict[str, Any]], week: int, n: int = CUT_N) -> List[Dict[str, Any]]:
    """A week's best moments for a post: the top n by story score (at most CUT_PER_KIND of one kind), then told in
    the order they happened, numbered, each with its caption and its live-speed clip."""
    ranked = sorted((m for m in moments if week_of(m.get("day") or 1) == week),
                    key=lambda m: (-moment_score({"kind": m.get("kind"), "importance": m.get("importance")}),
                                   int(m.get("tick") or 0), str(m.get("name"))))
    picked, per_kind = [], Counter()
    for m in ranked:
        if per_kind[m.get("kind")] >= CUT_PER_KIND:
            continue
        picked.append(m)
        per_kind[m.get("kind")] += 1
        if len(picked) >= n:
            break
    picked.sort(key=lambda m: (int(m.get("tick") or 0), str(m.get("name"))))
    return [{"n": i + 1, "file": f"cut-{week:02d}-{i + 1:02d}-{m['name']}.mp4", "clip": m["clip"],
             "caption": m.get("caption") or "", "day": m.get("day"), "clock": m.get("clock"),
             "world": m.get("world_name") or m.get("world"), "kind": m.get("kind"), "seconds": m.get("seconds")}
            for i, m in enumerate(picked)]


def cut_markdown(week: int, plan: Sequence[Dict[str, Any]], video: Optional[str]) -> str:
    """The shot list for the post: one numbered line (the caption) per clip, in order."""
    lines = [f"# Director's cut, week {week}", ""]
    if video:
        lines += [f"[▶ Watch the whole cut]({video})", ""]
    for c in plan:
        when = f"Day {c['day']}" + (f", {c['clock']}" if c.get("clock") else "")
        secs = f", {c['seconds']:.0f} s" if c.get("seconds") else ""
        lines.append(f"{c['n']:02d}. **{when}, {c['world']}**: {c['caption']} ([clip]({c['file']}){secs})")
    return "\n".join(lines).rstrip() + "\n"


def spread(n: int, keep: int) -> List[int]:
    """`keep` indices out of range(n), evenly spaced, always with the first and the last."""
    if keep <= 0 or n <= 0:
        return []
    if n <= keep:
        return list(range(n))
    if keep == 1:
        return [0]
    return sorted({round(i * (n - 1) / (keep - 1)) for i in range(keep)})


def thin(paths: Sequence[Path], keep: int) -> List[Path]:
    """Keep `keep` of these frame files, evenly spaced in time, and delete the rest. Returns the ones kept."""
    if len(paths) <= keep:
        return list(paths)
    wanted = set(spread(len(paths), keep))
    kept = []
    for i, p in enumerate(paths):
        if i in wanted:
            kept.append(p)
        else:
            try:
                p.unlink()
            except OSError:
                pass
    return kept


def frames_between(frames_dir: Path, start_ms: int, end_ms: int) -> List[Path]:
    """Frames taken in [start_ms, end_ms), oldest first. Frame files are named by the time they were taken."""
    found = []
    for p in frames_dir.glob("*.jpg"):
        if p.stem.isdigit() and start_ms <= int(p.stem) < end_ms:
            found.append((int(p.stem), p))
    return [p for _, p in sorted(found)]


class Recorder:
    def __init__(self, rt) -> None:
        self.rt = rt
        self.dir = rt.data_dir / "recordings"
        self.frames = self.dir / "frames"
        self.settings: Dict[str, Any] = {**DEFAULTS, **self._load()}
        self.proc: Optional[subprocess.Popen] = None
        self.proc_world = ""
        self.segment_start_ms = int(time.time() * 1000)
        self.last_error = ""
        self.last_clip = ""
        self.encoding = 0
        self._next_restart = 0.0
        self._lock = threading.Lock()
        self._threads: List[threading.Thread] = []
        self._recovered = False
        self.moments = Moments()
        self._mlock = threading.Lock()  # the moment queue: events arrive from the tick, finishes from watch()
        self._moment_jobs: set = set()  # moment folders being encoded
        self._storage_checked = 0.0
        self._storage_cache: Dict[str, Any] = {}
        self._next_prune = 0.0
        self._next_tend = 0.0
        self._recovering = False
        self._disk_paused = False  # filming was stopped (or not started) because the disk was nearly full
        self.last_pruned_bytes = 0

    # ------------------------------------------------------------ settings and status
    def _load(self) -> Dict[str, Any]:
        try:
            s = json.loads((self.dir / "recorder.json").read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(s, dict):
            return {}
        if int(s.get("v") or 1) < SETTINGS_VERSION:
            # v1 filmed a frame a second and played it at 24 fps (24x real time): far too fast to follow
            s = {k: v for k, v in s.items() if k not in ("interval_ms", "fps")}
            s["v"] = SETTINGS_VERSION
        s.setdefault("retention_gb", LEGACY_RETENTION_GB)  # (a fresh install has no file, and gets the lower default)
        return s

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "recorder.json").write_text(json.dumps(self.settings, indent=2))

    def run_dir(self) -> Path:
        return self.dir / self.rt.run_id

    @staticmethod
    def _dir_bytes(path: Path) -> int:
        total = 0
        if not path.exists():
            return 0
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
        return total

    def storage_status(self, force: bool = False) -> Dict[str, Any]:
        """Disk use for recording media. Run folders count toward retention; live scratch frames are reported
        separately because deleting a frame while ffmpeg/browser owns it would corrupt the current clip."""
        now = time.monotonic()
        if self._storage_cache and not force and now - self._storage_checked < 60:
            return dict(self._storage_cache)
        self.dir.mkdir(parents=True, exist_ok=True)
        active = self.run_dir()
        runs = [p for p in self.dir.iterdir() if p.is_dir() and p.name != "frames"]
        run_bytes = sum(self._dir_bytes(p) for p in runs)
        active_bytes = self._dir_bytes(active)
        frames_bytes = self._dir_bytes(self.frames)
        free_bytes = self.free_bytes()
        limit_bytes = max(0, int(float(self.settings.get("retention_gb") or 0) * 1024 ** 3))
        warning = ""
        if free_bytes >= 0 and free_bytes < 5 * 1024 ** 3:
            warning = f"low disk space: {free_bytes / 1024 ** 3:.1f} GiB free"
        # pruning (every 5 minutes) holds the archive at its cap, so being near or at it is the normal state: say so
        # only when it runs well past the cap, i.e. pruning isn't keeping up (live, "20.0/20.0 GiB" warned for good)
        if limit_bytes and run_bytes > int(limit_bytes * 1.1):
            near = f"recording archive {run_bytes / 1024 ** 3:.1f}/{limit_bytes / 1024 ** 3:.1f} GiB: old runs aren't being pruned"
            warning = f"{warning}; {near}" if warning else near
        out = {"bytes": run_bytes + frames_bytes, "run_bytes": run_bytes, "active_bytes": active_bytes,
               "frames_bytes": frames_bytes, "free_bytes": free_bytes, "limit_bytes": limit_bytes,
               "warning": warning, "last_pruned_bytes": self.last_pruned_bytes}
        self._storage_cache, self._storage_checked = out, now
        return dict(out)

    def free_bytes(self) -> int:
        """Free space on the disk the recordings are on, or -1 when it can't be read."""
        try:
            return shutil.disk_usage(self.dir).free
        except OSError:
            return -1

    def disk_low(self) -> bool:
        return 0 <= self.free_bytes() < MIN_FREE_BYTES

    def stranded_frames(self, run: Path) -> List[Path]:
        """Folders of frames set aside for a day's clip (.day-NNN-frames), oldest first. One exists only while that
        day is being encoded; any that are still there when nothing is encoding were left by a crash or a failure."""
        found = []
        for d in run.glob(".day-*-frames"):
            try:
                if d.is_dir() and DAY_FRAMES_DIR.match(d.name):
                    found.append((d.stat().st_mtime, d))
            except OSError:
                pass
        return [d for _, d in sorted(found)]

    def thin_scratch(self) -> int:
        """Bound the frames waiting for the day to end. The browser adds one every interval even while the game is
        paused, so a day can last any length of real time; a clip can show at most MAX_DAY_FRAMES of them. Only whole
        frames in frames/ are thinned (they are renamed into place when complete, and nothing reads them until the
        day ends); a moment being filmed (frames/moments) is left alone. Returns how many were deleted."""
        if not self.frames.exists():
            return 0
        waiting = frames_between(self.frames, 0, 1 << 62)
        if len(waiting) <= SCRATCH_MAX_FRAMES:
            return 0
        return len(waiting) - len(thin(waiting, MAX_DAY_FRAMES))

    def tend(self, force: bool = False) -> None:
        """Keep recording within its disk budget. Runs on the wall clock (the runtime calls it whether or not the
        world is ticking: the over-cap bytes seen live piled up while the game stood still)."""
        now = time.monotonic()
        if not force and now < self._next_tend:
            return
        self._next_tend = now + 30
        try:
            self.thin_scratch()
            if self.running() and self.disk_low():
                self.last_error = self._disk_low_message()
                self._disk_paused = True
                self.proc.terminate()  # (start() refuses until there is room again)
            elif self._disk_paused and not self.running() and not self.disk_low():
                # Room again: start filming from here, on the wall clock. watch() only runs after a tick, so a paused
                # game stayed unfilmed for good although the message says it starts again by itself.
                self._disk_paused = False
                if self.settings["enabled"]:
                    self.proc = None
                    self.start()
            if force or now >= self._next_prune:
                self._next_prune = now + 300
                self.prune_storage()
        except Exception as e:  # never let a recording problem hurt the game
            log.warning("recording housekeeping failed: %s", e)

    @staticmethod
    def _disk_low_message() -> str:
        return (f"Recording is paused: the disk has less than {MIN_FREE_BYTES / 1024 ** 3:.0f} GiB free. "
                "Free some space and it starts again by itself.")

    def prune_storage(self, limit_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Keep recording media bounded without touching live scratch frames.

        Old completed run directories go first. If the active run alone crosses the cap, frames stranded by a
        failed or interrupted encode go next, then its oldest finalized MP4 clips, while story/JSON evidence stays.
        Never prune the active run while a clip is encoding.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        cap = max(0, int(limit_bytes if limit_bytes is not None else
                         float(self.settings.get("retention_gb") or 0) * 1024 ** 3))
        before = self.storage_status(force=True)["run_bytes"]
        if cap <= 0 or before <= cap:
            self.last_pruned_bytes = 0
            return self.storage_status(force=True)

        active = self.run_dir()
        completed = []
        for p in self.dir.iterdir():
            if not p.is_dir() or p.name == "frames" or p == active or not (p / "run.json").exists():
                continue
            try:
                stamp = json.loads((p / "run.json").read_text()).get("started") or p.stat().st_mtime
            except (OSError, ValueError, TypeError):
                stamp = p.stat().st_mtime
            completed.append((float(stamp), p))
        current = before
        for _, p in sorted(completed):
            if current <= cap:
                break
            n = self._dir_bytes(p)
            shutil.rmtree(p, ignore_errors=True)
            current -= n

        # A single months-long run can itself exceed the cap. Finalized videos are derivative media, so roll the
        # oldest ones off; markdown/JSON evidence stays. Scratch frames and a clip currently encoding are untouchable.
        if current > cap and active.exists() and self.encoding == 0 and not self._moment_jobs and not self._recovering:
            # Frames nobody is encoding are scratch, not evidence, and they count toward the cap: they go before any
            # finished clip. (Live, 29 GiB of them sat in the run folder while every new clip was rolled off instead.)
            for d in self.stranded_frames(active):
                if current <= cap:
                    break
                n = self._dir_bytes(d)
                shutil.rmtree(d, ignore_errors=True)
                current -= n
            clips = []
            for p in active.glob("*.mp4"):
                try:
                    clips.append((p.stat().st_mtime, p, p.stat().st_size))
                except OSError:
                    pass
            for _, p, n in sorted(clips):
                if current <= cap:
                    break
                p.unlink(missing_ok=True)
                current -= n

        self.last_pruned_bytes = max(0, before - current)
        self._storage_cache = {}
        return self.storage_status(force=True)

    def world_param(self) -> str:
        return "split" if len(self.rt.worlds) > 1 else next(iter(self.rt.worlds), "A")

    def missing(self) -> List[str]:
        from .tools.timelapse import find_ffmpeg

        out = []
        if not shutil.which("node"):
            out.append("Node.js (sudo apt install nodejs)")
        if not find_ffmpeg():
            out.append("ffmpeg (sudo apt install ffmpeg)")
        if not (ROOT / "web" / "node_modules" / "playwright").exists():
            out.append("Playwright (cd web && npm i -D playwright && npx playwright install chromium)")
        return out

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> Dict[str, Any]:
        waiting = sum(1 for _ in self.frames.glob("*.jpg")) if self.frames.exists() else 0
        busy = self.moments.busy
        return {**self.settings, "recording": self.running(), "frames_waiting": waiting, "encoding": self.encoding,
                "last_clip": self.last_clip, "last_error": self.last_error, "run": self.rt.run_id,
                "world": self.world_param(), "missing": self.missing(), "storage": self.storage_status(),
                "filming": busy["text"][:CAPTION_MAX] if busy else "", "moments_waiting": len(self.moments.pending)}

    def configure(self, **changes: Any) -> Dict[str, Any]:
        for k in ("enabled", "url", "interval_ms", "fps", "aspect", "moments", "day_seconds", "retention_gb"):
            if changes.get(k) is not None:
                self.settings[k] = changes[k]
        if self.settings["aspect"] not in ASPECTS:
            self.settings["aspect"] = "16:9"
        self.settings["interval_ms"] = max(250, min(10000, int(self.settings["interval_ms"])))
        fps = int(self.settings["fps"] or 0)
        self.settings["fps"] = 0 if fps <= 0 else max(6, min(60, fps))  # 0: fit the day to day_seconds
        self.settings["day_seconds"] = max(5, min(120, int(self.settings.get("day_seconds") or 18)))
        self.settings["moments"] = bool(self.settings.get("moments"))
        self.settings["retention_gb"] = max(1.0, min(500.0, float(self.settings.get("retention_gb")
                                                                    or DEFAULTS["retention_gb"])))
        self._storage_cache = {}
        self._next_prune = 0.0  # a lower cap applies at the next housekeeping pass, not minutes later
        self._save()
        if self.settings["enabled"]:
            self.stop()  # (re)start with the new settings
            self.start()
        else:
            self.stop()
        return self.status()

    # ------------------------------------------------------------ the browser that films
    def start(self) -> None:
        if self.running() or not self.settings["enabled"] or not self.settings["url"]:
            return
        missing = self.missing()
        if missing:
            self.last_error = "Can't record yet. Missing: " + "; ".join(missing)
            return
        if self.disk_low():
            self.last_error = self._disk_low_message()
            self._disk_paused = True  # (tend() starts it once there is room)
            return
        self.frames.mkdir(parents=True, exist_ok=True)
        self.proc_world = self.world_param()
        cmd = ["node", str(SCRIPT), "--url", self.settings["url"], "--out", str(self.frames),
               "--interval-ms", str(self.settings["interval_ms"]), "--aspect", self.settings["aspect"],
               "--world", self.proc_world]
        logf = open(self.dir / "recorder.log", "a")
        # a moment the browser never finished belongs to nobody now (finished ones are still encoded by _pump)
        for d in (self.frames / "moments").glob("moment-*") if (self.frames / "moments").exists() else []:
            if d.is_dir() and not (d / "done.json").exists():
                shutil.rmtree(d, ignore_errors=True)
        # stdin stays a pipe: the recorder takes moment commands on it, and if this server dies it sees it close
        # and stops too
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=logf, stderr=logf, cwd=str(ROOT))
        self.last_error = ""
        log.info("recorder started: %s", " ".join(cmd))

    def stop(self) -> None:
        with self._mlock:  # the browser's page for a moment dies with it
            self.moments.done()
            self.moments.pending.clear()
        for t in self._threads:  # let a day being encoded finish (a few seconds at 720p)
            t.join(timeout=60)
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self.proc = None

    def recover(self) -> None:
        """Finish days a shutdown interrupted: frames moved aside but never encoded, pages never written. The
        encoding runs in the background (a long day's frames used to hold the game up while they were encoded)."""
        self._recovered = True
        out = self.run_dir()
        if not out.exists():
            return
        jobs = []
        for tmp in self.stranded_frames(out):
            day = int(DAY_FRAMES_DIR.match(tmp.name).group(1))  # (any number of digits: day 3106 was read as 310)
            if day and not (out / f"day-{day:03d}.mp4").exists() and any(tmp.glob("*.jpg")):
                jobs.append((day, tmp))
            else:
                shutil.rmtree(tmp, ignore_errors=True)
            if day and not (out / f"day-{day:03d}.md").exists():
                try:
                    self._write_stories(out, {day: self._story_inputs(day)})
                except Exception as e:
                    log.warning("recovering day %s: %s", day, e)
        if jobs:
            self._recovering = True
            t = threading.Thread(target=self._recover_days, args=(out, jobs), daemon=True)
            self._threads = [x for x in self._threads if x.is_alive()] + [t]
            t.start()

    def _recover_days(self, out: Path, jobs: List[Tuple[int, Path]]) -> None:
        with self._lock:
            self.encoding += 1
            try:
                for day, tmp in jobs:
                    self._encode(out, day, tmp)
            except Exception as e:
                self.last_error = f"recovering a recorded day failed: {e}"
                log.warning(self.last_error)
            finally:
                self.encoding -= 1
                self._recovering = False

    def watch(self) -> None:
        """Keep the recorder alive (and filming the right worlds). Cheap; called every in-game hour."""
        if not self._recovered:  # (before any pruning: frames a restart interrupted are finished, not thrown away)
            try:
                self.recover()
            except Exception as e:
                log.warning("recording recovery failed: %s", e)
        self.tend()
        if not self.settings["enabled"]:
            return
        if self.running() and self.proc_world != self.world_param():
            self.stop()
        if not self.running() and time.time() >= self._next_restart:
            self._next_restart = time.time() + 60
            if self.proc is not None:
                self.last_error = f"The recorder stopped (exit {self.proc.returncode}); restarting. See {self.dir / 'recorder.log'}"
                self.proc = None
            self.start()
        self._pump()

    def new_run(self) -> None:
        """A new game started: frames from the old one belong to nobody."""
        self.segment_start_ms = int(time.time() * 1000)
        with self._mlock:
            self.moments = Moments()
        if self.frames.exists():
            for p in self.frames.glob("*.jpg"):
                p.unlink(missing_ok=True)
            shutil.rmtree(self.frames / "moments", ignore_errors=True)

    # ------------------------------------------------------------ moments, filmed close up at live speed
    def on_event(self, world_id: str, ev: Any) -> None:
        """A world listener: every event passes through here, inside the tick, so it must stay cheap."""
        kind = getattr(ev, "kind", None) or (ev.get("kind") if isinstance(ev, dict) else None)
        imp = getattr(ev, "importance", None) if not isinstance(ev, dict) else ev.get("importance")
        if kind not in MOMENT_KINDS and kind not in ("birth", "convert") and int(imp or 0) < 4:
            return
        if not (self.settings["enabled"] and self.settings.get("moments")) or not self.running():
            return
        try:
            e = ev.to_dict() if hasattr(ev, "to_dict") else dict(ev)
            if not is_moment(e, first_birth=kind == "birth" and self._first_birth(world_id),
                             founder=kind == "convert" and self._founder(world_id, e.get("actor"))):
                return
            x, y = e.get("x"), e.get("y")
            if x is None or y is None:
                spot = self._busiest(world_id)
                if spot is None:
                    return
                x, y = spot
            with self._mlock:
                self.moments.offer({"world": world_id, "tick": int(e.get("tick") or 0), "seq": e.get("seq"),
                                    "kind": kind, "importance": int(imp or 0), "text": str(e.get("text") or ""),
                                    "x": float(x), "y": float(y)}, time.monotonic())
            self._pump()
        except Exception as err:  # never let a recording problem hurt the game
            log.warning("moment skipped: %s", err)

    def _world(self, world_id: str) -> Any:
        return self.rt.worlds.get(world_id)

    def _first_birth(self, world_id: str) -> bool:
        """Was this the first child ever born here? (Called right after the birth, so it is counted.)"""
        w = self._world(world_id)
        people = list(getattr(w, "agents", {}).values()) + list(getattr(w, "dead", {}).values())
        known = [a for a in people if hasattr(a, "parents")]  # (a remote world doesn't know who has parents)
        return bool(known) and sum(1 for a in known if a.parents) <= 1

    def _founder(self, world_id: str, actor: Optional[str]) -> bool:
        """One of the island's first chits, or the founder of a belief."""
        w = self._world(world_id)
        a = getattr(w, "agents", {}).get(actor or "")
        if a is not None and getattr(a, "generation", 1) == 0 and not getattr(a, "parents", ()):
            return True
        return any(b.get("founder") == actor for b in getattr(w, "beliefs", {}).values())

    def _busiest(self, world_id: str) -> Optional[Tuple[float, float]]:
        w = self._world(world_id)
        return busiest_spot([(a.x, a.y) for a in list(getattr(w, "agents", {}).values())])

    def _free_name(self, out: Path, m: Dict[str, Any]) -> str:
        """The queue numbers moments from 1 after a restart: step past clips already on disk."""
        name, n = m["name"], int(m["name"].rsplit("-", 1)[-1])
        while (out / f"{name}.mp4").exists() or (out / f"{name}.json").exists() or (self.frames / "moments" / name).exists():
            n += 1
            name = moment_name(m["day"], m["world"], m["kind"], n)
        return name

    def _pump(self) -> None:
        """Start the next queued moment when none is filming, give up on one the browser lost, and encode the
        ones it has finished. Called on every big event and from watch()."""
        now = time.monotonic()
        send = None
        with self._mlock:
            busy = self.moments.busy
            if busy and not self.running():
                self.moments.done()
            elif busy and now - busy["started"] > MOMENT_TIMEOUT_S + busy.get("seconds", MOMENT_SECONDS):
                self.last_error = f"a moment was never finished by the browser: {busy['name']}"
                if busy.get("dir"):
                    shutil.rmtree(busy["dir"], ignore_errors=True)
                self.moments.done()
            if self.moments.busy is None and self.running() and self.settings.get("moments"):
                send = self.moments.next(now)
            if send is not None:
                try:
                    send = self._dispatch(send)
                except Exception as e:
                    self.last_error = f"couldn't start filming a moment: {e}"
                    self.moments.done()
        self._collect_moments()

    def _dispatch(self, m: Dict[str, Any]) -> Dict[str, Any]:
        out = self.run_dir()
        m["name"] = self._free_name(out, m)
        d = self.frames / "moments" / m["name"]
        d.mkdir(parents=True, exist_ok=True)
        m.update(run=self.rt.run_id, dir=str(d), seconds=MOMENT_SECONDS, fps=MOMENT_FPS,
                 zoom=MOMENT_ZOOM + (0.3 if m.get("importance", 0) >= 5 else 0.0),
                 caption=m["text"][:CAPTION_MAX], clock=clock_of(m["tick"]),
                 world_name=getattr(self._world(m["world"]), "name", f"World {m['world']}"))
        (d / "moment.json").write_text(json.dumps({k: v for k, v in m.items() if k not in ("at", "started")}))
        cmd = {"cmd": "moment", "dir": str(d), "world": m["world"], "x": m["x"], "y": m["y"], "zoom": m["zoom"],
               "caption": m["caption"], "seconds": m["seconds"], "fps": m["fps"],
               "label": f"{m['world_name']} · Day {m['day']} · {m['clock']}"}
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(cmd) + "\n").encode())
        self.proc.stdin.flush()
        log.info("filming a moment: %s (%s)", m["name"], m["caption"])
        return m

    def _collect_moments(self) -> None:
        root = self.frames / "moments"
        if not root.exists():
            return
        for d in sorted(root.glob("moment-*")):
            if not (d / "done.json").exists() or str(d) in self._moment_jobs:
                continue
            with self._mlock:
                if self.moments.busy and self.moments.busy.get("dir") == str(d):
                    self.moments.done()
            self._moment_jobs.add(str(d))
            t = threading.Thread(target=self._finish_moment, args=(d,), daemon=True)
            self._threads = [x for x in self._threads if x.is_alive()] + [t]
            t.start()

    def _finish_moment(self, d: Path) -> None:
        from .story.recording import add_moment_line, moment_line
        from .tools.timelapse import find_ffmpeg

        with self._lock:
            self.encoding += 1
            try:
                m = json.loads((d / "moment.json").read_text())
                frames = sorted((p for p in d.glob("*.jpg") if p.stem.isdigit()), key=lambda p: int(p.stem))
                if len(frames) < 10:  # the page never showed the world: nothing worth keeping
                    self.last_error = f"moment {m.get('name')}: only {len(frames)} frames were filmed"
                    return
                out = self.dir / m["run"]
                out.mkdir(parents=True, exist_ok=True)
                lst = d / "frames.txt"
                lst.write_text(moment_concat(frames, int(m.get("fps") or MOMENT_FPS)))
                clip = out / f"{m['name']}.mp4"
                ffmpeg = find_ffmpeg() or "ffmpeg"
                r = subprocess.run(moment_cmd(ffmpeg, str(lst), str(clip), int(m.get("fps") or MOMENT_FPS),
                                              self.settings["aspect"]), capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    self.last_error = f"ffmpeg failed on {m['name']}: {r.stderr.strip()[-300:]}"
                    return
                span = (int(frames[-1].stem) - int(frames[0].stem)) / 1000
                info = {k: m.get(k) for k in ("name", "day", "world", "world_name", "kind", "importance", "tick",
                                              "clock", "seq", "x", "y", "caption", "fps")}
                info.update(clip=clip.name, frames=len(frames), seconds=round(span, 1))
                (out / f"{m['name']}.json").write_text(json.dumps(info, indent=2))
                self.last_clip = f"{out.name}/{clip.name}"
                page = out / f"day-{int(m['day']):03d}.md"
                if page.exists():  # the day's story was written before this moment finished
                    page.write_text(add_moment_line(page.read_text(), moment_line(info)))
            except Exception as e:
                self.last_error = f"moment {d.name} failed: {e}"
                log.warning(self.last_error)
            finally:
                shutil.rmtree(d, ignore_errors=True)
                self._moment_jobs.discard(str(d))
                self.encoding -= 1

    def moments_of(self, out: Path, day: Optional[int] = None) -> List[Dict[str, Any]]:
        """The moments filmed in a run (or on one day of it), in the order they happened."""
        found = []
        for p in out.glob(f"moment-{day:03d}-*.json" if day else "moment-*.json"):
            try:
                info = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(info, dict) and (out / str(info.get("clip", ""))).is_file():
                found.append(info)
        return sorted(found, key=lambda i: (int(i.get("tick") or 0), str(i.get("name"))))

    # ------------------------------------------------------------ one clip + story per day
    def day_ended(self, day: int) -> None:
        """Called once per game when `day` has just finished (right after its chronicle pages are written)."""
        if not self.settings["enabled"] or day < 1:
            return
        frames = frames_between(self.frames, 0, 1 << 62) if self.frames.exists() else []
        out = self.run_dir()
        out.mkdir(parents=True, exist_ok=True)
        self._write_run_info(out)
        stories = {d: self._story_inputs(d) for d in (day - 1, day) if d >= 1}
        week = day // 7 if day % 7 == 0 else 0
        # the day after a week ends, its saga has been told (narrated): write the week page again
        retell = (day - 1) // 7 if day % 7 == 1 and day > 7 else 0
        t = threading.Thread(target=self._finish_day, args=(out, day, frames, stories, week, retell))
        self._threads = [x for x in self._threads if x.is_alive()] + [t]
        t.start()

    def _write_run_info(self, out: Path) -> None:
        info = out / "run.json"
        if info.exists():
            return
        worlds = [{"id": w.id, "name": w.name, "label": getattr(w, "label", ""),
                   "brain": self.rt.brain_summary().get(w.id, {}).get("label", "")} for w in self.rt.worlds.values()]
        info.write_text(json.dumps({"run": self.rt.run_id, "mode": self.rt.mode, "started": time.time(),
                                    "worlds": worlds}, indent=2))

    def _story_inputs(self, day: int) -> List[Dict[str, Any]]:
        from .story.recording import how_they_did_it

        worlds = []
        for w in self.rt.worlds.values():
            evs = self.rt.store.events(w.id, since_tick=(day - 1) * TICKS_PER_DAY, until_tick=day * TICKS_PER_DAY,
                                       min_importance=1, limit=20000, epoch=w.timeline() if hasattr(w, "timeline") else w.epoch)
            page = self.rt.data_dir / "stories" / w.id / f"day-{day:03d}.md"
            worlds.append({"id": w.id, "name": w.name, "label": getattr(w, "label", ""),
                           "brain": self.rt.brain_summary().get(w.id, {}).get("label", ""),
                           "lines": how_they_did_it(evs, self.rt.names(w)),
                           "chronicle": page.read_text() if page.exists() else ""})
        return worlds

    def _write_stories(self, out: Path, stories: Dict[int, List[dict]], coming: Optional[int] = None) -> None:
        from .story.recording import day_story

        for d, worlds in stories.items():
            c = out / f"day-{d:03d}.mp4"
            (out / f"day-{d:03d}.md").write_text(day_story(d, worlds, c.name if c.exists() or d == coming else None,
                                                           self.moments_of(out, d)))

    def _encode(self, out: Path, day: int, tmp: Path) -> None:
        from .tools.timelapse import find_ffmpeg

        clip = out / f"day-{day:03d}.mp4"
        ffmpeg = find_ffmpeg() or "ffmpeg"
        frames = sorted(tmp.glob("f-*.jpg"))
        if len(frames) > MAX_DAY_FRAMES:  # (frames set aside by an older version, finished after a restart)
            for i, p in enumerate(thin(frames, MAX_DAY_FRAMES), 1):
                p.replace(tmp / f"f-{i:06d}.jpg")  # ffmpeg wants them numbered without gaps (i never passes p's own)
            frames = sorted(tmp.glob("f-*.jpg"))
        fps = day_fps(len(frames), int(self.settings.get("fps") or 0), self.settings.get("day_seconds") or 18)
        try:
            r = subprocess.run(encode_cmd(ffmpeg, str(tmp / "f-%06d.jpg"), str(clip), fps,
                                          self.settings["aspect"], DAY_CRF), capture_output=True, text=True, timeout=300)
            failed = "" if r.returncode == 0 else r.stderr.strip()[-300:] or f"exit {r.returncode}"
        except (OSError, subprocess.SubprocessError) as e:  # ffmpeg missing, or it ran out of time
            failed = str(e)[-300:] or type(e).__name__
        if failed:
            self.last_error = f"ffmpeg failed on day {day}: {failed}"
            clip.unlink(missing_ok=True)  # (a half-written clip is not a clip)
        else:
            self.last_clip = f"{out.name}/{clip.name}"
        # The frames go either way. Kept after a failure they were never encoded and never pruned: the day's story
        # (written first) is the evidence, the frames are only scratch.
        shutil.rmtree(tmp, ignore_errors=True)

    def _finish_day(self, out: Path, day: int, frames: List[Path], stories: Dict[int, List[dict]], week: int,
                    retell: int = 0) -> None:
        with self._lock:
            self.encoding += 1
            try:
                # stories first: a shutdown mid-encode used to lose the day's page and the week's
                # (today's page now, and yesterday's again: its chronicle has been told by now)
                self._write_stories(out, stories, coming=day if frames else None)
                if retell:
                    self._week_page(out, retell)
                if frames:
                    tmp = out / f".day-{day:03d}-frames"
                    tmp.mkdir(exist_ok=True)
                    moved = 0
                    for p in thin(frames, MAX_DAY_FRAMES):
                        try:
                            p.replace(tmp / f"f-{moved + 1:06d}.jpg")
                            moved += 1
                        except OSError:  # (thinned away between the day ending and this thread starting)
                            pass
                    self._encode(out, day, tmp)
                if week:
                    self._finish_week(out, week)
            except Exception as e:  # never let a recording problem hurt the game
                self.last_error = f"recording day {day} failed: {e}"
                log.warning(self.last_error)
            finally:
                self.encoding -= 1

    def _finish_week(self, out: Path, week: int) -> None:
        from .tools.timelapse import find_ffmpeg

        days = [out / f"day-{d:03d}.mp4" for d in range(week * 7 - 6, week * 7 + 1)]
        days = [p for p in days if p.exists()]
        self._week_page(out, week)  # the page first, like the days
        if days:
            ffmpeg = find_ffmpeg() or "ffmpeg"
            # seven ~18 s days would make a two-minute reel: play them faster so the week stays under a minute
            lengths = [clip_seconds(p, ffmpeg) or float(self.settings.get("day_seconds") or 18) for p in days]
            speed = week_speed(lengths, float(self.settings.get("week_seconds") or 56))
            r = subprocess.run(week_cmd(ffmpeg, days, str(out / f"week-{week:02d}.mp4"), speed, self.settings["aspect"]),
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                self.last_error = f"ffmpeg failed on week {week}: {r.stderr.strip()[-300:]}"
        self._week_page(out, week)

    def _week_page(self, out: Path, week: int) -> None:
        parts = [f"# Week {week}", ""]
        if (out / f"week-{week:02d}.mp4").exists():
            parts += [f"[▶ Watch week {week}](week-{week:02d}.mp4)", ""]
        for w in self.rt.worlds.values():
            saga = self.rt.data_dir / "stories" / w.id / f"week-{week:02d}.md"
            if saga.exists():
                parts += [saga.read_text().strip(), ""]
        (out / f"week-{week:02d}.md").write_text("\n".join(parts).rstrip() + "\n")

    def director_cut(self, run: str, week: int) -> Dict[str, Any]:
        """Number a week's best moments for a post (cut-WW-NN-<moment>.mp4, in story order), write the shot list
        (cut-WW.md) and join them into one live-speed video (cut-WW.mp4)."""
        from .tools.timelapse import find_ffmpeg

        out = self.dir / run
        if not SAFE_NAME.match(run) or run == "frames" or not out.is_dir():
            return {"error": "no such recording"}
        plan = cut_plan(self.moments_of(out), int(week))
        if not plan:
            return {"week": week, "clips": [], "error": "no moments were filmed that week"}
        for old in out.glob(f"cut-{int(week):02d}-*.mp4"):  # a remake: the last cut's clips go first
            old.unlink()
        for c in plan:
            shutil.copyfile(out / c["clip"], out / c["file"])
        video, err = f"cut-{int(week):02d}.mp4", None
        lst = out / f"cut-{int(week):02d}.txt"
        lst.write_text("".join(f"file '{(out / c['file']).as_posix()}'\n" for c in plan))
        ffmpeg = find_ffmpeg() or "ffmpeg"
        try:
            r = subprocess.run(concat_cmd(ffmpeg, str(lst), str(out / video)), capture_output=True, text=True, timeout=300)
            if r.returncode != 0:  # clips of different sizes: re-encode them to one
                r = subprocess.run(week_cmd(ffmpeg, [out / c["file"] for c in plan], str(out / video), 1.0,
                                            self.settings["aspect"], MOMENT_FPS), capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                err, video = f"ffmpeg: {r.stderr.strip()[-200:]}", None
        except (OSError, subprocess.SubprocessError) as e:
            err, video = f"ffmpeg: {e}", None
        finally:
            lst.unlink(missing_ok=True)
        (out / f"cut-{int(week):02d}.md").write_text(cut_markdown(int(week), plan, video))
        return {"week": week, "clips": plan, "story": f"cut-{int(week):02d}.md", "video": video, "error": err}

    # ------------------------------------------------------------ what's been recorded
    def listing(self) -> List[Dict[str, Any]]:
        runs = []
        if not self.dir.exists():
            return runs
        for d in self.dir.iterdir():
            if not d.is_dir() or d.name == "frames" or not SAFE_NAME.match(d.name):
                continue
            try:
                info = json.loads((d / "run.json").read_text())
            except (OSError, ValueError):
                info = {"run": d.name}
            days = sorted(int(p.stem[4:]) for p in d.glob("day-*.md") if p.stem[4:].isdigit())
            weeks = sorted(int(p.stem[5:]) for p in d.glob("week-*.md") if p.stem[5:].isdigit())
            info["current"] = d.name == self.rt.run_id
            info["days"] = [{"day": n, "story": f"day-{n:03d}.md",
                             "clip": f"day-{n:03d}.mp4" if (d / f"day-{n:03d}.mp4").exists() else None} for n in days]
            info["weeks"] = [{"week": n, "story": f"week-{n:02d}.md",
                              "clip": f"week-{n:02d}.mp4" if (d / f"week-{n:02d}.mp4").exists() else None} for n in weeks]
            info["moments"] = [{k: m.get(k) for k in ("name", "clip", "day", "world", "world_name", "kind", "clock",
                                                      "caption", "seconds", "seq")} for m in self.moments_of(d)]
            info["cuts"] = [{"week": int(p.stem[4:]), "story": p.name,
                             "video": f"{p.stem}.mp4" if (d / f"{p.stem}.mp4").exists() else None}
                            for p in sorted(d.glob("cut-*.md")) if p.stem[4:].isdigit()]
            runs.append(info)
        return sorted(runs, key=lambda r: (not r["current"], -(r.get("started") or 0)))

    def file(self, run: str, name: str) -> Optional[Path]:
        if not SAFE_NAME.match(run) or not SAFE_NAME.match(name) or run == "frames":
            return None
        p = self.dir / run / name
        return p if p.is_file() else None
