"""🧭 Progress: the road to space, what chits are doing, and how the latest achievements happened."""

from chits import views
from chits.sim.world import World


def test_progress_shows_the_road_to_space_honestly():
    w = World("A", "A", 3, "direct", 64, 6)
    chit = next(iter(w.agents.values()))
    # farming was invented, but nobody ever made a stone axe: that age is skipped, not claimed
    w.first["design:campfire"] = {"tick": 10, "by": chit.id, "name": chit.name}
    w.first["design:farm"] = {"tick": 300, "by": chit.id, "name": chit.name}
    chit.activity = "gathering wood"
    chit.objective = "somewhere warm before winter"
    events = [{"seq": 1, "tick": w.tick, "kind": "discovery", "importance": 5, "actor": chit.id, "text": "",
               "data": {"knowledge": "recipe:bread", "how": "discovered"}}]
    p = views.progress(w, events)
    rungs = {r["name"]: r for r in p["ladder"]}
    assert p["era"]["name"] == "Farmers" and p["next"]["name"] == "Potters" and p["next"]["needs"] == "clay pot"
    assert rungs["Farmers"]["reached"] and rungs["Farmers"]["by"] == chit.name and rungs["Farmers"]["day"] == 2
    assert not rungs["Toolmakers"]["reached"]
    assert ["gathering", 1] in [list(d) for d in p["doing"]]
    assert p["aims"][0] == ("somewhere warm before winter", 1)
    assert p["recent"][0]["day"] == p["day"] and "worked out bread by experimenting" in p["recent"][0]["lines"][0]
