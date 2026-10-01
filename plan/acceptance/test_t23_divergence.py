from fastapi.testclient import TestClient

from chits.story.divergence import compare, to_markdown, to_tweet
from chits.sim.world import World


def twins(seed=21):
    return World("A", "World A", seed, "direct", 64, 3), World("B", "World B", seed, "stigmergy", 64, 3)


def first(w, key, tick):
    w.first[key] = {"tick": tick, "by": "x", "name": "x"}


def test_identical_twins_are_not_divergent():
    wa, wb = twins()
    c = compare(wa, wb)
    assert c["divergence"] == 0 and c["only"] == {"A": [], "B": []}
    assert "identical" in c["headline"].lower()


def test_scores_and_lists():
    wa, wb = twins()
    first(wa, "design:campfire", 250)   # day 2
    first(wa, "recipe:stone_axe", 500)
    first(wa, "recipe:pot", 900)
    first(wb, "recipe:pot", 300)
    first(wb, "design:campfire", 700)
    first(wb, "recipe:clay_tablet", 1000)
    c = compare(wa, wb)
    assert c["only"]["A"] == ["recipe:stone_axe"] and c["only"]["B"] == ["recipe:clay_tablet"]
    assert set(c["shared"]) == {"design:campfire", "recipe:pot"}
    assert abs(c["scores"]["knowledge"] - 0.5) < 1e-9
    assert abs(c["scores"]["order"] - 1.0) < 1e-9
    assert c["scores"]["culture"] == 0
    assert c["divergence"] == 55
    race = {r["key"]: r for r in c["race"]}
    assert race["design:campfire"]["A"] == 2 and race["design:campfire"]["winner"] == "A"
    assert race["recipe:pot"]["winner"] == "B"
    assert c["wins"] == {"A": 1, "B": 1}
    assert c["worlds"]["A"]["discoveries"] == 3 and c["worlds"]["B"]["culture"] == "stigmergy"


def test_culture_counts_and_text():
    wa, wb = twins()
    first(wa, "design:campfire", 250)
    first(wa, "recipe:stone_axe", 500)
    first(wa, "recipe:pot", 900)
    first(wb, "recipe:pot", 300)
    first(wb, "design:campfire", 700)
    first(wb, "recipe:clay_tablet", 1000)
    wa.inventions["inv_a_1"] = {"key": "inv_a_1", "name": "Fishnet", "inputs": {"fiber": 2, "wood": 1},
                                "purpose": "fishing", "purpose_text": "catch fish", "effect": {"tool": "spear", "tool_power": 1.2},
                                "props": ["invented"], "by": "x", "by_name": "Pip", "tick": 800}
    first(wa, "recipe:inv_a_1", 800)  # inventions are not base keys
    wb.beliefs["b1"] = {"id": "b1", "name": "The Ember Way", "tenet": "The fire remembers", "founder": "y",
                        "founder_name": "Mo", "tick": 900, "followers": ["y"]}
    c = compare(wa, wb)
    assert abs(c["scores"]["culture"] - 0.2) < 1e-9
    assert c["divergence"] == 59
    assert c["worlds"]["A"]["inventions"] == ["Fishnet"] and c["worlds"]["B"]["beliefs"] == ["The Ember Way"]
    assert "recipe:inv_a_1" not in c["only"]["A"]
    md = to_markdown(c)
    assert md.startswith("# ")
    for s in ("World A", "World B", "Fishnet", "The Ember Way", "59/100", "## Only in World A", "## The race"):
        assert s in md, s
    tw = to_tweet(c)
    assert len(tw) <= 280 and "59" in tw


def test_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_SPEED", "0")
    from chits.app import app

    with TestClient(app) as c:
        r = c.get("/api/compare")
        assert r.status_code == 200
        j = r.json()
        assert "divergence" in j["compare"] and j["markdown"].startswith("# ") and len(j["tweet"]) <= 280
