from fastapi.testclient import TestClient

from chits.brain.llm import BrainConfig, LLMBrain
from chits.story import chronicle as C

NAMES = {"a1": "Pip", "a2": "Mo", "a3": "Bix", "a9": "Zorbo"}
WORLD = {"id": "A", "name": "World A", "label": "Direct culture", "culture": "direct", "brain": "RTX 5090"}


def ev(seq, tick, kind, actor=None, text=None, imp=3, **data):
    return {"seq": seq, "tick": tick, "kind": kind, "text": text or f"{NAMES.get(actor, '')} did {kind}", "importance": imp,
            "actor": actor, "x": 1.0, "y": 1.0, "data": data}


EVENTS = [
    ev(1, 250, "discovery", "a1", "Pip discovered how to make stone axe — a first for the world!", 5, knowledge="recipe:stone_axe"),
    ev(2, 300, "built", "a2", "Mo, Pip and Bix finished the first hut together", 4, builders=["a1", "a2", "a3"], first=True),
    ev(3, 320, "speech", "a3", 'Bix: "hello"', 1),
    ev(4, 100, "birth", "a9", "Zorbo was born", 4, generation=1),  # day 1, not day 2
]
STATS = {"population": 17, "discoveries": 6, "structures": 9}


def facts():
    return C.daily_facts(WORLD, 2, EVENTS, STATS, NAMES)


def test_facts():
    f = facts()
    assert f["world"] == "A" and f["day"] == 2 and f["brain"] == "RTX 5090"
    assert f["agents"] == ["Bix", "Mo", "Pip"]
    assert [e["seq"] for e in f["events"]] == [1, 2]
    assert f["counts"] == {"discovery": 1, "built": 1, "speech": 1}
    assert f["moments"] and f["moments"][0]["kind"] == "first"


def test_markdown():
    md = C.render_markdown(facts())
    assert md.startswith("# World A — Day 2")
    assert "## Highlights" in md and "(#1)" in md and "## Numbers" in md and "17" in md


def test_validator():
    f = facts()
    known = set(NAMES.values())
    good = "On day 2 Pip chipped the island's first stone axe (#1), and Mo, Pip and Bix raised the first hut (#2)."
    assert C.validate_narration(good, f, known) == []
    assert C.validate_narration("Pip made an axe.", f, known)                       # no citation
    assert C.validate_narration("Pip made an axe (#99).", f, known)                 # bad citation
    assert C.validate_narration("Zorbo cheered as Pip made an axe (#1).", f, known)  # not involved today
    assert C.validate_narration("Pip made 42 axes (#1).", f, known)                 # invented number
    assert C.validate_narration("17 chits watched Pip (#1).", f, known) == []       # number from stats


async def test_narrate_rejects_bad_model(fake_llm_url):
    brain = LLMBrain(BrainConfig(id="fake", base_url=fake_llm_url))
    out = await C.narrate(brain, facts(), set(NAMES.values()))
    await brain.close()
    assert out is None or C.validate_narration(out, facts(), set(NAMES.values())) == []


def test_write_day(tmp_path):
    p = C.write_day(tmp_path, facts(), "A good day (#1).")
    assert p == tmp_path / "stories" / "A" / "day-002.md"
    txt = p.read_text()
    assert txt.startswith("# World A — Day 2") and "## The day, told" in txt and "A good day (#1)." in txt


def test_runtime_and_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_SPEED", "0")  # paused: the test drives the world itself
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        rt = appmod.rt
        w = rt.worlds["A"]
        for _ in range(250):
            w.step(rt.mind.hook)
        rt._flush_events(w)
        p = rt.write_chronicle(w, 1)
        assert p.exists() and p.read_text().startswith("# World A — Day 1")
        r = c.get("/api/worlds/A/stories/1")
        assert r.status_code == 200 and r.json()["markdown"].startswith("# World A — Day 1")
        assert c.get("/api/worlds/A/stories/999").status_code == 404
