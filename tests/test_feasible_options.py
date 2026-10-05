"""Instinct drafts the options a choosing model picks by letter (Instinct.options). An option that can't run from where
the chit stands is not offered: with the scripted model in the loop (tools/harness, --mind scripted --bad-rate 0) most
failed model steps were drafted options failing at once."""

import json

from chits.brain.instinct import Instinct, _drafted_runs
from chits.sim.actions import build_could_start
from chits.sim.items import DESIGNS
from chits.sim.world import World

WANDER = {"goal": "look around", "thought": "", "steps": [{"do": "wander"}]}


def _world(seed=3, brain="brainA"):
    w = World("A", "A", seed, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = o.health = o.mood = 95.0
        o.inventory.clear()
        o.plan = []
        o.brain = brain
    w.tick = 240 * 2 + 120  # midday
    return w, a


def _menu(w, a, *drafted):
    """The options instinct offers when its planners draft exactly these plans (and its own pick is a wander)."""
    ins = Instinct()
    queue = [json.loads(json.dumps(p)) for p in drafted]
    ins.plan = lambda world, ag: dict(WANDER)
    ins._progress = lambda world, ag, rng: queue.pop(0) if queue else None
    ins._communal = ins._maintain = ins._experiment = lambda world, ag, rng: None
    return [o["goal"] for o in ins.options(w, a)]


def _stockpile(w, a, **storage):
    st = w.place_site("stockpile", *w.find_site("stockpile", a.x + 3, a.y, 10), a)
    w.complete_structure(st, a)
    st.storage.update(storage)
    return st


def _no_ground(w, a, radius=40):
    """Every tile around the chit taken, its own excepted: nowhere for a building to go up."""
    for y in range(max(0, a.y - radius), min(w.h, a.y + radius + 1)):
        for x in range(max(0, a.x - radius), min(w.w, a.x + radius + 1)):
            if (x, y) != (a.x, a.y):
                w.occupied[y * w.w + x] = "struct_test"


# ---------------------------------------------------------------------------- build with no clear ground

def test_a_build_with_no_clear_ground_is_not_offered():
    w, a = _world()
    a.learn("design:brick_house", "taught", w.tick)
    house = {"goal": "build a brick house", "thought": "", "steps": [{"do": "build", "what": "brick_house"}]}
    assert "build a brick house" in _menu(w, a, house)
    _no_ground(w, a)
    assert not build_could_start(w, a, house["steps"][0])
    assert "build a brick house" not in _menu(w, a, house)
    # and the build step agrees: run it, it finds no clear ground
    a.plan = [dict(house["steps"][0])]
    w.step()
    assert "no clear ground" in a.last_result, a.last_result


def test_has_site_agrees_with_find_site_and_draws_nothing_random():
    w, a = _world()
    rng = w.rng_for("sites")
    before = rng.getstate()
    for design in ("hut", "brick_house", "stockpile", "farm", "kiln"):
        for r in (3, 8, 16):
            assert w.has_site(design, a.x, a.y, r, reach=(a.x, a.y)) == (w.find_site(design, a.x, a.y, r, reach=(a.x, a.y)) is not None)
    rng.setstate(before)
    w.has_site("brick_house", a.x, a.y, 28, reach=(a.x, a.y))
    assert rng.getstate() == before
    _no_ground(w, a)
    assert not w.has_site("hut", a.x, a.y, 28, reach=(a.x, a.y))
    assert w.find_site("hut", a.x, a.y, 28, reach=(a.x, a.y)) is None


def test_a_build_that_joins_a_site_or_does_not_know_the_design_is_judged_like_the_step():
    w, a = _world()
    hut = {"do": "build", "what": "hut"}
    assert not build_could_start(w, a, {"do": "build", "what": "brick_house"})  # it doesn't know how
    assert build_could_start(w, a, {"do": "build", "site": "anything"})  # (help at a site: no ground needed)
    a.learn("design:hut", "taught", w.tick)
    site = w.place_site("hut", *w.find_site("hut", a.x + 2, a.y, 8), a)
    _no_ground(w, a)
    assert build_could_start(w, a, hut)  # no ground, but a hut going up close by: the step joins it
    w.structures.pop(site.id)
    assert not build_could_start(w, a, hut)


# ---------------------------------------------------------------------------- invent and experiment without the parts

def test_an_invention_is_not_offered_from_parts_the_chits_own_plan_is_about_to_use():
    w, a = _world()
    a.inventory.update({"fiber": 2, "wood": 1})
    invents = lambda goals: [g for g in goals if g.startswith("invent")]
    assert invents(_menu(w, a))  # it carries the parts for a net
    # the mind asks for the next plan while this one's last steps are still to run: the same parts go into this
    a.plan = [{"do": "invent", "with": ["fiber", "wood"], "name": "Twine Rig", "purpose": "to catch fish"}]
    assert not invents(_menu(w, a))
    a.plan = [{"do": "store", "what": "all"}]  # everything it carries goes into the stores
    assert not invents(_menu(w, a))
    a.plan = [{"do": "eat"}]
    assert invents(_menu(w, a))


def test_an_experiment_needs_its_items_in_hand_or_a_step_that_gets_them():
    w, a = _world()
    exp = {"goal": "experiment", "thought": "", "steps": [{"do": "experiment", "with": ["stone", "wood"]}]}
    fetched = {"goal": "experiment", "thought": "",
               "steps": [{"do": "gather", "what": "wood", "qty": 1}, {"do": "experiment", "with": ["stone", "wood"]}]}
    assert "experiment" not in _menu(w, a, exp)
    a.inventory.update({"stone": 1})
    assert "experiment" not in _menu(w, a, exp)
    assert "experiment" in _menu(w, a, fetched)
    a.inventory.update({"wood": 1})
    assert "experiment" in _menu(w, a, exp)
    a.plan = [{"do": "experiment", "with": ["wood", "wood"]}]  # its current plan uses the wood
    assert "experiment" not in _menu(w, a, exp)
    # a building its plan is about to put up takes its materials from its hands (scripted seed 7: "build campfire",
    # then the experiment it had been offered with the same stone and wood)
    a.inventory.update({"wood": 3, "stone": 2})
    assert set(DESIGNS["campfire"].material_map) >= {"wood", "stone"}
    a.plan = [{"do": "build", "what": "campfire"}]
    assert "experiment" not in _menu(w, a, exp)
    site = w.place_site("campfire", *w.find_site("campfire", a.x + 3, a.y, 8), a)
    a.plan = [{"do": "help", "site": site.id}]
    assert "experiment" not in _menu(w, a, exp)
    site.needs.clear()  # (nothing left to bring)
    assert "experiment" in _menu(w, a, exp)
    # when the first of a kind can't run, the next of that kind can stand in for it
    a.plan = []
    a.inventory.pop("wood")
    assert "experiment" not in _menu(w, a, exp)
    assert "experiment" in _menu(w, a, exp, fetched)  # (the second: it gathers the wood)


# ---------------------------------------------------------------------------- store what it isn't carrying

def test_a_store_of_what_it_is_not_carrying_is_not_offered():
    w, a = _world()
    _stockpile(w, a)
    store = {"goal": "store the grain", "thought": "", "steps": [{"do": "store", "what": "grain"}]}
    assert "store the grain" not in _menu(w, a, store)
    a.inventory.update({"grain": 3})
    assert "store the grain" in _menu(w, a, store)
    a.plan = [{"do": "give", "to": "someone", "what": "grain", "qty": 3}]  # it gives the grain away first
    assert "store the grain" not in _menu(w, a, store)
    a.plan = []
    a.inventory.clear()
    gather = {"goal": "store berries", "thought": "", "steps": [{"do": "gather", "what": "berries", "qty": 8},
                                                                 {"do": "store", "what": "berries"}]}
    assert "store berries" in _menu(w, a, gather)  # it gathers them first


# ---------------------------------------------------------------------------- take and pick up what isn't there

def test_a_take_from_stores_that_hold_none_is_not_offered():
    w, a = _world()
    take = {"goal": "fetch cord", "thought": "", "steps": [{"do": "take", "what": "cord", "qty": 2}]}
    st = _stockpile(w, a)
    assert not _drafted_runs(w, a, take)
    st.storage["cord"] = 2
    assert _drafted_runs(w, a, take)
    a.plan = [{"do": "take", "what": "cord", "qty": 2}]  # its own plan takes those two first
    assert not _drafted_runs(w, a, take)


def test_a_pickup_with_nothing_lying_about_is_not_offered():
    w, a = _world()
    pick = {"goal": "pick up clay", "thought": "", "steps": [{"do": "pickup", "what": "clay"},
                                                              {"do": "experiment", "with": ["clay"], "at": "fire"}]}
    assert not _drafted_runs(w, a, pick)
    w.put_ground(a.x + 2, a.y, "clay", 2)
    assert _drafted_runs(w, a, pick)
    a.plan = [{"do": "pickup", "what": "clay"}]  # its own plan picks the pile up first
    assert not _drafted_runs(w, a, pick)


def test_a_fetch_into_full_hands_is_not_offered_unless_something_is_put_down_first():
    w, a = _world()
    _stockpile(w, a, wood=10)
    take = {"goal": "fetch wood", "thought": "", "steps": [{"do": "take", "what": "wood", "qty": 2}]}
    gather = {"goal": "collect wood", "thought": "", "steps": [{"do": "gather", "what": "wood", "qty": 2}]}
    assert _drafted_runs(w, a, take) and _drafted_runs(w, a, gather)
    while a.free_space() >= w.item("stone").weight:
        a.inventory["stone"] = a.inventory.get("stone", 0) + 1
    assert a.free_space() < w.item("wood").weight
    assert not _drafted_runs(w, a, take) and not _drafted_runs(w, a, gather)
    first = {"goal": "fetch wood", "thought": "", "steps": [{"do": "store", "what": "stone"}] + take["steps"]}
    assert _drafted_runs(w, a, first)
    a.plan = [{"do": "store", "what": "all"}]  # its own plan empties its hands first
    assert _drafted_runs(w, a, take)


def test_room_in_hand_is_counted_after_what_its_own_plan_brings_in_first():
    # (Codex, PR #119) one stone fits now and the rest of its plan takes it: a drafted "gather wood" then starts with
    # full hands
    w, a = _world()
    _stockpile(w, a, stone=10)
    stone, wood, fiber = w.item("stone"), w.item("wood"), w.item("fiber")
    while a.free_space() - fiber.weight >= max(wood.weight, stone.weight) and a.free_space() - fiber.weight >= 0:
        a.inventory["fiber"] = a.inventory.get("fiber", 0) + 1
    gather = {"goal": "collect wood", "thought": "", "steps": [{"do": "gather", "what": "wood", "qty": 2}]}
    assert a.free_space() >= wood.weight and _drafted_runs(w, a, gather)
    a.plan = [{"do": "take", "what": "stone", "qty": 1}]
    assert a.free_space() - stone.weight < wood.weight
    assert not _drafted_runs(w, a, gather)
    a.plan = [{"do": "take", "what": "stone", "qty": 1}, {"do": "experiment", "with": ["stone", "fiber"]}]
    assert _drafted_runs(w, a, gather)  # (the experiment uses the stone again, and a fiber)


def test_a_build_the_step_would_not_reuse_is_judged_on_its_ground():
    # (Codex, PR #119) the step builds a new farm beside a sown one and a new campfire beside a ruin: with no ground
    # for it, it fails, so the preflight must say so; an empty farm or a lit campfire it uses instead
    from chits.sim.actions import reuse_within

    w, a = _world()
    for d in ("farm", "campfire"):
        a.learn(f"design:{d}", "taught", w.tick)
        assert reuse_within(d)
    farm = w.place_site("farm", *w.find_site("farm", a.x + 2, a.y, 8), a)
    w.complete_structure(farm, a)
    fire = w.place_site("campfire", *w.find_site("campfire", a.x - 3, a.y, 8), a)
    w.complete_structure(fire, a)
    _no_ground(w, a)
    farm.planted = True
    assert not build_could_start(w, a, {"do": "build", "what": "farm"})
    farm.planted = False
    assert build_could_start(w, a, {"do": "build", "what": "farm"})  # it sows the empty one
    assert build_could_start(w, a, {"do": "build", "what": "campfire"})  # it feeds the one standing
    fire.durability = 0
    assert fire.ruined
    assert not build_could_start(w, a, {"do": "build", "what": "campfire"})


# ---------------------------------------------------------------------------- the menu is never empty, and costs nothing

def test_a_menu_with_nothing_that_can_run_still_offers_instincts_pick_and_changes_nothing():
    w, a = _world()
    ins = Instinct()
    ins.plan = lambda world, ag: {"goal": "store the grain", "thought": "", "steps": [{"do": "store", "what": "grain"}]}
    ins._progress = ins._communal = ins._maintain = ins._experiment = ins._survive = lambda world, ag, rng: None
    a.hunger = 30.0  # (needy: instinct's own pick is offered)
    before = json.dumps(w.to_dict(), sort_keys=True, default=str)
    assert [o["goal"] for o in ins.options(w, a)] == ["store the grain"]
    assert json.dumps(w.to_dict(), sort_keys=True, default=str) == before
