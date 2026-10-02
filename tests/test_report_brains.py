"""The desktop launcher's "which model is each world thinking with" lines (scripts/report_brains.py). It used to be a
program inside a single-quoted bash string, where speed['text'] closed the quotes: the first time a model was flagged
slow, the report crashed with "NameError: name 'text' is not defined" and said nothing about World B."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "report_brains.py"

BRAINS = {
    "assign": {"A": "none", "B": "rtx3090", "C": "rtx5090"},
    "brains": [
        {"config": {"id": "rtx3090", "base_url": "http://127.0.0.1:18192/v1", "model": "m3"}, "stats": {},
         "healthy": True, "speed": {"level": "slow", "text": "Too slow for 85 chits: keeps up with about 16."}},
        {"config": {"id": "rtx5090", "base_url": "http://127.0.0.1:18191/v1", "model": "m5"}, "stats": {},
         "healthy": False, "speed": {}},
    ],
}


def run(d, models=""):
    r = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(d), capture_output=True, text=True,
                       env={"MODELS": models}, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def test_each_world_gets_a_line_and_a_slow_model_says_why():
    out = run(BRAINS, "18192 3090 /x.log\n18191 5090 /y.log")
    assert out == [
        "@warn wA World A has no model, so it runs on instinct (pick one in the game: Brains).",
        "@warn wB World B thinks with m3 on the 3090. Too slow for 85 chits: keeps up with about 16.",
        "@warn wC World C should use m5 on the 5090, but it isn't answering yet.",
    ]


def test_a_healthy_model_at_speed_is_ok():
    d = json.loads(json.dumps(BRAINS))
    d["brains"][0]["speed"] = {"level": "fast", "text": "Fast enough."}
    assert "@ok wB World B thinks with m3." in run(d)


def test_the_launcher_runs_the_script_not_an_inline_program():
    sh = (SCRIPT.parent / "desktop.sh").read_text()
    assert "scripts/report_brains.py" in sh and "speed['text']" not in sh
