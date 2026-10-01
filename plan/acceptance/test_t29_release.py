from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_cli_parser():
    from chits.cli import build_parser

    a = build_parser().parse_args(["--port", "8123", "--mode", "single", "--no-browser", "--speed", "5", "--model", "http://x:1/v1"])
    assert a.port == 8123 and a.mode == "single" and a.no_browser and a.speed == 5 and a.model == "http://x:1/v1"
    d = build_parser().parse_args([])
    assert d.port == 8000 and d.host == "127.0.0.1" and not d.no_browser
    py = (ROOT / "pyproject.toml").read_text()
    assert "[project.scripts]" in py and 'little-chits = "chits.cli:main"' in py


def test_packaging_files():
    df = (ROOT / "Dockerfile").read_text()
    assert "EXPOSE 8000" in df and "web/dist" in df
    dc = (ROOT / "docker-compose.yml").read_text()
    assert "network_mode: host" in dc
    mk = (ROOT / "Makefile").read_text()
    assert "\nplay:" in mk and "\nplay-single:" in mk
    assert "Play in 2 minutes" in (ROOT / "README.md").read_text()


def test_health_reports_first_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_SCAN_PORTS", "9")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.delenv("CHITS_BRAINS", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["first_run"] is True and h["autodetected"] == []
        assert h["mode"] in ("versus", "single", "culture")
        assert set(h["brains"]) == {"A", "B"}
