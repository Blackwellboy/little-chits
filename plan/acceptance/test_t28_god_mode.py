import json

from fastapi.testclient import TestClient

from chits.brain import prompt as P
from chits.sim.items import ITEMS, RECIPES, all_knowledge_keys
from chits.sim.world import World
import chits.sim.artifacts  # noqa: F401  (registers the artifacts)

ARTIFACTS = ["meteorite", "alien_ship", "holy_book", "treasure_chest", "golden_idol", "musket", "radio",
             "seed_vault", "time_capsule"]


def one(seed=3):
    w = World("A", "A", seed, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    for c in (a, b):
        c.hunger = c.energy = c.warmth = c.health = 100.0
        c.inventory.clear()
        c.plan = []
    return w, a, b


def run(w, a, step, limit=120):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_artifacts_are_items_but_not_knowledge():
    for k in ARTIFACTS:
        assert k in ITEMS and k not in RECIPES, k
    keys = all_knowledge_keys()
    assert not any(k.endswith(":" + x) for x in ARTIFACTS for k in keys)
    assert ITEMS["musket"].tool == "weapon"


def test_drop_and_pickup():
    w, a, b = one()
    a.add("wood", 3)
    run(w, a, {"do": "drop", "what": "wood", "qty": 2})
    assert w.ground.get(f"{a.x},{a.y}", {}).get("wood") == 2
    assert "On the ground" in P.scene(w, b) or "On the ground" in P.scene(w, a)
    run(w, a, {"do": "pickup", "what": "wood"})
    assert a.inventory.get("wood") == 3
    assert not w.ground.get(f"{a.x},{a.y}", {}).get("wood")


def test_meteorite_and_seed_vault():
    w, a, b = one(5)
    w.ground[f"{a.x},{a.y}"] = {"meteorite": 1, "_t": w.tick}
    run(w, a, {"do": "grab", "what": "meteorite"})
    here = w.ground.get(f"{a.x},{a.y}", {})
    assert a.inventory.get("ore", 0) >= 1 and a.inventory.get("ore", 0) + here.get("ore", 0) == 10
    assert not a.inventory.get("meteorite") and not here.get("meteorite")
    a.inventory.clear()
    w.ground[f"{a.x},{a.y}"] = {"seed_vault": 1, "_t": w.tick}
    run(w, a, {"do": "pickup", "what": "seed_vault"})
    here = w.ground.get(f"{a.x},{a.y}", {})
    assert a.inventory.get("seeds", 0) + here.get("seeds", 0) == 30


def test_alien_ship_teaches_something_new():
    w, a, b = one(7)
    evs = []
    w.listeners.append(evs.append)
    w.ground[f"{a.x},{a.y}"] = {"alien_ship": 1, "_t": w.tick}
    known = set(a.knows)
    run(w, a, {"do": "pickup", "what": "alien_ship"})
    assert not a.inventory.get("alien_ship")  # too big to carry
    run(w, a, {"do": "inspect", "target": "alien ship"})
    new = set(a.knows) - known
    assert any(k.startswith("recipe:") for k in new), a.last_result
    assert any(e.kind == "revelation" and e.importance == 5 for e in evs)


def test_god_api_and_save_points(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app
    import chits.app as appmod

    with TestClient(app) as c:
        rt = appmod.rt
        w = rt.worlds["A"]
        a = next(iter(w.agents.values()))
        ax, ay = a.x, a.y  # where the ship lands (a walks on while the world steps below)
        r = c.post("/api/worlds/A/god", json={"action": "drop", "item": "alien_ship", "x": ax, "y": ay})
        assert r.status_code == 200 and r.json()["ok"]
        assert w.ground[f"{a.x},{a.y}"]["alien_ship"] == 1
        assert c.post("/api/worlds/A/god", json={"action": "drop", "item": "unicorn", "x": 1, "y": 1}).status_code == 400
        assert c.post("/api/worlds/A/god", json={"action": "nuke", "x": 1, "y": 1}).status_code == 400
        assert c.post("/api/worlds/A/god", json={"action": "bless", "x": a.x, "y": a.y}).status_code == 200
        rt._flush_events(w)
        assert any(e["kind"] == "miracle" for e in rt.store.events("A", min_importance=5, limit=50))

        sp = c.post("/api/savepoints", json={"name": "before chaos"}).json()
        tick0, pop0 = w.tick, len(w.agents)
        for _ in range(50):
            w.step(rt.mind.hook)
        c.post("/api/worlds/A/god", json={"action": "meteor", "x": a.x, "y": a.y})
        lst = c.get("/api/savepoints").json()
        assert lst[0]["name"] == "before chaos" and "data" not in lst[0]
        assert c.post(f"/api/savepoints/{sp['id']}/restore").json()["ok"]
        w2 = appmod.rt.worlds["A"]
        assert w2.tick == tick0 and len(w2.agents) == pop0
        assert w2.ground.get(f"{ax},{ay}", {}).get("alien_ship") == 1
        assert "meteorite" not in json.dumps(w2.ground)
        assert c.delete(f"/api/savepoints/{sp['id']}").status_code == 200
