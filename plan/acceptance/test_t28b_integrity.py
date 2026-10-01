from fastapi.testclient import TestClient


def test_god_mode_marks_sandbox_forks_timelines_and_is_refused_in_experiments(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        rt = appmod.rt
        w = rt.worlds["A"]
        a = next(iter(w.agents.values()))
        assert c.post("/api/worlds/A/god", json={"action": "bless", "x": a.x, "y": a.y}).status_code == 200
        assert c.get("/api/run").json()["sandbox_modified"] is True
        sp = c.post("/api/savepoints", json={"name": "x"}).json()
        epoch = appmod.rt.worlds["A"].epoch
        c.post(f"/api/savepoints/{sp['id']}/restore")
        assert appmod.rt.worlds["A"].epoch != epoch
        c.post("/api/reset", json={"seed": 2, "contract": "experiment"})
        assert c.post("/api/worlds/A/god", json={"action": "bless", "x": 1, "y": 1}).status_code == 409
        assert c.post("/api/savepoints", json={"name": "y"}).status_code in (200, 409)
