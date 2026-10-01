"""Turn a stretch of Little Chits into an MP4 clip for X (a timelapse from record mode).

    python -m chits.tools.timelapse --url http://127.0.0.1:8000 --seconds 30 --aspect 9:16 --speed 25 --out clip.mp4

Needs node + Playwright (for capturing frames) and ffmpeg (for encoding).
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[3]
TARGETS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}


def find_ffmpeg() -> Optional[str]:
    env = os.environ.get("FFMPEG")
    if env and Path(env).exists():
        return env
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    for p in sorted(glob.glob("/opt/pw-browsers/ffmpeg-*/ffmpeg-linux")):
        return p
    try:
        import imageio_ffmpeg  # optional

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def build_ffmpeg_cmd(frames_dir: Path, out: Path, fps: int = 30, aspect: str = "16:9") -> List[str]:
    w, h = TARGETS.get(aspect, TARGETS["16:9"])
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    return [find_ffmpeg() or "ffmpeg", "-y", "-framerate", str(fps), "-i", str(Path(frames_dir) / "frame-%05d.png"),
            "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--seconds", type=float, default=30, help="length of the finished clip")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--interval-ms", type=int, default=250, help="real time between captured frames")
    ap.add_argument("--aspect", default="9:16", choices=list(TARGETS))
    ap.add_argument("--speed", type=int, default=25, help="game speed while recording")
    ap.add_argument("--world", default="A", choices=["A", "B", "split"])
    ap.add_argument("--out", default="")
    ap.add_argument("--keep-frames", action="store_true")
    args = ap.parse_args(argv)

    node = shutil.which("node")
    if not node:
        print("node isn't installed. Install Node.js 18+ (https://nodejs.org), then try again.", file=sys.stderr)
        return 2
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("ffmpeg isn't installed. On Ubuntu/WSL:  sudo apt install ffmpeg   (or: pip install imageio-ffmpeg)",
              file=sys.stderr)
        return 2
    out = Path(args.out or ROOT / "data" / "clips" / f"clip-{args.aspect.replace(':', 'x')}.mp4").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(args.seconds * args.fps))
    tmp = Path(tempfile.mkdtemp(prefix="chits-frames-"))
    print(f"Recording {frames} frames (about {frames * args.interval_ms / 60000:.1f} min of real time)…", flush=True)
    cap = subprocess.run([node, str(ROOT / "scripts" / "capture.mjs"), "--url", args.url, "--out", str(tmp),
                          "--frames", str(frames), "--interval-ms", str(args.interval_ms), "--aspect", args.aspect,
                          "--speed", str(args.speed), "--world", args.world])
    if cap.returncode != 0:
        print("Capturing frames failed (see above). Is Little Chits running at " + args.url + "?", file=sys.stderr)
        return cap.returncode or 1
    enc = subprocess.run(build_ffmpeg_cmd(tmp, out, args.fps, args.aspect))
    if not args.keep_frames:
        shutil.rmtree(tmp, ignore_errors=True)
    if enc.returncode != 0:
        print("ffmpeg couldn't encode the clip (it needs libx264: sudo apt install ffmpeg).", file=sys.stderr)
        return enc.returncode
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
