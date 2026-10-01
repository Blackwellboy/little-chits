"""F28 plough slice: a real iron plough has a physical farming effect."""

from chits.sim import actions
from chits.sim.items import ITEMS, RECIPES
from chits.sim.world import World


def _ripe_farm(w, a):
    spot = w.find_site("farm", a.x, a.y)
    assert spot is not None
    st = w.place_site("farm", *spot, a)
    w.complete_structure(st, a)
    st.planted = True
    st.growth = 1.0
    a.x, a.y = st.x, st.y
    return st


def _harvest(with_plough: bool) -> int:
    w = World("A", "A", 73, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["cart"] = 1  # enough carrying room that yield is measured in hand, not spill
    if with_plough:
        a.inventory["plough"] = 1
    st = _ripe_farm(w, a)
    step = {"do": "harvest", "target": st.id}
    for _ in range(80):
        out = actions.advance(w, a, step)
        if out != actions.RUNNING:
            assert out == actions.DONE, out
            break
        w.tick += 1
    else:
        raise AssertionError("harvest never finished")
    return a.inventory.get("grain", 0)


def test_plough_is_an_iron_workshop_tool_and_doubles_base_harvest():
    assert ITEMS["plough"].name == "plough"
    r = RECIPES["plough"]
    assert r.station == "workshop"
    assert dict(r.inputs) == {"iron": 2, "wood": 1}
    assert _harvest(False) == 6
    assert _harvest(True) == 12
