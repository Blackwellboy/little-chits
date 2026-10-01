# T19 · Timelapse and clip export (MP4 for X)

**Why:** one command should turn an evening of civilisation into a 30-second vertical clip.

## Build
1. **`scripts/capture.mjs`** is a Node script using Playwright. Load it via `import("playwright")`, and print
   a clear install hint if it's missing.
   - Arguments: `--url`, `--out <dir>`, `--frames N`, `--interval-ms`, `--aspect 16:9|9:16|1:1`,
     `--width W`, `--speed S`, `--world A|B|split`.
   - Open `{url}/?record=1&aspect=…&world=…&speed=…` in Chromium, at a viewport of W×H from the aspect
     (the default 1080 px on the short side).
   - Wait 4 s, then save `frame-00001.png`… every interval.
   - Honour `PLAYWRIGHT_CHROMIUM` or `executablePath` if it's set.
2. **`server/chits/tools/timelapse.py`**:
   ```python
   def find_ffmpeg() -> str | None
   def build_ffmpeg_cmd(frames_dir: Path, out: Path, fps: int = 30, aspect: str = "16:9") -> list[str]
   def main(argv=None) -> int
   ```
   - **`find_ffmpeg`** checks, in order: `$FFMPEG`, `ffmpeg` on PATH, then `/opt/pw-browsers/ffmpeg-*/ffmpeg-linux`,
     then `imageio_ffmpeg.get_ffmpeg_exe()` if it's importable. Returns the path or None.
   - **`build_ffmpeg_cmd`** returns
     `[ffmpeg, "-y", "-framerate", str(fps), "-i", str(frames_dir/"frame-%05d.png"), "-vf", <scale+pad to target>, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]`,
     where `ffmpeg` is `find_ffmpeg() or "ffmpeg"`. The targets are 1920x1080 (16:9), 1080x1920 (9:16) and
     1080x1080 (1:1). Use
     `scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2:color=black`.
   - **CLI** `python -m chits.tools.timelapse --url http://127.0.0.1:8000 --seconds 30 --aspect 9:16 --speed 25 --out clip.mp4`:
     - capture `seconds*fps/…` frames with a sensible interval (default 1 frame per 250 ms of real time)
     - into a temp dir, via `node scripts/capture.mjs`
     - run ffmpeg
     - print the output path
     - return non-zero with a helpful message if node, playwright or ffmpeg is missing
3. **Makefile:** `clip:` target, e.g. `make clip ARGS="--aspect 9:16 --seconds 30"`.
4. README section "Making clips for X", covering record mode URLs, `make clip`, `make experiment` and the
   thread/card endpoints.

## Done when
`python scripts/plan.py verify T19` passes. 🖐 Then `make clip` produces a playable MP4.
