import json
import subprocess
import sys
from pathlib import Path

from chits.brain.llm import BrainConfig

ROOT = Path(__file__).resolve().parents[2]


def test_scenes_deterministic():
    from chits.tools.bench import bench_scenes

    a = bench_scenes(4, seed=5)
    b = bench_scenes(4, seed=5)
    assert len(a) == 4 and a == b
    assert all(m[0]["role"] == "system" and m[1]["role"] == "user" for m in a)


async def test_bench_scores(fake_llm_url, dead_url):
    from chits.tools.bench import bench

    r = await bench([BrainConfig(id="fake", label="Fake", base_url=fake_llm_url),
                     BrainConfig(id="dead", base_url=dead_url, timeout=2)], scenes=4)
    assert r["scenes"] == 4
    f, d = r["results"]["fake"], r["results"]["dead"]
    for k in ("label", "model", "valid_rate", "mean_steps", "verb_diversity", "experiment_rate", "social_rate",
              "latency_ms", "tok_s", "score", "errors"):
        assert k in f
    assert 0 < f["valid_rate"] <= 1 and f["mean_steps"] > 0 and f["verb_diversity"] >= 1
    exp = 100 * (0.45 * f["valid_rate"] + 0.15 * min(1, f["mean_steps"] / 4) + 0.15 * min(1, f["verb_diversity"] / 10)
                 + 0.15 * f["experiment_rate"] + 0.10 * f["social_rate"])
    assert abs(f["score"] - round(exp, 1)) < 0.11
    assert d["valid_rate"] == 0 and d["score"] == 0 and d["errors"] == 4


def test_bench_cli(fake_llm_url, tmp_path):
    out = tmp_path / "b.json"
    p = subprocess.run([sys.executable, "-m", "chits.tools.bench", "--url", fake_llm_url, "--scenes", "3", "--out", str(out)],
                       cwd=ROOT / "server", capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr
    d = json.loads(out.read_text())
    assert len(d["results"]) == 1
    assert "\nbench:" in (ROOT / "Makefile").read_text()
