"""📖 The Knowledge tab's encyclopedia: what a discovered thing is for, and nothing about what isn't discovered."""

import json

from chits import views
from chits.sim.invent import register_invention
from chits.sim.items import DESIGNS, RECIPES
from chits.sim.world import World


def _world(wid="A"):
    w = World(wid, wid, 3, "direct", 64, 6)
    return w, next(iter(w.agents.values()))


def test_an_item_says_what_it_is_made_from_what_it_does_and_what_it_goes_into():
    w, chit = _world()
    w.learned(chit, "recipe:cord", "discovered")
    e = views.encyclopedia(w, "recipe:cord")
    assert e["name"] == "cord" and e["props"] == ["strong", "binding", "flexible"]
    assert e["first_by"] == chit.name and e["first_day"] == 1
    assert e["made_from"] == {"inputs": [{"key": "fiber", "name": "plant fiber", "icon": "🌾", "n": 2}],
                              "station": None, "makes": 1}
    assert e["used_in_recipes"] == [], "nothing made with cord has been discovered yet"
    w.learned(chit, "recipe:sharp_stone", "discovered")
    w.learned(chit, "recipe:stone_axe", "discovered")
    e = views.encyclopedia(w, "recipe:cord")
    assert [x["key"] for x in e["used_in_recipes"]] == ["stone_axe"]
    axe = views.encyclopedia(w, "recipe:stone_axe")
    assert axe["effects"] == ["Tool: works as an axe with power 2.", "Helps to gather wood."]
    assert [(x["key"], x["n"]) for x in axe["made_from"]["inputs"]] == [("cord", 1), ("sharp_stone", 1), ("wood", 1)]


def test_effects_come_from_the_item_table():
    w, chit = _world()
    for k in ("bread", "basket", "clothes", "spear", "plough"):
        w.first[f"recipe:{k}"] = {"tick": 0, "by": chit.id, "name": chit.name}
    fx = lambda k: views.encyclopedia(w, f"recipe:{k}")["effects"]
    assert fx("bread") == ["Food: eating one restores 55 hunger."]
    assert fx("basket") == ["Carrying: its holder can carry 8 more."]
    assert fx("clothes") == ["Wearable: a chit can wear it.", "Use: wear them: a warm thing to wear halves the cold."]
    assert fx("spear") == ["Tool: works as a spear with power 1.", "Needed to gather fish."]
    assert fx("plough") == ["Use: carry it while harvesting a farm to double the base grain yield."]
    assert views.encyclopedia(w, "recipe:bread")["made_from"]["station"] == "fire"


def test_nothing_undiscovered_is_returned():
    w, chit = _world()
    w.learned(chit, "recipe:cord", "discovered")
    assert views.encyclopedia(w, "recipe:copper") is None
    assert views.encyclopedia(w, "design:furnace") is None
    assert views.encyclopedia(w, "recipe:no_such_thing") is None and views.encyclopedia(w, "nonsense") is None
    e = views.encyclopedia(w, "recipe:cord")
    found = {k for k in list(RECIPES) + list(DESIGNS)
             if views.discovered(w, f"recipe:{k}") or views.discovered(w, f"design:{k}")}
    for x in e["used_in_recipes"] + e["used_in_buildings"]:
        assert x["key"] in found
    text = json.dumps(e)
    assert "copper_pick" not in text and "copper pick" not in text and "cloak" not in text, \
        "an undiscovered recipe that takes cord is not named"
    uses = sum(1 for r in RECIPES.values() if "cord" in dict(r.inputs)) + sum(1 for d in DESIGNS.values() if "cord" in d.material_map)
    assert e["undiscovered_uses"] == uses - len(e["used_in_recipes"]) - len(e["used_in_buildings"]) > 0


def test_a_building_says_what_it_does_what_it_takes_and_how_big_it_is():
    w, chit = _world()
    e = views.encyclopedia(w, "design:hut")  # (every chit starts knowing it: no first finder)
    assert e["blurb"] == DESIGNS["hut"].blurb and e["size"] == [2, 2] and e["first_by"] is None
    assert [(m["key"], m["n"]) for m in e["materials"]] == [("wood", 8), ("fiber", 4)]
    fire = views.encyclopedia(w, "design:campfire")
    assert fire["station"] == "fire" and fire["made_here"] == [] and fire["undiscovered_uses"] > 0
    w.first["recipe:bread"] = {"tick": 0, "by": chit.id, "name": chit.name}
    assert [x["key"] for x in views.encyclopedia(w, "design:campfire")["made_here"]] == ["bread"]


def test_a_worlds_own_invention_is_in_its_encyclopedia_and_in_no_other():
    w, chit = _world("A")
    other, _ = _world("B")
    key = "inv_a_1"
    register_invention(w, key, "wolf stick", {"wood": 1, "sharp_stone": 1}, ("sturdy", "sharp"), {"tool": "spear", "tool_power": 1.0})
    w.inventions[key] = {"key": key, "name": "wolf stick", "inputs": {"wood": 1, "sharp_stone": 1}, "purpose": "defence",
                         "purpose_text": "to keep wolves off", "effect": {}, "props": ["sturdy", "sharp"], "by": chit.id,
                         "by_name": chit.name, "tick": 500}
    w.learned(chit, f"recipe:{key}", "discovered")
    e = views.encyclopedia(w, f"recipe:{key}")
    assert e["name"] == "wolf stick" and e["icon"] == "💡"
    assert e["invention"] == {"purpose": "defence", "purpose_text": "to keep wolves off", "by": chit.name, "day": 3}
    assert [x["name"] for x in e["made_from"]["inputs"]] == ["sharp stone", "wood"]
    assert views.encyclopedia(other, f"recipe:{key}") is None
    assert all(not x["key"].startswith("inv_") for x in views.knowledge_table([other]) if x["discovered"])


def test_the_endpoint_gives_404_for_the_undiscovered_and_needs_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_TOKEN", "book-test-token")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from fastapi.testclient import TestClient
    from chits.app import app

    with TestClient(app) as c:
        h = {"Authorization": "Bearer book-test-token"}
        wid = c.get("/api/worlds", headers=h).json()[0]["id"]
        assert c.get(f"/api/worlds/{wid}/encyclopedia/design:hut").status_code == 401
        r = c.get(f"/api/worlds/{wid}/encyclopedia/design:hut", headers=h)
        assert r.status_code == 200 and r.json()["blurb"].startswith("a home")
        assert c.get(f"/api/worlds/{wid}/encyclopedia/recipe:rocket_part", headers=h).status_code == 404
        assert c.get(f"/api/worlds/{wid}/encyclopedia/design:launch_pad", headers=h).status_code == 404
        assert c.get(f"/api/worlds/nope/encyclopedia/design:hut", headers=h).status_code == 404
