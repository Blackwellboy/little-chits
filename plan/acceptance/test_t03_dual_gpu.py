import json
import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_preset_file():
    d = json.loads((ROOT / "configs" / "dual-gpu.json").read_text())
    ids = {b["id"]: b for b in d["brains"]}
    assert ids["rtx5090"]["base_url"] == "http://127.0.0.1:18090/v1"
    assert ids["rtx3090"]["base_url"] == "http://127.0.0.1:18080/v1"
    assert d["assign"] == {"A": "rtx5090", "B": "rtx3090"}


def test_merge_preset(tmp_path):
    from chits.brain.mind import Mind

    m = Mind(tmp_path / "brains.json")
    m.upsert({"id": "rtx5090", "label": "old", "base_url": "http://x/v1"})
    m.merge_preset(ROOT / "configs" / "dual-gpu.json")
    assert m.brains["rtx5090"].cfg.base_url == "http://127.0.0.1:18090/v1"
    assert m.brains["rtx5090"].cfg.label == "RTX 5090"
    assert "rtx3090" in m.brains
    assert m.world_brain["A"] == "rtx5090" and m.world_brain["B"] == "rtx3090"
    saved = json.loads((tmp_path / "brains.json").read_text())
    assert saved["assign"]["B"] == "rtx3090"


def test_runtime_applies_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_BRAINS_PRESET", str(ROOT / "configs" / "dual-gpu.json"))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.delenv("CHITS_BRAINS", raising=False)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    assert all(a.brain == "rtx5090" for a in rt.worlds["A"].agents.values())
    assert all(a.brain == "rtx3090" for a in rt.worlds["B"].agents.values())


def test_scripts_and_make():
    mk = (ROOT / "Makefile").read_text()
    assert "\ndual:" in mk and "\ndual-doctor:" in mk
    s = ROOT / "scripts" / "start_dual.sh"
    assert s.exists() and os.stat(s).st_mode & stat.S_IXUSR
    txt = s.read_text()
    assert "18090" in txt and "18080" in txt
    assert "Two GPUs" in (ROOT / "README.md").read_text()
