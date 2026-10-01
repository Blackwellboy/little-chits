import json

from fastapi.testclient import TestClient

from chits.brain import prompt as P
from chits.sim.world import World


def build(w, design, x, y, who):
    pos = w.find_site(design, x, y, radius=6)
    assert pos, design
    s = w.place_site(design, pos[0], pos[1], who)
    s.builders[who.id] = 1
    w.complete_structure(s, who)
    return s


def village_world():
    w = World("A", "A", 1234, "direct", 128, 6)
    a, b = list(w.agents.values())[:2]
    x, y = a.x, a.y
    h1 = build(w, "hut", x, y, a)
    h2 = build(w, "hut", x + 3, y, b)
    build(w, "campfire", x + 1, y + 3, a)
    a.home, b.home = h1.id, h2.id
    return w, a, b


def test_village_name_deterministic():
    from chits.sim.settlements import village_name

    assert village_name(5, "s3") == village_name(5, "s3")
    names = {village_name(5, f"s{i}") for i in range(30)}
    assert len(names) >= 10
    assert all(n[0].isupper() and n.isalpha() for n in names)


def test_detect_and_announce():
    from chits.sim.settlements import detect

    w, a, b = village_world()
    evs = []
    w.listeners.append(evs.append)
    found = detect(w)
    assert len(found) == 1
    s = found[0]
    num = lambda i: int(i[1:])
    assert s.homes == 2 and len(s.structures) == 3
    assert s.id == min(s.structures, key=num) and s.structures == sorted(s.structures, key=num)
    assert set(s.residents) == {a.id, b.id}
    w.update_settlements()
    ev = [e for e in evs if e.kind == "settlement"]
    assert len(ev) == 1 and ev[0].importance == 4 and s.name in ev[0].text
    w.update_settlements()
    assert len([e for e in evs if e.kind == "settlement"]) == 1  # announced once
    assert f"village of {s.name}" in P.scene(w, a)
    assert w.stats()["settlements"] == 1


def test_needs_two_homes():
    from chits.sim.settlements import detect

    w = World("A", "A", 1234, "direct", 128, 4)
    a = next(iter(w.agents.values()))
    build(w, "hut", a.x, a.y, a)
    build(w, "campfire", a.x + 3, a.y, a)
    build(w, "stockpile", a.x, a.y + 3, a)
    assert detect(w) == []


def test_name_stable_and_persisted():
    w, a, b = village_world()
    w.update_settlements()
    name = next(iter(w.settlements.values()))["name"]
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert next(iter(w2.settlements.values()))["name"] == name
    d = w.to_dict()
    d.pop("settlements")
    assert World.from_dict(json.loads(json.dumps(d))).settlements == {}


def test_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_SPEED", "0")  # paused: the test drives the world itself
    from chits.app import app

    with TestClient(app) as c:
        r = c.get("/api/worlds/A/settlements")
        assert r.status_code == 200 and isinstance(r.json(), list)
