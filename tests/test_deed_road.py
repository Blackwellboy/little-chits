"""The road to an age leads to the deed that earns it (projects.DEED_ROAD), and a great work is the island's
(projects.ISLAND_WORKS). By deeds, a village that knew the dynamo had no project for 75 days while the Electric Age
waited on a power station and a lamp; and no village ever planned a launch pad, counting only its own residents while
pioneers leave a village at 40 (issue #168)."""

import pytest

from chits.sim import projects
from chits.sim import world as W
from chits.sim.items import DESIGNS
from chits.sim.world import ERAS, World

MACHINE = next(i for i, (_, k) in enumerate(ERAS) if k == "recipe:engine")


def _machine_world(monkeypatch, n=12):
    monkeypatch.setattr(W, "ERA_BY_DEEDS", True)
    w = World("A", "A", 3, "direct", 96, n)
    a = next(iter(w.agents.values()))
    pump = w.place_site("steam_pump", *w.find_site("steam_pump", a.x + 2, a.y, 12), a)
    w.complete_structure(pump, a)  # a machine at work: the Machine Age, by its deed
    w.update_era()
    assert w.era()[0] == MACHINE
    for o in w.agents.values():
        o.learn("recipe:dynamo", "taught", w.tick)  # everyone knows the dynamo: the idea of the next age is had
        o.learn("design:power_station", "taught", w.tick)
        o.learn("design:street_lamp", "taught", w.tick)
    return w, a


def _next_age(w):
    return [c for c in projects.candidates(w) if "Electric Age" in c[3]]


@pytest.mark.parametrize("on", [True, False])
def test_knowing_the_dynamo_the_road_leads_on_to_a_power_station(on, monkeypatch):
    monkeypatch.setattr(projects, "DEED_ROAD", on)
    w, a = _machine_world(monkeypatch)
    road = _next_age(w)
    if not on:
        assert not road  # the idea is had: the old road ends there, though the age is not earned
        return
    assert len(road) == 1  # a project on the road (its first step may be a station or material on the way)
    view = projects.road(w)
    assert view and view["age"] == ERAS[MACHINE + 1][0]
    undone = [s["key"] for s in view["steps"] if not s["done"]]
    assert "power_station" in undone and "street_lamp" in undone  # (the deed: both standing at once)
    assert projects.age_targets(w, MACHINE + 1) == [("recipe", "dynamo"), ("design", "power_station"),
                                                    ("design", "street_lamp")]


def test_with_the_station_standing_the_road_asks_for_the_lamp(monkeypatch):
    w, a = _machine_world(monkeypatch)
    st = w.place_site("power_station", *w.find_site("power_station", a.x - 6, a.y, 14), a)
    w.complete_structure(st, a)
    assert len(_next_age(w)) == 1
    undone = [s["key"] for s in projects.road(w)["steps"] if not s["done"]]
    assert "street_lamp" in undone and "power_station" not in undone  # (the station stands: the lamp is what's left)


@pytest.mark.parametrize("on", [True, False])
def test_a_great_work_counts_everyone_on_the_island(on, monkeypatch):
    monkeypatch.setattr(projects, "ISLAND_WORKS", on)
    w = World("A", "A", 3, "direct", 96, DESIGNS["launch_pad"].min_pop + 5)
    sc = projects.Scope(w, None, True)
    sc.pop = 25  # a village of 25 on an island of 45: pioneers have carried the rest to daughter villages
    designs = {"launch_pad"}
    recipes = {k for kind, k in DESIGNS["launch_pad"].prereqs if kind == "recipe"}
    recipes |= {m for m, _ in DESIGNS["launch_pad"].materials}
    step = projects.next_step(w, designs, recipes, set(), "design", "launch_pad", sc=sc)
    assert (step is not None) is on
