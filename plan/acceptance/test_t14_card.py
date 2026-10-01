import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from chits.story.card import scoreboard_svg

WORLDS = [
    {"id": "A", "name": "World A", "brain": "Qwen <27B> & friends", "culture": "direct", "day": 9,
     "stats": {"population": 21, "discoveries": 15, "structures": 30}},
    {"id": "B", "name": "World B", "brain": "RTX 3090", "culture": "stigmergy", "day": 9,
     "stats": {"population": 17, "discoveries": 11, "structures": 22}},
]


def test_svg_valid_and_complete():
    svg = scoreboard_svg(WORLDS, {"kind": "first", "text": 'Pip named the axe "Chopper" & shared it ' + "very " * 40})
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and root.get("width") == "1200" and root.get("height") == "675"
    text = " ".join(t for t in root.itertext())
    assert "Qwen <27B> & friends" in text and "RTX 3090" in text
    assert "21" in text and "15" in text and "17" in text and "11" in text
    assert "Day 9" in text and "Chopper" in text and "…" in text
    assert "#ffb86b" in svg.lower() and "#7dd3fc" in svg.lower()
    assert svg.count("<circle") >= 4


def test_single_world_and_no_moment():
    ET.fromstring(scoreboard_svg(WORLDS[:1], None))


def test_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        r = c.get("/api/story/card.svg")
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
        ET.fromstring(r.text)
        png = c.get("/api/story/card.png")
        assert png.status_code in (200, 501)
