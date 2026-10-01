"""World A and World B may differ only by their culture flags; the storyteller treats both alike and hands out no
knowledge (recovered Codex audit, 2026-09-29)."""
import random

from chits.sim.world import World


def setup(n=2):
    w = World("A", "A", 1, "direct", 64, n)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = a.energy = a.warmth = 100
    return w, a


def building(w, a, design):
    x, y = w.find_site(design, a.x, a.y)
    st = w.place_site(design, x, y, a)
    w.complete_structure(st, a)
    return st


def test_stigmergy_does_not_read_neighbours_private_failures():
    w = World("B", "B", 1, "stigmergy", 64, 2)
    a, b = w.agents.values()
    b.x, b.y = a.x, a.y
    b.failed_experiments = ["2 wood at the fire"]
    assert not w.village_failed(a)


def test_inheritance_respects_culture_and_records_provenance():
    from chits.sim.items import RECIPES
    for culture in ("direct", "stigmergy"):
        w = World("A", "A", 5, culture, 64, 2)
        a, b = w.agents.values()
        for k in RECIPES:
            a.learn("recipe:" + k, "discovered", w.tick)
        # Hearing a recipe does not establish a parent's practical competence.
        a.knows["recipe:engine"]["status"] = "told"
        home = building(w, a, "hut")
        child = w._make_child(a, b, home)
        got = {k for k in child.knows if k.startswith("recipe:")}
        if culture == "stigmergy":
            assert not got
        else:
            assert got and "recipe:engine" not in got
            records = [x for x in w.deliveries if x["to"] == child.id and x["channel"] == "raised"]
            assert {x["knowledge"] for x in records} == got


def test_traveller_offers_observations_without_granting_knowledge():
    from chits.sim import storyteller
    w, a = setup()
    w.tick = 40 * 240
    for agent in w.agents.values():
        agent.familiar.update({"clay", "wood", "stone", "charcoal"})
    before = {x.id: dict(x.knows) for x in w.agents.values()}
    assert storyteller.stranger(w, random.Random(1))
    assert {x.id: dict(x.knows) for x in w.agents.values()} == before
    assert any(m.kind == "wonder" for x in w.agents.values() for m in x.memories)


def test_matched_storyteller_application_has_equal_effects():
    from chits.sim import storyteller
    for day in range(20, 70):
        if not storyteller.today(1234, day):
            continue
        worlds = [World(wid, wid, 1234, "direct", 64, 8) for wid in ("A", "B")]
        for w in worlds:
            w.tick = day * 240
        assert storyteller.daily(worlds[0]) == storyteller.daily(worlds[1])
        assert [(a.health, a.energy) for a in worlds[0].agents.values()] == [(a.health, a.energy) for a in worlds[1].agents.values()]
        assert worlds[0].ground == worlds[1].ground
