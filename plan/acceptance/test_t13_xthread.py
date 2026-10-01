from fastapi.testclient import TestClient

from chits.story.moments import Moment
from chits.story.xpost import make_thread, pick_clip

WORLDS = [
    {"id": "A", "name": "World A", "brain": "RTX 5090", "culture": "direct", "day": 12,
     "stats": {"population": 21, "discoveries": 15, "structures": 30}},
    {"id": "B", "name": "World B", "brain": "RTX 3090", "culture": "stigmergy", "day": 12,
     "stats": {"population": 17, "discoveries": 11, "structures": 22}},
]


def M(kind, score, text, tick=100, x=1.0):
    return Moment(kind=kind, score=score, tick=tick, x=x, y=2.0, actors=["a1"], text=text, seqs=[tick])


MOMENTS = {
    "A": [M("first", 95, 'Pip discovered how to make stone axe and named it "Chopper" — a first for the world!'),
          M("teaching_chain", 75, "Pip taught Mo, who taught Bix: stone axe"), M("birth", 40, "Lu was born")],
    "B": [M("legacy", 80, "Tam learned from a tablet left by the late Kip", tick=200, x=9.0), M("storm", 65, "A storm tears across the island")],
}


def test_thread_shape():
    posts = make_thread(WORLDS, MOMENTS, max_posts=6)
    assert 2 <= len(posts) <= 6
    assert all(len(p) <= 280 for p in posts)
    assert "RTX 5090" in posts[0] and "RTX 3090" in posts[0] and "Day 12" in posts[0]
    assert "Chopper" in posts[0]  # best moment in the hook
    body = "\n".join(posts[1:-1])
    assert "📜" in body and "World B · RTX 3090" in body and "📚" in body
    assert posts[-1].startswith("Scoreboard, day 12") and "#LittleChits" in posts[-1]
    assert "21 chits" in posts[-1] and "11 discoveries" in posts[-1]
    assert sum("Chopper" in p for p in posts) == 1  # hook moment not repeated
    assert make_thread(WORLDS, MOMENTS) == make_thread(WORLDS, MOMENTS)


def test_limits_and_dicts():
    long = {"A": [M("first", 90, "x" * 600)], "B": []}
    posts = make_thread(WORLDS, long, max_posts=3)
    assert len(posts) <= 3 and all(len(p) <= 280 for p in posts)
    as_dicts = {k: [m.__dict__ for m in v] for k, v in MOMENTS.items()}
    assert make_thread(WORLDS, as_dicts) == make_thread(WORLDS, MOMENTS)
    assert len(make_thread(WORLDS[:1], {"A": []})) >= 2


def test_clip():
    c = pick_clip(MOMENTS)
    assert c["world"] == "A" and c["kind"] == "first" and c["x"] == 1.0
    assert pick_clip({"A": [], "B": []}) is None


def test_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        rt = appmod.rt
        for w in rt.worlds.values():
            for _ in range(300):
                w.step(rt.mind.hook)
            rt._flush_events(w)
        r = c.get("/api/story/x?since_day=1&max_posts=5")
        assert r.status_code == 200
        d = r.json()
        assert 2 <= len(d["posts"]) <= 5 and all(len(p) <= 280 for p in d["posts"])
        assert "Instinct" in d["posts"][0]
