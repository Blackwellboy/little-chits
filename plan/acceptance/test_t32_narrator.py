from fastapi.testclient import TestClient


def test_narrator_config_and_saga(tmp_path, monkeypatch, fake_llm_url):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "5")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        rt = appmod.rt
        assert c.post("/api/brains", json={"id": "story", "base_url": fake_llm_url}).status_code == 200
        assert c.post("/api/narrator", json={"brain": "nope"}).status_code == 404
        assert c.post("/api/narrator", json={"brain": "story"}).status_code == 200
        assert c.get("/api/brains").json()["narrator"] == "story"
        w = rt.worlds["A"]
        assert rt.narrator_brain(w).id == "story"  # world A itself is on instinct
        c.post("/api/narrator", json={"brain": ""})
        assert rt.narrator_brain(w) is None
        for _ in range(240 * 7):
            w.step(rt.mind.hook)
        rt._flush_events(w)
        p = rt.write_saga(w, 1)
        assert p.name == "week-01.md" and p.read_text().startswith("# World A — Week 1")
        r = c.get("/api/worlds/A/sagas/1")
        assert r.status_code == 200 and r.json()["markdown"].startswith("# World A — Week 1")
        assert c.get("/api/worlds/A/sagas/9").status_code == 404
        assert 1 in [s["week"] if isinstance(s, dict) else s for s in c.get("/api/worlds/A/sagas").json()]
