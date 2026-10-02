"""Updating a brain changes only what was sent. The API filled every field left out with its default, so a request
that set a brain's model and slots also reset the live World B brain's prompt_style from "cascade" to "full"."""


def test_updating_a_brain_keeps_the_settings_not_sent(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    def cfg(c, bid):
        return next(x for x in c.get("/api/brains").json()["brains"] if x["config"]["id"] == bid)["config"]

    with TestClient(app) as c:
        new = {"id": "m3", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "cascade", "escalate_below": 0.35,
               "max_concurrency": 8, "focus": False}
        assert c.post("/api/brains", json=new).status_code == 200
        assert c.post("/api/brains", json={"id": "m3", "base_url": "http://127.0.0.1:9/v1", "model": "smaller.gguf",
                                           "max_concurrency": 16}).status_code == 200
        got = cfg(c, "m3")
        assert got["model"] == "smaller.gguf" and got["max_concurrency"] == 16
        assert got["prompt_style"] == "cascade" and got["escalate_below"] == 0.35 and got["focus"] is False
        # a new brain still gets the defaults for what it leaves out
        assert c.post("/api/brains", json={"id": "m4", "base_url": "http://127.0.0.1:9/v1"}).status_code == 200
        assert cfg(c, "m4")["max_concurrency"] == 6


def test_an_update_by_label_keeps_the_settings_not_sent(tmp_path, monkeypatch):
    # no id but a label naming an existing brain: the id is derived first, so it's an update, not defaults (Codex, #42)
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        new = {"id": "gpu-b", "label": "GPU B", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "cascade"}
        assert c.post("/api/brains", json=new).status_code == 200
        assert c.post("/api/brains", json={"label": "GPU B", "base_url": "http://127.0.0.1:9/v1",
                                           "max_concurrency": 16}).status_code == 200
        got = next(x for x in c.get("/api/brains").json()["brains"] if x["config"]["id"] == "gpu-b")["config"]
        assert got["max_concurrency"] == 16 and got["prompt_style"] == "cascade"
