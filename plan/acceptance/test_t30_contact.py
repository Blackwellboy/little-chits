import json


def runtime(tmp_path, monkeypatch, contact):
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_CONTACT", "1" if contact else "0")
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="versus")
    return rt


def boat_for(w, a):
    pos = w.find_site("boat", a.x, a.y)
    assert pos, "a coast site for the boat"
    x, y = pos
    assert w.passable(x, y)
    s = w.place_site("boat", x, y, a)
    w.complete_structure(s, a)
    a.x, a.y = x, y
    return s


def ready(a):
    a.hunger = a.energy = a.warmth = a.health = 100.0
    a.plan = [{"do": "sail"}]


def test_no_contact_means_no_voyage(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch, False)
    wa = rt.worlds["A"]
    a = next(iter(wa.agents.values()))
    boat_for(wa, a)
    ready(a)
    for _ in range(40):
        rt.step_worlds()
        if not a.plan:
            break
    assert a.id in wa.agents and "sea" in a.last_result.lower()


def test_a_stranger_arrives(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch, True)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    a = next(iter(wa.agents.values()))
    a.learn("recipe:stone_axe", "discovered", wa.tick, None)
    boat_for(wa, a)
    ready(a)
    pop_b = len(wb.agents)
    for _ in range(400):
        rt.step_worlds()
        if len(wb.agents) > pop_b:
            break
    assert a.id not in wa.agents and a.id not in wa.dead
    arrived = [x for x in wb.agents.values() if x.origin == "A"]
    assert len(arrived) == 1
    s = arrived[0]
    assert s.name == a.name and "recipe:stone_axe" in s.knows and s.home is None
    kinds_a = {e.kind for e in wa.events}
    kinds_b = {e.kind for e in wb.events}
    assert "voyage" in kinds_a and "arrival" in kinds_b
    assert not any(st.design == "boat" for st in wa.structures.values())
    d = json.loads(json.dumps(wb.to_dict()))
    from chits.sim.world import World

    assert World.from_dict(d).agents[s.id].origin == "A"
