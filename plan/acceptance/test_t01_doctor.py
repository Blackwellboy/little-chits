import subprocess
import sys
from pathlib import Path

from chits.brain.llm import BrainConfig

ROOT = Path(__file__).resolve().parents[2]


async def test_doctor_ok_against_fake(fake_llm_url):
    from chits.tools.doctor import check_brain

    r = await check_brain(BrainConfig(id="fake", base_url=fake_llm_url, max_concurrency=4), samples=3)
    assert set(r) >= {"ok", "model", "samples", "valid", "valid_rate", "latency_ms", "tok_s", "est_chits_1x", "error", "example"}
    assert r["ok"] is True and r["error"] == ""
    assert r["model"] == "fake-chit-7b"
    assert r["samples"] == 3 and 1 <= r["valid"] <= 3
    assert abs(r["valid_rate"] - r["valid"] / 3) < 1e-9
    assert r["latency_ms"] > 0 and r["est_chits_1x"] > 0
    assert r["est_chits_1x"] == int(4 * 15000 / max(1, r["latency_ms"]))
    assert r["example"]["steps"]


async def test_doctor_reports_dead_endpoint(dead_url):
    from chits.tools.doctor import check_brain

    r = await check_brain(BrainConfig(id="dead", base_url=dead_url, timeout=2), samples=2)
    assert r["ok"] is False
    assert r["error"]
    assert r["est_chits_1x"] == 0 and r["valid"] == 0


def test_doctor_cli_exit_codes(fake_llm_url, dead_url):
    env_py = [sys.executable, "-m", "chits.tools.doctor"]
    ok = subprocess.run(env_py + ["--url", fake_llm_url, "--samples", "2"], cwd=ROOT / "server", capture_output=True, text=True, timeout=120)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "OK" in ok.stdout
    bad = subprocess.run(env_py + ["--url", dead_url, "--samples", "1"], cwd=ROOT / "server", capture_output=True, text=True, timeout=120)
    assert bad.returncode == 1


def test_makefile_has_doctor():
    assert "\ndoctor:" in (ROOT / "Makefile").read_text()
