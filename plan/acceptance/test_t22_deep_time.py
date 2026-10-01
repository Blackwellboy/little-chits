import json

from chits.brain import prompt as P
from chits.sim.items import (DESIGNS, GATHERABLE, ITEMS, RECIPES, STATIONS, match_recipe, normalize_design)
from chits.sim.world import ERAS, World

NEW_ITEMS = ["iron", "iron_axe", "iron_pick", "wheel", "cart", "paper", "steel", "gear", "engine", "wire",
             "magnet", "dynamo", "lightbulb", "fuel", "alloy", "rocket_part"]


def test_items_recipes_and_stations():
    for k in NEW_ITEMS:
        assert k in ITEMS and k in RECIPES, k
    assert "forge" in STATIONS and "factory" in STATIONS
    assert dict(RECIPES["iron"].inputs) == {"ore": 2, "charcoal": 2} and RECIPES["iron"].station == "furnace"
    assert RECIPES["steel"].station == "forge" and RECIPES["engine"].station == "forge"
    assert dict(RECIPES["rocket_part"].inputs) == {"alloy": 2, "engine": 1} and RECIPES["rocket_part"].station == "factory"
    assert RECIPES["wire"].qty == 3 and RECIPES["gear"].qty == 2
    assert match_recipe({"ore": 2, "charcoal": 2}, "furnace").key == "iron"
    assert match_recipe({"ore": 1, "charcoal": 1}, "furnace").key == "copper"
    assert match_recipe({"steel": 2, "gear": 2, "pot": 1}, "workshop") is None
    assert ITEMS["iron_axe"].tool == "axe" and ITEMS["iron_axe"].tool_power > ITEMS["copper_axe"].tool_power
    assert ITEMS["cart"].carry_bonus == 16


def test_designs_and_aliases():
    assert DESIGNS["forge"].station == "forge" and DESIGNS["factory"].station == "factory"
    assert DESIGNS["factory"].min_pop == 20 and DESIGNS["launch_pad"].min_pop == 40
    assert DESIGNS["hut"].min_pop == 0
    assert DESIGNS["launch_pad"].size == (3, 3)
    assert ("recipe", "rocket_part") in DESIGNS["launch_pad"].prereqs
    assert normalize_design("forge") == "forge" and normalize_design("smelter") == "furnace"
    assert normalize_design("rocket") == "launch_pad" and normalize_design("launch pad") == "launch_pad"


def test_the_ladder_is_reachable_and_long():
    """Every recipe and design is reachable from gatherable resources, and the rocket is expensive."""
    # grain is harvested from a farm (built from wood and seeds); meat is hunted and wool comes from tame sheep (T31)
    have = set(GATHERABLE) | {"grain", "meat", "wool"}
    stations = {"fire"}  # a campfire needs only wood and stone
    for _ in range(40):
        for d in DESIGNS.values():
            if d.station and all(m in have for m, _ in d.materials):
                stations.add(d.station)
        for r in RECIPES.values():
            if r.key.startswith("inv_"):
                continue
            if all(i in have for i, _ in r.inputs) and (r.station is None or r.station in stations):
                have.add(r.key)
    missing = [k for k in RECIPES if not k.startswith("inv_") and k not in have]
    assert not missing, missing
    for d in DESIGNS.values():
        assert all(m in have for m, _ in d.materials), d.key

    def raw(k):
        r = RECIPES.get(k)
        if not r or k.startswith("inv_"):
            return 1.0
        return sum(raw(i) * n for i, n in r.inputs) / r.qty

    assert sum(raw(m) * n for m, n in DESIGNS["launch_pad"].materials) >= 400


def test_great_works_need_many_hands():
    w = World("A", "A", 3, "direct", 64, 4)
    a = next(iter(w.agents.values()))
    a.hunger = a.energy = a.warmth = a.health = 100.0
    a.learn("design:factory", "taught", w.tick, None)
    a.inventory.clear()
    a.add("brick", 4)
    a.plan = [{"do": "build", "what": "factory"}]
    for _ in range(40):
        w.step()
        if not a.plan:
            break
    assert "people" in a.last_result.lower()
    assert not any(s.design == "factory" for s in w.structures.values())


def test_eras():
    w = World("A", "A", 5, "direct", 64, 2)
    evs = []
    w.listeners.append(evs.append)
    assert w.era() == (0, "Wanderers") and [n for n, _ in ERAS][-1] == "Space Age"
    assert len(ERAS) == 11
    w.first["design:campfire"] = {"tick": 1, "by": "x", "name": "x"}
    w.first["recipe:copper"] = {"tick": 2, "by": "x", "name": "x"}
    w.update_era()
    assert w.era() == (6, "Copper Age") and w.era_index == 6
    assert sum(e.kind == "era" for e in evs) == 1 and "Copper Age" in [e for e in evs if e.kind == "era"][0].text
    w.update_era()
    assert sum(e.kind == "era" for e in evs) == 1
    assert w.clock()["era"] == "Copper Age" and w.stats()["era"] == "Copper Age"
    a = next(iter(w.agents.values()))
    assert "Copper Age" in P.scene(w, a)
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.era_index == 6


def test_launch_makes_astronauts():
    w = World("A", "A", 7, "direct", 96, 4)
    evs = []
    w.listeners.append(evs.append)
    a, b, c, d = list(w.agents.values())[:4]
    pos = w.find_site("launch_pad", a.x, a.y)
    s = w.place_site("launch_pad", pos[0], pos[1], a)
    s.builders = {a.id: 50.0, b.id: 30.0, c.id: 20.0, d.id: 1.0}
    w.complete_structure(s, a)
    launch = [e for e in evs if e.kind == "launch"]
    assert launch and launch[0].importance == 5
    assert set(launch[0].data["crew"]) == {a.id, b.id, c.id}
    assert a.astronaut and b.astronaut and c.astronaut and not d.astronaut
    assert w.era()[1] == "Space Age"
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.agents[a.id].astronaut and not w2.agents[d.id].astronaut
