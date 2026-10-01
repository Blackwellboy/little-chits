import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from chits.brain.llm import BrainConfig

ROOT = Path(__file__).resolve().parents[2]


async def test_model_vs_instinct(fake_llm_url, tmp_path):
    from chits.tools.experiment import run_experiment

    out = tmp_path / "exp"
    s = await run_experiment({"A": BrainConfig(id="fake", label="Fake 7B", base_url=fake_llm_url, max_concurrency=8), "B": None},
                             days=0.5, out_dir=out, chits=6, seed=42, max_wall_s=120)
    assert s["ticks"] == 120 and s["seed"] == 42
    a, b = s["worlds"]["A"], s["worlds"]["B"]
    assert a["label"] == "Fake 7B" and a["culture"] == "direct" and b["culture"] == "stigmergy"
    assert a["model_plans"] > 0 and a["decisions"] > 0 and a["brain_stats"]["ok"] > 0
    assert b["model_plans"] == 0 and b["brain_stats"] == {}
    for f in ("summary.json", "summary.md", "card.svg", "events_A.jsonl", "events_B.jsonl"):
        assert (out / f).exists(), f
    assert json.loads((out / "summary.json").read_text())["worlds"]["A"]["label"] == "Fake 7B"
    md = (out / "summary.md").read_text()
    assert "Fake 7B" in md and "Scoreboard" in md
    ET.fromstring((out / "card.svg").read_text())
    for line in (out / "events_A.jsonl").read_text().splitlines()[:5]:
        assert {"seq", "tick", "kind", "text"} <= set(json.loads(line))


def test_cli(tmp_path):
    out = tmp_path / "cli"
    p = subprocess.run([sys.executable, "-m", "chits.tools.experiment", "--a", "instinct", "--b", "instinct", "--days", "0.25",
                        "--chits", "4", "--out", str(out)], cwd=ROOT / "server", capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (out / "summary.md").exists()
    assert "\nexperiment:" in (ROOT / "Makefile").read_text()
