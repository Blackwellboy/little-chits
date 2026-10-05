"""A model choosing from instinct's options in the 2026-10-05 live game took "harvest, then store the grain" when it
could no longer bring grain home: "I'm not carrying any grain" (store, 159 tries by day 107)."""

from chits.brain.instinct import Instinct, _can_run, _drafted_runs
from chits.sim.world import World

HARVEST_AND_STORE = {"goal": "harvest", "steps": [{"do": "harvest"}, {"do": "store", "what": "grain"}]}


def _farm_world():
    w = World("A", "A", 3, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    pos = w.find_site("farm", a.x + 3, a.y, 10)
    farm = w.place_site("farm", pos[0], pos[1], a)
    w.complete_structure(farm, a)
    farm.planted, farm.growth = True, 1.0
    pile_at = w.find_site("stockpile", a.x - 3, a.y, 10)
    pile = w.place_site("stockpile", pile_at[0], pile_at[1], a)
    w.complete_structure(pile, a)
    a.inventory.clear()
    b.x, b.y = a.x, a.y + 1
    return w, a, b, farm


def test_not_when_another_chit_is_already_on_its_way_to_the_only_ripe_farm():
    w, a, b, farm = _farm_world()
    assert _can_run(w, a, HARVEST_AND_STORE)  # (while the farm is free)
    b.plan = [{"do": "harvest"}, {"do": "store", "what": "grain"}]
    assert not _can_run(w, a, HARVEST_AND_STORE)
    b.plan = []
    b.pending_plan = {"steps": [{"do": "harvest"}, {"do": "store", "what": "grain"}]}
    assert not _can_run(w, a, HARVEST_AND_STORE)


def test_not_with_no_room_in_hand_for_the_grain():
    w, a, b, farm = _farm_world()
    while a.free_space() > 0:
        a.add("stone", 1)
    assert not _drafted_runs(w, a, HARVEST_AND_STORE)  # (the projection of its hands: #119)
    assert all(not _is_harvest_and_store(w, o) for o in Instinct().options(w, a))


def test_not_when_nothing_is_ripe_and_a_plain_harvest_to_eat_is_not_judged():
    w, a, b, farm = _farm_world()
    farm.growth = 0.5
    assert not _can_run(w, a, HARVEST_AND_STORE)
    assert _can_run(w, a, {"goal": "harvest the farm", "steps": [{"do": "harvest"}, {"do": "eat"}]})


def test_the_menu_a_model_chooses_from_leaves_out_a_harvest_another_chit_has_taken():
    w, a, b, farm = _farm_world()
    ins = Instinct()

    def offered():
        n = 0
        for t in range(60):
            w.tick = 1000 + t * 37
            n += sum(1 for o in ins.options(w, a) if _is_harvest_and_store(w, o))
        return n

    assert offered() > 0  # (the control: a free ripe farm is offered)
    b.plan = [{"do": "harvest"}, {"do": "store", "what": "grain"}]
    assert offered() == 0


def _is_harvest_and_store(w, o):
    steps = o.get("steps") or []
    return any(s.get("do") == "harvest" for s in steps) and any(
        s.get("do") == "store" and w.norm_item(s.get("what")) == "grain" for s in steps)


def test_a_chit_harvesting_some_other_named_farm_takes_nothing_from_this_one():
    # (Codex on #113): a harvest names its farm, or takes the nearest ripe one to its harvester
    # (an id that names no structure is no farm of its own: the step takes the nearest ripe one, so name a real one)
    w, a, b, farm = _farm_world()
    pos = w.find_site("farm", a.x - 12, a.y, 10)
    elsewhere = w.place_site("farm", pos[0], pos[1], a)
    w.complete_structure(elsewhere, a)
    b.plan = [{"do": "harvest", "target": elsewhere.id}, {"do": "store", "what": "grain"}]
    assert _can_run(w, a, HARVEST_AND_STORE)


def test_two_chits_naming_the_same_farm_leave_the_other_ripe_farm_free():
    w = World("A", "A", 3, "direct", 64, 3)
    a, b, c = list(w.agents.values())[:3]
    farms = []
    for dx in (3, -8):
        pos = w.find_site("farm", a.x + dx, a.y, 10)
        f = w.place_site("farm", pos[0], pos[1], a)
        w.complete_structure(f, a)
        f.planted, f.growth = True, 1.0
        farms.append(f)
    a.inventory.clear()
    for o in (b, c):
        o.x, o.y = a.x, a.y + 1
        o.plan = [{"do": "harvest", "target": farms[0].id}]
    assert _can_run(w, a, HARVEST_AND_STORE)  # (the second farm is nobody's)
    c.plan = [{"do": "harvest", "target": farms[1].id}]
    assert not _can_run(w, a, HARVEST_AND_STORE)


def test_a_chits_own_harvest_still_to_run_takes_its_farm():
    # (Codex on #113): asked ahead, the chit's own last steps run first and leave the only farm harvested
    w, a, b, farm = _farm_world()
    a.plan = [{"do": "harvest"}, {"do": "store", "what": "grain"}]
    assert not _can_run(w, a, HARVEST_AND_STORE)


def test_a_harvest_naming_its_farm_by_kind_takes_the_farm_the_step_would_find():
    # (Codex on #113): {"target": "farm"} is the nearest ripe farm to its harvester, not a farm called "farm"
    w, a, b, farm = _farm_world()
    b.plan = [{"do": "harvest", "target": "farm"}, {"do": "store", "what": "grain"}]
    assert not _can_run(w, a, HARVEST_AND_STORE)


def test_an_option_that_names_its_farm_needs_that_farm_free():
    # (Codex on #113, issue #128) the communal harvest names its farm: with that farm taken and another free, it was
    # still offered, and two chits went to one farm while the other stood ripe
    w, a, b, farm = _farm_world()
    pos = w.find_site("farm", a.x, a.y + 4, 10)
    other = w.place_site("farm", pos[0], pos[1], a)
    w.complete_structure(other, a)
    other.planted, other.growth = True, 1.0
    named = {"goal": "harvest", "steps": [{"do": "harvest", "target": farm.id}, {"do": "store", "what": "grain"}]}
    assert _can_run(w, a, named)
    b.plan = [{"do": "harvest", "target": farm.id}, {"do": "store", "what": "grain"}]
    assert not _can_run(w, a, named)  # the farm it names is taken...
    assert _can_run(w, a, HARVEST_AND_STORE)  # (...while a harvest with no farm named still finds the free one)
    other_named = {"goal": "harvest", "steps": [{"do": "harvest", "target": other.id}, {"do": "store", "what": "grain"}]}
    assert _can_run(w, a, other_named)
