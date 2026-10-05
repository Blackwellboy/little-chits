"""A harvest step that named a farm took grain from it ripe or not: 6 grain from an empty plot."""

from chits.sim import actions
from chits.sim.world import World


def _farm(w, a, dx):
    pos = w.find_site("farm", a.x + dx, a.y, 10)
    f = w.place_site("farm", pos[0], pos[1], a)
    w.complete_structure(f, a)
    return f


def _harvest(w, a, target):
    a.plan = [{"do": "harvest", "target": target}]
    for _ in range(300):
        if not a.plan:
            break
        a.hunger, a.energy, a.warmth = 100.0, 100.0, 100.0
        actions.run(w, a)
        w.tick += 1


def _world():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    return w, a


# ------------------------------------------------------------------ a named farm must be ripe
def test_a_named_empty_farm_gives_no_grain():
    w, a = _world()
    farm = _farm(w, a, 3)
    farm.planted, farm.growth = False, 0.0
    _harvest(w, a, farm.id)
    assert a.inventory.get("grain", 0) == 0, a.last_result


def test_a_named_unripe_farm_gives_way_to_a_ripe_one_nearby():
    w, a = _world()
    green = _farm(w, a, 3)
    green.planted, green.growth = True, 0.4
    ripe = _farm(w, a, -6)
    ripe.planted, ripe.growth = True, 1.0
    _harvest(w, a, green.id)
    assert a.inventory.get("grain", 0) > 0
    assert green.planted and green.growth < 1.0  # (it grows on, unharvested)
    assert ripe.growth == 0.0


def test_the_switch_restores_the_old_physics_for_the_identity_test(monkeypatch):
    monkeypatch.setattr(actions, "RIPE_TARGET", False)
    w, a = _world()
    farm = _farm(w, a, 3)
    farm.planted, farm.growth = False, 0.0
    _harvest(w, a, farm.id)
    assert a.inventory.get("grain", 0) > 0  # (the old fault: grain from an empty plot)


def test_the_ripe_farm_it_turned_to_stays_its_goal_as_it_walks():
    # chosen afresh each tick, the nearest ripe farm changed under a walking chit: two starved walking between farms
    w, a = _world()
    green = _farm(w, a, 3)
    green.planted, green.growth = True, 0.4
    near = _farm(w, a, -8)
    far = _farm(w, a, 16)
    for f in (near, far):
        f.planted, f.growth = True, 1.0
    a.plan = [{"do": "harvest", "target": green.id}]
    actions.run(w, a)
    chosen = a.plan[0]["_s"]["farm"]
    a.x, a.y = far.x, far.y + 3  # (now nearer the other one)
    actions.run(w, a)
    assert a.plan and a.plan[0]["_s"]["farm"] == chosen
