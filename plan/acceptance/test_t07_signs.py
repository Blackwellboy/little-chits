import json

from chits.brain import prompt as P
from chits.sim import actions
from chits.sim.world import World
from chits import views


def run_step(w, a, step, max_ticks=200):
    a.plan = [step]
    for _ in range(max_ticks):
        if not a.plan:
            break
        w.tick += 1
        actions.run(w, a)
    return a.last_result


def setup(culture="stigmergy"):
    w = World("B", "B", 11, culture, 96, 4)
    a, b = list(w.agents.values())[:2]
    for c in (a, b):
        c.hunger = c.energy = c.warmth = 100
    b.x, b.y = a.x + 2, a.y
    return w, a, b


def test_mark_in_stigmergy_world():
    w, a, b = setup()
    evs = []
    w.listeners.append(evs.append)
    a.inventory = {"wood": 2}
    run_step(w, a, {"do": "mark", "what": "clay"})
    assert len(w.signs) == 1
    s = next(iter(w.signs.values()))
    assert (s["x"], s["y"], s["symbol"], s["author"], s["author_name"]) == (a.x, a.y, "clay", a.id, a.name)
    assert a.inventory.get("wood") == 1
    assert any(e.kind == "sign" and e.importance == 2 for e in evs)
    assert w.signs_dirty


def test_costs_wood_and_validates():
    w, a, b = setup()
    a.inventory = {}
    assert "wood" in run_step(w, a, {"do": "mark", "what": "food"})
    a.inventory = {"wood": 1}
    res = run_step(w, a, {"do": "mark", "what": "unicorns"})
    assert "clay" in res and not w.signs
    run_step(w, a, {"do": "mark", "what": "berries"})
    assert next(iter(w.signs.values()))["symbol"] == "food"
    assert actions.normalize_verb("signpost") == "mark"


def test_one_sign_per_tile_and_expiry():
    w, a, b = setup()
    a.inventory = {"wood": 3}
    run_step(w, a, {"do": "mark", "what": "food"})
    run_step(w, a, {"do": "mark", "what": "danger"})
    assert len(w.signs) == 1 and next(iter(w.signs.values()))["symbol"] == "danger"
    for _ in range(800):
        w.step()
    assert not w.signs


def test_others_see_it_in_their_prompt_and_views():
    w, a, b = setup()
    a.inventory = {"wood": 1}
    run_step(w, a, {"do": "mark", "what": "ore"})
    assert "- Signs:" in P.scene(w, b) and '"ore"' in P.scene(w, b) and a.name in P.scene(w, b)
    assert "mark" in P.verb_guide(w)
    assert views.snapshot(w)["signs"][0]["symbol"] == "ore"
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert list(w2.signs.values())[0]["symbol"] == "ore"


def test_runtime_frame_sends_signs_once(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    w = rt.worlds["A"]
    a = next(iter(w.agents.values()))
    a.inventory = {"wood": 1}
    run_step(w, a, {"do": "mark", "what": "home"})
    f1 = rt.frame(w)
    f2 = rt.frame(w)
    assert f1["signs"] and f1["signs"][0]["symbol"] == "home"
    assert f2["signs"] is None
