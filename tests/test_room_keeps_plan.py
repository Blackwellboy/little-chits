"""The arms-full reflex keeps what the rest of the plan needs (actions.ROOM_KEEPS_PLAN, issue #98). Off, it stored
everything: a pioneer who had just fetched wood for the new village's hut put it back in the stockpile."""

import pytest

from chits.sim import actions
from chits.sim.items import DESIGNS
from chits.sim.world import World

FIRE = dict(DESIGNS["campfire"].material_map)


def _full_handed(on, monkeypatch, fetch):
    monkeypatch.setattr(actions, "ROOM_KEEPS_PLAN", on)
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.hunger = a.energy = a.warmth = a.health = 95.0
    a.inventory.clear()
    a.learn("design:campfire", "taught", w.tick)
    pile = w.place_site("stockpile", *w.find_site("stockpile", a.x + 2, a.y, 8), a)
    w.complete_structure(pile, a)
    a.inventory.update(FIRE)
    while a.free_space() > 0:
        a.add("clay", 1)  # (the rest of the load: not the fire's)
    a.plan = [{"do": "take", "what": fetch, "qty": 2}, {"do": "build", "what": "campfire"}]
    return w, a, pile


def _settle(w, a):
    for _ in range(80):
        if not a.plan or a.plan[0]["do"] != "store":
            break
        actions.run(w, a)
        w.tick += 1


@pytest.mark.parametrize("on", [True, False])
def test_the_load_is_put_down_but_the_plans_materials_stay(on, monkeypatch):
    w, a, pile = _full_handed(on, monkeypatch, "sand")  # (fetching something the plan doesn't already hold)
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "store" and a.plan[0]["_reflex"]
    _settle(w, a)
    assert pile.storage.get("clay", 0) > 0  # the rest of the load goes down either way
    assert all(a.inventory.get(k, 0) >= n for k, n in FIRE.items()) is on  # off: the fire's things went too


@pytest.mark.parametrize("on", [True, False])
def test_a_fetch_for_what_it_already_holds_is_dropped_not_the_load(on, monkeypatch):
    w, a, pile = _full_handed(on, monkeypatch, "wood")  # (it holds the fire's wood already)
    actions.reflexes(w, a)
    if on:
        assert a.plan[0]["do"] == "build" and not pile.storage  # the surplus fetch is dropped; nothing put down
    else:
        assert a.plan[0]["do"] == "store"  # off: as before, everything goes down first
        _settle(w, a)
        assert pile.storage.get("wood", 0) > 0


def test_plan_needs_counts_builds_crafts_and_experiments():
    w = World("A", "A", 3, "direct", 64, 2)
    need = actions.plan_needs(w, [{"do": "build", "what": "hut"}, {"do": "experiment", "with": ["clay", "clay"]},
                                  {"do": "gather", "what": "wood"}])
    assert need.get("clay") == 2 and all(need.get(k, 0) >= n for k, n in DESIGNS["hut"].material_map.items())
