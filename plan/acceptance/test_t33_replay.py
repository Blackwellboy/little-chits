import base64
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_keyframes_api_and_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        rt = appmod.rt
        w = rt.worlds["A"]
        for t in range(1, 241):
            w.step(rt.mind.hook)
            if t % 24 == 0:
                rt.record_keyframe(w)
        rt._flush_events(w)
        kf = rt.store.keyframes("A", 0, 10_000)
        assert len(kf) == 10 and kf[0]["t"] == 24
        assert all(len(row) == 4 for row in kf[0]["a"])
        assert kf[-1]["s"] is not None  # tick 240 carries the full structure list
        r = c.get("/api/worlds/A/replay?from=0&to=100").json()
        assert r["meta"]["id"] == "A" and [k["t"] for k in r["keyframes"]] == [24, 48, 72, 96]
        b = c.get("/api/replay/export?days=1").json()
        assert b["version"] == 1 and "A" in b["worlds"]
        wa = b["worlds"]["A"]
        assert wa["terrain"]["size"] == w.w and len(base64.b64decode(wa["terrain"]["tiles"])) == w.w * w.h
        assert wa["keyframes"] and set(wa["names"]) >= set(w.agents)


def test_viewer_is_built():
    assert (ROOT / "web" / "replay.html").exists()
    cfg = next((ROOT / "web").glob("vite.config.*")).read_text()
    assert "replay" in cfg
