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
        w.tick += 240 * 5
        builder = list(w.agents.values())[-1]
        w.complete_structure(farm, builder)  # one stands: now it is the Farmers' age
        assert w.era_index == FARMERS and "farm" in w.built_designs
        # and the age is the builder's, on the day it stood: not the thinker's, on the day of the idea
        from chits.story.recap import _age_days
        from chits.views import eras, progress
        hero = eras(w)["heroes"][-1]
        assert hero["who"] == builder.name and hero["day"] == w.tick // 240 + 1
        rung = next(r for r in progress(w, [])["ladder"] if r["needs"] and r["reached"] and r["name"] == ERAS[FARMERS][0])
        assert rung["by"] == builder.name and rung["day"] == hero["day"]
        assert _age_days(w)[ERAS[FARMERS][0]] == hero["day"]


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


def test_a_save_without_a_build_record_takes_it_from_what_stands(monkeypatch):
    w, a = _world(False, monkeypatch)
    farm = w.place_site("farm", *w.find_site("farm", a.x + 2, a.y, 8), a)
    w.complete_structure(farm, a)
    d = json.loads(json.dumps(w.to_dict()))
    assert "built_designs" not in d
    back = World.from_dict(d)
    assert back.built_designs["farm"] == d["first"]["design:farm"]  # (who built the first, and when, from its record)


# --- age_rules 2: the late ages are earned by capability, not the idea (issue #161) -------------------------------

MACHINE = next(i for i, (_, k) in enumerate(ERAS) if k == "recipe:engine")
ELECTRIC = next(i for i, (_, k) in enumerate(ERAS) if k == "recipe:dynamo")
SPACE = next(i for i, (_, k) in enumerate(ERAS) if k == "design:launch_pad")


def _stand(w, a, design):
    s = w.place_site(design, *w.find_site(design, a.x + 2, a.y, 12), a)
    w.complete_structure(s, a)
    return s


def test_the_machine_age_needs_a_machine_not_the_idea(monkeypatch):
    w, a = _world(True, monkeypatch)
    assert w.age_rules == 2  # (a new deeds world plays by the capability rules)
    w.learned(a, "recipe:engine", "insight")  # a chit dreams of engines: no machine stands yet
    assert w.era()[0] < MACHINE
    _stand(w, a, "theatre")  # an unrelated modern building advances nothing
    assert w.era()[0] < MACHINE and not w.deed_ages
    _stand(w, a, "steam_pump")  # an engine-driven machine stands: its cost bought an engine, and it works
    assert w.era()[0] == MACHINE
    deed = w.deed_ages["recipe:engine"]
    assert deed["evidence"] == "building:steam_pump" and deed["by"] == a.id and deed["name"] == a.name
    assert w.age_record("recipe:engine") == deed  # (the provenance is the record)


def test_the_electric_age_needs_generation_and_a_load(monkeypatch):
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")  # (Machine first, the natural order)
    _stand(w, a, "power_station")  # generation, but no electrical load yet
    assert w.era()[0] == MACHINE and "recipe:dynamo" not in w.deed_ages
    _stand(w, a, "street_lamp")  # a real electrical load: now the age is earned
    assert w.era()[0] == ELECTRIC
    assert w.deed_ages["recipe:dynamo"]["evidence"] == "building:power_station+building:street_lamp"


def test_the_electric_age_also_arrives_if_the_load_came_first(monkeypatch):
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")
    _stand(w, a, "street_lamp")  # a lamp, but nothing generates yet
    assert w.era()[0] == MACHINE
    _stand(w, a, "power_station")
    assert w.era()[0] == ELECTRIC


def test_the_electric_age_needs_generation_and_a_load_standing_now_not_in_history(monkeypatch):
    # (Codex P2, #165: built_designs remembers a station that no longer stands, so a lamp alone earned Electric)
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")
    ps = _stand(w, a, "power_station")
    w.remove_structure(ps)  # the real removal path: the station is gone from the land
    _stand(w, a, "street_lamp")  # a load, but nothing generates: the ledger remembers, the island does not
    assert w.era()[0] == MACHINE and "recipe:dynamo" not in w.deed_ages
    ps2 = _stand(w, a, "power_station")  # generation again, while the lamp still stands
    assert w.era()[0] == ELECTRIC
    deed = w.deed_ages["recipe:dynamo"]
    assert deed["structure"] == ps2.id and deed["by"] == a.id  # (provenance: the deed that completed the capability)


def test_the_electric_age_also_waits_while_the_load_is_a_ruin(monkeypatch):
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")
    lamp = _stand(w, a, "street_lamp")
    lamp.durability = 0.0  # (fallen: complete, but a ruin)
    _stand(w, a, "power_station")  # generation, but the only load is a ruin
    assert w.era()[0] == MACHINE and "recipe:dynamo" not in w.deed_ages
    _stand(w, a, "street_lamp")  # a living load while the station stands: now the age is earned
    assert w.era()[0] == ELECTRIC


def test_the_space_age_needs_the_launch_not_the_design(monkeypatch):
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")
    _stand(w, a, "power_station")
    _stand(w, a, "street_lamp")
    w.learned(a, "design:launch_pad", "insight")  # the idea of a launch pad: no rocket has flown
    assert w.era()[0] == ELECTRIC
    _stand(w, a, "launch_pad")  # the pad stands, and its completion is the launch (_launch: the first astronauts)
    assert w.era()[0] == SPACE
    deed = w.deed_ages["design:launch_pad"]
    assert deed["evidence"] == "event:launch" and deed["by"] == a.id
    assert any(e.kind == "launch" for e in w.events)  # (the launch really happened, it is not just a label)


def test_capability_ages_keep_their_provenance_across_a_save(monkeypatch):
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")
    _stand(w, a, "power_station")
    _stand(w, a, "street_lamp")
    _stand(w, a, "launch_pad")
    d = json.loads(json.dumps(w.to_dict()))
    assert d["age_rules"] == 2 and set(d["deed_ages"]) == {"recipe:engine", "recipe:dynamo", "design:launch_pad"}
    monkeypatch.setattr(W, "ERA_BY_DEEDS", False)  # (a later default doesn't reinterpret a saved world)
    back = World.from_dict(d)
    assert back.age_rules == 2 and back.deed_ages == w.deed_ages
    assert back.era_index == w.era_index == SPACE and back.era()[0] == SPACE


def test_a_world_saved_before_age_rules_plays_by_the_old_rules(monkeypatch):
    w, a = _world(True, monkeypatch)
    _stand(w, a, "steam_pump")
    d = json.loads(json.dumps(w.to_dict()))
    del d["age_rules"], d["deed_ages"]  # (a #157-era deeds save: it has neither)
    back = World.from_dict(d)
    assert back.age_rules == 1 and back.deed_ages == {}
    w2 = back
    w2.learned(next(iter(w2.agents.values())), "recipe:engine", "insight")
    assert w2.era()[0] == MACHINE  # (v1: knowing the engine IS the Machine Age)
    _stand(w2, next(iter(w2.agents.values())), "power_station")
    assert w2.era()[0] == MACHINE  # (v1: no capability recording, no load requirement)
    assert not w2.deed_ages
