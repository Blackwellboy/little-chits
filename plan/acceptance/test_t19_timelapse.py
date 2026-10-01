from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ffmpeg_cmd():
    from chits.tools.timelapse import build_ffmpeg_cmd, find_ffmpeg

    f = find_ffmpeg()
    assert f is None or isinstance(f, str)
    cmd = build_ffmpeg_cmd(Path("/tmp/fr"), Path("/tmp/out.mp4"), fps=24, aspect="9:16")
    assert cmd[1:5] == ["-y", "-framerate", "24", "-i"]
    assert cmd[5] == "/tmp/fr/frame-%05d.png"
    vf = cmd[cmd.index("-vf") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in vf and "pad=1080:1920" in vf
    assert cmd[-1] == "/tmp/out.mp4" and "libx264" in cmd and "yuv420p" in cmd
    assert "pad=1920:1080" in build_ffmpeg_cmd(Path("a"), Path("b.mp4"))[build_ffmpeg_cmd(Path("a"), Path("b.mp4")).index("-vf") + 1]
    assert "1080:1080" in " ".join(build_ffmpeg_cmd(Path("a"), Path("b.mp4"), aspect="1:1"))


def test_ffmpeg_env_override(monkeypatch, tmp_path):
    from chits.tools import timelapse

    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("FFMPEG", str(fake))
    assert timelapse.find_ffmpeg() == str(fake)


def test_capture_script_and_docs():
    s = (ROOT / "scripts" / "capture.mjs").read_text()
    assert "record=1" in s and "playwright" in s and "frame-" in s
    assert "\nclip:" in (ROOT / "Makefile").read_text()
    assert "Making clips for X" in (ROOT / "README.md").read_text()
