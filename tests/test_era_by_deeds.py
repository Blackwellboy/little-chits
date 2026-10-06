"""An age whose key is a building is reached when one stands, not when a chit imagines it (world.ERA_BY_DEEDS). A live
world entered the Space Age on day 369 because one chit came up with the idea of a launch pad: none was ever built."""

import json

import pytest

from chits.sim import world as W
from chits.sim.world import ERAS, World

FARMERS = next(i for i, (_, k) in enumerate(ERAS) if k == "design:farm")


def _world(deeds, monkeypatch):
    monkeypatch.setattr(W, "ERA_BY_DEEDS", deeds)
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    for key in [k for _, k in ERAS[:FARMERS] if k]:  # (every age below the Farmers, reached)
        w.first[key] = {"tick": 0, "by": a.id, "name": a.name}
    w.update_era()
    return w, a


@pytest.mark.parametrize("deeds", [True, False])
def test_imagining_a_building_reaches_its_age_only_without_deeds(deeds, monkeypatch):
    w, a = _world(deeds, monkeypatch)
    before = w.era_index
    w.learned(a, "design:farm", "insight")  # a chit comes up with the idea of a farm
    assert (w.era_index == FARMERS) is (not deeds)
    if deeds:
        assert w.era_index == before
        farm = w.place_site("farm", *w.find_site("farm", a.x + 2, a.y, 8), a)
        w.complete_structure(farm, a)  # one stands: now it is the Farmers' age
        assert w.era_index == FARMERS and "farm" in w.built_designs


def test_a_world_keeps_its_rule_and_what_it_built_across_a_save(monkeypatch):
    w, a = _world(True, monkeypatch)
    farm = w.place_site("farm", *w.find_site("farm", a.x + 2, a.y, 8), a)
    w.complete_structure(farm, a)
    d = json.loads(json.dumps(w.to_dict()))
    assert d["era_by_deeds"] is True and "farm" in d["built_designs"]
    monkeypatch.setattr(W, "ERA_BY_DEEDS", False)  # (a later default doesn't reinterpret a saved world)
    back = World.from_dict(d)
    assert back.era_by_deeds is True and "farm" in back.built_designs and back.era_index == w.era_index


def test_a_world_saved_before_keeps_the_ages_it_reached(monkeypatch):
    w, a = _world(False, monkeypatch)
    w.learned(a, "design:farm", "insight")
    d = json.loads(json.dumps(w.to_dict()))
    assert "era_by_deeds" not in d and "built_designs" not in d  # (the legacy shape, unchanged)
    monkeypatch.setattr(W, "ERA_BY_DEEDS", True)
    back = World.from_dict(d)
    assert back.era_by_deeds is False and back.era_index == FARMERS and back.era()[0] == FARMERS
