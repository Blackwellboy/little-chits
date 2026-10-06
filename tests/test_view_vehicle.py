"""A chit's view names the vehicle it holds (web: WorldView draws it pulled behind). Only one it really has."""

from chits.sim.world import World
from chits.views import agent_brief


def test_the_view_names_the_best_vehicle_a_chit_holds():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    assert agent_brief(w, a)["vehicle"] is None
    a.add("sled", 1)
    assert agent_brief(w, a)["vehicle"] == "sled"
    a.add("cart", 1)
    assert agent_brief(w, a)["vehicle"] == "cart"
    a.add("wagon", 1)
    assert agent_brief(w, a)["vehicle"] == "wagon"  # (the biggest it has)
