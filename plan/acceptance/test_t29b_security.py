from fastapi.testclient import TestClient


def test_token_guards_mutations(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_TOKEN", "s3cret")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.post("/api/control", json={"speed": 2}).status_code == 401
        assert c.post("/api/control", json={"speed": 2}, headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.post("/api/control", json={"speed": 2}, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_public_bind_needs_a_token():
    from chits.cli import check_bind

    assert check_bind("127.0.0.1", token=None, insecure=False) is None
    assert check_bind("0.0.0.0", token=None, insecure=False)  # an error message
    assert check_bind("0.0.0.0", token="abc", insecure=False) is None
    assert check_bind("0.0.0.0", token=None, insecure=True) is None
