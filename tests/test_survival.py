"""Winter survival fixes from the second audit (2026-09-28): chits froze at hut doors, starved under a waiting
reflex, flip-flopped between two full huts, and lost harvests to full hands."""

from chits.sim import actions
from chits.sim.world import World


def village(n=2, seed=1):
    w = World("A", "A", seed, "direct", 64, n)
    ags = list(w.agents.values())
    for a in ags:
        a.plan = []
        a.inventory.clear()
    return w, ags


def hut_for(w, a):
    a.learn("design:hut", "taught", w.tick)
    pos = w.find_site("hut", a.x, a.y)
    st = w.place_site("hut", pos[0], pos[1], a)
    w.complete_structure(st, a)
    return st


def test_sheltering_goes_inside_the_hut_not_to_its_door():
    w, (a, _) = village()
    hut = hut_for(w, a)
    a.home = hut.id
    # stand right beside the hut: that already counts as sheltered
    for x in range(hut.x - 1, hut.x + hut.w + 1):
        a.x, a.y = x, hut.y - 1
        if w.passable(a.x, a.y) and not w.in_home(a):
            break
    assert w.sheltered(a) and not w.in_home(a)
    w.weather = "snow"
    s = {}
    for _ in range(40):
        if actions._do_shelter(w, a, {"do": "shelter"}, s) != actions.RUNNING or w.in_home(a):
            break
    assert w.in_home(a)


def test_a_starving_chit_eats_even_while_waiting_out_the_weather():
    w, (a, _) = village()
    a.plan = [{"do": "shelter", "_reflex": True}]
    a.inventory["berries"] = 3
    a.hunger = 5.0
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "eat"
    a.plan = [{"do": "shelter", "_reflex": True}]
    a.hunger = 30.0  # hungry but not starving: the weather comes first
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "shelter"


def test_sleep_keeps_the_place_it_chose():
    w, (a, b) = village()
    hut = hut_for(w, b)
    a.home, a.energy = None, 5.0
    s = {}
    actions._do_sleep(w, a, {"do": "sleep"}, s)
    first = s.get("home")
    assert first == hut.id
    a.x += 1  # moving closer to somewhere else doesn't change its mind
    actions._do_sleep(w, a, {"do": "sleep"}, s)
    assert s.get("home") == first


def test_a_harvest_with_full_hands_leaves_the_rest_on_the_ground():
    w, (a, _) = village()
    a.learn("design:farm", "taught", w.tick)
    pos = w.find_site("farm", a.x, a.y)
    farm = w.place_site("farm", pos[0], pos[1], a)
    w.complete_structure(farm, a)
    farm.planted, farm.growth = True, 1.0
    a.inventory.update({"wood": 5, "stone": 3, "fiber": 2})  # 10 of 12
    s = {}
    note = ""
    for _ in range(200):
        r = actions._do_harvest(w, a, {"do": "harvest"}, s)
        if r != actions.RUNNING:
            note = s.get("note", r)
            break
    ground = sum(p.get("grain", 0) + p.get("seeds", 0) for _, _, p in w.piles_near(a.x, a.y, 1))
    assert a.inventory.get("grain", 0) + a.inventory.get("seeds", 0) + ground == 8, (note, a.inventory)
    assert "on the ground" in note


def test_eat_with_empty_hands_fetches_food_nearby():
    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = 40.0
    w.structures.clear()  # no stockpile to take from
    w.put_ground(a.x + 3, a.y, "berries", 2)
    a.plan = [{"do": "eat"}]
    for _ in range(200):
        w.step(lambda world, ag: None)
        if not a.plan:
            break
    assert a.hunger > 40.0, a.last_result
    assert "no food" not in (a.last_result or "")


def test_help_fetches_from_a_stockpile_further_than_a_few_tiles():
    from chits.sim.actions import DONE, RUNNING, advance

    for gap in (3, 6, 11):
        w = World("A", "A", 5, "direct", 64, 1)
        a = next(iter(w.agents.values()))
        a.inventory.clear()
        w.structures.clear()
        w.occupied.clear()
        site_xy = w.find_site("campfire", a.x, a.y)
        site = w.place_site("campfire", site_xy[0], site_xy[1], a)
        pile_xy = w.find_site("stockpile", site.x + gap, site.y, 4)
        pile = w.place_site("stockpile", pile_xy[0], pile_xy[1], a)
        w.complete_structure(pile, a)
        pile.storage.update({"wood": 20, "stone": 20})
        step = {"do": "help", "site": site.id}
        r = RUNNING
        for _ in range(900):
            r = advance(w, a, step)
            if r != RUNNING:
                break
            w.tick += 1
        assert r == DONE and site.complete, (gap, r, site.needs)


def _pair_ready_to_breed(w):
    a, b = list(w.agents.values())[:2]
    spot = w.find_site("hut", a.x, a.y)
    hut = w.place_site("hut", spot[0], spot[1], a)
    w.complete_structure(hut, a)
    for x in (a, b):
        x.hunger, x.health, x.home, x.last_birth_tick = 90.0, 100.0, hut.id, -10 ** 6
        x.x, x.y = hut.x, hut.y
    a.affinity[b.id] = b.affinity[a.id] = 60.0
    return a, b


def test_no_children_between_parent_and_child_or_siblings():
    for relation in ("parent", "sibling", "none"):
        w = World("A", "A", 5, "direct", 64, 3)
        a, b = _pair_ready_to_breed(w)
        c = list(w.agents.values())[2]
        if relation == "parent":
            b.parents = (a.id, c.id)
        elif relation == "sibling":
            a.parents = b.parents = (c.id, "someone")
        born = 0
        for _ in range(40):  # births are a coin flip each try
            n = len(w.agents)
            w._births()
            born += len(w.agents) - n
            a.last_birth_tick = b.last_birth_tick = -10 ** 6
            if born:
                break
        assert (born > 0) == (relation == "none"), relation


def test_a_hut_keeps_a_sleeper_warm_on_a_winter_night():
    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    spot = w.find_site("hut", a.x, a.y)
    hut = w.place_site("hut", spot[0], spot[1], a)
    w.complete_structure(hut, a)
    a.x, a.y = next(c for c in hut.cells())
    a.activity, a.warmth = "sleeping", 60.0
    assert w.in_home(a)
    for _ in range(60):
        w._needs(a, -0.21)  # an ordinary winter night
    assert a.warmth >= 60.0
    a.warmth = 60.0
    for _ in range(60):
        w._needs(a, -0.38)  # a winter storm: a hut is not enough
    assert a.warmth < 60.0


def test_a_hungry_chit_puts_down_spare_tools_to_carry_food():
    from chits.sim.actions import _drop_for_room

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.add("stone_pick", 6)
    a.add("spear", 3)
    free = a.free_space()
    _drop_for_room(w, a, free + 3)
    assert a.inventory.get("stone_pick") == 1 or a.inventory.get("spear") == 1
    assert a.inventory.get("stone_pick", 0) >= 1 and a.inventory.get("spear", 0) >= 1  # one of each is kept
    assert sum(n for k, p in w.ground.items() for i, n in p.items() if i != "_t") > 0  # dropped, not destroyed


def test_abandoned_and_unreachable_sites():
    from chits.sim.actions import advance
    from chits.sim.agent import TICKS_PER_DAY
    from chits.sim.world import SITE_IDLE_DAYS

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    spot = w.find_site("hut", a.x, a.y)
    site = w.place_site("hut", spot[0], spot[1], a)
    site.builders[a.id] = 3  # begun, then left
    w.tick += TICKS_PER_DAY * (SITE_IDLE_DAYS + 1)
    w._structure_tick(site, False)
    assert site.id not in w.structures
    # a site the chit can't get to is not chosen again for a day
    site2 = w.place_site("hut", spot[0], spot[1], a)
    import chits.sim.actions as ACT
    real = ACT._goto_structure
    ACT._goto_structure = lambda *args: "blocked"
    try:
        r = advance(w, a, {"do": "help", "site": site2.id})
    finally:
        ACT._goto_structure = real
    assert "couldn't reach" in r and a.reflex_rest.get("unreach:" + site2.id, 0) > w.tick
    from chits.brain.instinct import _reachable
    assert not _reachable(w, a, site2)


def _run(w, a, step, ticks=400):
    from chits.sim.actions import RUNNING, advance
    r = RUNNING
    for _ in range(ticks):
        r = advance(w, a, step)
        if r != RUNNING:
            return r
        w.tick += 1
    return r


def _pile(w, a, dx=3, storage=None):
    xy = w.find_site("stockpile", a.x + dx, a.y, 5)
    p = w.place_site("stockpile", xy[0], xy[1], a)
    w.complete_structure(p, a)
    p.storage.update(storage or {})
    return p


def test_store_picks_a_stockpile_with_room():
    from chits.sim.actions import DONE, STOCKPILE_CAP

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    full = _pile(w, a, 2, {"stone": STOCKPILE_CAP})
    roomy = _pile(w, a, 8)
    a.inventory.clear(); a.add("wood", 4)
    assert _run(w, a, {"do": "store", "what": "wood"}) == DONE
    assert roomy.storage.get("wood") == 4 and "wood" not in full.storage


def test_plant_fetches_seeds_from_a_stockpile():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    pile = _pile(w, a, 3, {"seeds": 10})
    xy = w.find_site("farm", a.x - 4, a.y, 5)
    farm = w.place_site("farm", xy[0], xy[1], a)
    w.complete_structure(farm, a)
    farm.planted = False
    a.inventory.clear()
    assert _run(w, a, {"do": "plant"}) == DONE
    assert farm.planted and pile.storage.get("seeds", 0) < 10


def test_teach_all_finds_someone_who_doesnt_know():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 3)
    a, b, c = list(w.agents.values())[:3]
    a.learn("recipe:cord", "discovered", w.tick)
    b.x, b.y = a.x + 1, a.y
    c.x, c.y = a.x + 2, a.y
    b.learn("recipe:cord", "discovered", w.tick)
    b.activity = c.activity = "resting"
    assert _run(w, a, {"do": "teach", "to": "all", "what": "cord"}) == DONE
    assert "recipe:cord" in c.knows


def test_give_to_a_stockpile_stores_it():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    pile = _pile(w, a, 3)
    a.inventory.clear(); a.add("seeds", 3)
    assert _run(w, a, {"do": "give", "to": pile.id, "what": "seeds", "qty": 3}) == DONE
    assert pile.storage.get("seeds") == 3


def test_failure_messages_say_what_to_do():
    from chits.sim.actions import DONE, advance

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("farm", a.x + 3, a.y, 5)
    farm = w.place_site("farm", xy[0], xy[1], a)
    w.complete_structure(farm, a)
    farm.planted, farm.growth = True, 0.4
    step = {"do": "harvest"}
    assert advance(w, a, step) == DONE and "40% grown" in step["_s"]["note"]  # a note, not a plan-ending failure
    assert "harvest a ripe farm" in advance(w, a, {"do": "gather", "what": "grain"})


def test_local_names_work_in_steps():
    from chits.sim.actions import _knowledge_key

    w = World("B", "B", 5, "direct", 64, 1)
    w.culture_names["recipe:sharp_stone"] = "stoneaxe"
    assert w.norm_item("stoneaxe") == "sharp_stone" and w.norm_item("StoneAxe") == "sharp_stone"
    assert _knowledge_key("stoneaxe", w) == "recipe:sharp_stone"


def test_sites_are_placed_on_land_the_chit_can_walk_to():
    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    comp = w._components()
    mine = comp[a.y * w.w + a.x]
    for design in ("hut", "farm", "campfire"):
        pos = w.find_site(design, a.x, a.y, 16, reach=(a.x, a.y))
        assert pos and comp[pos[1] * w.w + pos[0]] == mine


def test_a_reply_say_answers_whoever_spoke():
    import asyncio
    from chits.brain.mind import Mind

    w = World("A", "A", 5, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    a.spoken_to = {"id": b.id, "name": b.name, "text": "hi", "tick": w.tick}
    m = Mind(None)
    m.upsert({"id": "x", "base_url": "http://127.0.0.1:9/v1"})
    m.assign(w, "x")
    m.brains["x"].healthy = lambda: True
    a.pending_plan = {"steps": [{"do": "rest"}], "goal": "g", "say": "Hello back"}
    a.plan = []
    m.hook(w, a)
    say = {k: v for k, v in a.plan[0].items() if not k.startswith("_")}  # (its bookkeeping: provenance.py)
    assert say == {"do": "say", "to": b.name, "text": "Hello back"} and a.plan[0]["_origin"] == "model_generated"
    asyncio.run(m.close())


def test_a_cut_off_reply_keeps_its_complete_steps():
    from chits.brain.parse import parse_plan

    cut = '{"thought":"t","goal":"g","plan":[{"do":"gather","what":"wood","qty":3},{"do":"build","what":"hut","qty"'
    p = parse_plan(cut)
    assert p["steps"][0]["do"] == "gather" and p["steps"][1] == {"do": "build", "what": "hut"}


def test_neighbours_come_to_know_each_other():
    w = World("A", "A", 5, "direct", 64, 3)
    a, b, c = list(w.agents.values())[:3]
    homes = []
    for i, ch in enumerate((a, b, c)):
        xy = w.find_site("hut", a.x + (i * 4 if i < 2 else 30), a.y, 6)
        h = w.place_site("hut", xy[0], xy[1], ch)
        w.complete_structure(h, ch)
        ch.home = h.id
        homes.append(h)
    near = max(abs(homes[0].x - homes[1].x), abs(homes[0].y - homes[1].y)) <= 10
    far = max(abs(homes[0].x - homes[2].x), abs(homes[0].y - homes[2].y)) > 10
    before_ab, before_ac = a.affinity.get(b.id, 0), a.affinity.get(c.id, 0)
    for _ in range(10):
        w._neighbours()
    assert near and a.affinity.get(b.id, 0) >= before_ab + 10
    if far:
        assert a.affinity.get(c.id, 0) == before_ac


def test_a_starving_chit_goes_to_the_nearest_food():
    from chits.sim.actions import _food_reflex

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("stockpile", a.x + 25, a.y, 6)
    pile = w.place_site("stockpile", xy[0], xy[1], a)
    w.complete_structure(pile, a)
    pile.storage["berries"] = 20
    w.put_ground(a.x + 2, a.y, "berries", 3)
    assert _food_reflex(w, a) == {"do": "pickup", "what": "berries"}  # 2 tiles beats a pile 25 tiles off
    w.ground.clear()
    far_pick = _food_reflex(w, a)
    assert far_pick["do"] in ("eat", "gather")


def test_an_unreachable_pile_sends_a_hungry_chit_foraging():
    import chits.sim.actions as ACT

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("stockpile", a.x + 6, a.y, 6)
    pile = w.place_site("stockpile", xy[0], xy[1], a)
    w.complete_structure(pile, a)
    pile.storage["berries"] = 20
    w.put_ground(a.x + 1, a.y, "berries", 2)
    real = ACT._goto_structure
    ACT._goto_structure = lambda *args: "blocked"
    try:
        r = ACT.advance(w, a, {"do": "eat"})
    finally:
        ACT._goto_structure = real
    assert r == ACT.RUNNING and a.reflex_rest.get("unreach:" + pile.id, 0) > w.tick
    assert ACT._stockpile_with(w, a, ACT.FOODS, 30) is None  # not chosen again for a while


def test_an_exhausted_chit_sleeps_where_it_drops():
    from chits.sim.actions import advance

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("hut", a.x + 20, a.y, 8)
    hut = w.place_site("hut", xy[0], xy[1], a)
    w.complete_structure(hut, a)
    a.home, a.energy, a.hunger = hut.id, 2.0, 80.0
    start = (a.x, a.y)
    advance(w, a, {"do": "sleep"})
    assert a.activity == "sleeping" and (a.x, a.y) == start
    a.energy = 60.0  # merely tired: it walks home to sleep
    advance(w, a, {"do": "sleep"})
    assert a.activity != "sleeping"


def test_picking_up_food_with_full_hands_makes_room():
    from chits.sim.actions import DONE, advance

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    while a.free_space() >= 1:
        a.add("stone", 1)
    w.put_ground(a.x, a.y, "grain", 3)
    assert advance(w, a, {"do": "pickup", "what": "grain"}) == DONE
    assert a.inventory.get("grain", 0) >= 1


def test_a_failed_reflex_rests_instead_of_repeating_every_tick():
    from chits.sim import actions as ACT

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    w.structures.clear(); w.occupied.clear()
    w.ground.clear()
    a.hunger = 10.0
    a.plan = [{"do": "pickup", "what": "grain", "_reflex": True}]  # nothing lying here: it fails
    ACT.run(w, a)
    assert a.reflex_rest.get("food", 0) > w.tick
    a.plan = [{"do": "rest"}]
    ACT.reflexes(w, a)
    assert a.plan[0].get("do") == "rest"  # the food reflex waits its turn


def test_a_harvester_sows_the_plot_again():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("farm", a.x + 3, a.y, 5)
    farm = w.place_site("farm", xy[0], xy[1], a)
    w.complete_structure(farm, a)
    farm.planted, farm.growth = True, 1.0
    assert _run(w, a, {"do": "harvest"}) == DONE
    assert a.inventory.get("grain") == 6 and farm.planted and farm.growth == 0.0


def test_a_hungry_chit_eats_what_it_carries_and_is_told_it_is_hungry():
    from chits.brain import prompt as P
    from chits.sim import actions as ACT

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear(); a.add("berries", 3)
    a.hunger = 38.0
    a.plan = [{"do": "build", "what": "hut"}]
    ACT.reflexes(w, a)
    assert a.plan[0] == {"do": "eat", "_reflex": True}
    assert "Hunger 38/100 (hungry)" in P.scene(w, a)
    a.plan = [{"do": "build", "what": "hut"}]
    a.hunger = 50.0
    ACT.reflexes(w, a)
    assert a.plan[0]["do"] == "build"


def test_instinct_does_not_overshoot_its_stockpile_cap():
    from chits.sim.actions import DONE, advance

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.learn("design:stockpile", "taught", w.tick)
    for i in range(5):
        xy = w.find_site("stockpile", a.x + 6 * (i - 2), a.y + 12, 6)
        w.complete_structure(w.place_site("stockpile", xy[0], xy[1], a), a)
    n = len(w.structures)
    assert advance(w, a, {"do": "build", "what": "stockpile", "_cap": 5}) == DONE
    assert len(w.structures) == n


def test_a_dwindling_play_world_draws_wanderers(tmp_path):
    import asyncio
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="single")
    w = rt.worlds["A"]
    for a in list(w.agents.values())[5:]:
        w.kill(a, "old age")
    assert len(w.agents) == 5
    brain = next(iter(w.agents.values())).brain
    while w.tick % 240:
        rt.step_worlds()
    for _ in range(240 * 4):
        rt.step_worlds()
    assert len(w.agents) >= 6
    new = [a for a in w.agents.values() if any("wandered out of the wilds" in m.text for m in a.memories)]
    assert new and all(a.brain == brain and not a.parents for a in new)
    assert any(e.kind == "arrival" for e in w.events)
    asyncio.run(rt.mind.close())


def test_an_experiment_never_draws_wanderers(tmp_path):
    import asyncio
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="single", contract="experiment")
    w = rt.worlds["A"]
    for a in list(w.agents.values())[5:]:
        w.kill(a, "old age")
    for _ in range(240 * 4):
        rt.step_worlds()
    assert not any("wandered out of the wilds" in m.text for a in w.agents.values() for m in a.memories)
    assert not any(e.kind == "arrival" for e in w.events)
    asyncio.run(rt.mind.close())


def test_store_with_no_stockpile_keeps_the_plan_going():
    from chits.sim.actions import run

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    a.inventory.clear(); a.add("grain", 3)
    a.plan = [{"do": "store", "what": "grain"}, {"do": "rest"}]
    run(w, a)
    assert a.plan and a.plan[0]["do"] == "rest" and a.inventory.get("grain") == 3


def test_store_moves_on_to_a_pile_with_room():
    from chits.sim.actions import DONE, STOCKPILE_CAP, GOODS_SHARE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    full = _pile(w, a, 2, {"stone": int(STOCKPILE_CAP * GOODS_SHARE)})
    roomy = _pile(w, a, 9)
    a.inventory.clear(); a.add("wood", 4)
    assert _run(w, a, {"do": "store", "what": "wood", "target": full.id}) == DONE
    assert roomy.storage.get("wood") == 4
    roomy.storage["stone"] = int(STOCKPILE_CAP * GOODS_SHARE)
    a.add("wood", 2)
    assert _run(w, a, {"do": "store", "what": "wood", "target": full.id}) == DONE  # all full: keeps its things
    assert a.inventory.get("wood") == 2


def test_plant_gathers_wild_seeds_when_no_store_has_any():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    assert w.nearest_resource(a.x, a.y, "seeds", 20)
    xy = w.find_site("farm", a.x + 3, a.y, 5)
    farm = w.place_site("farm", xy[0], xy[1], a)
    w.complete_structure(farm, a)
    farm.planted = False
    a.inventory.clear()
    assert _run(w, a, {"do": "plant"}, 900) == DONE
    assert farm.planted


def test_building_next_to_one_of_the_same_uses_it_instead():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    for d in ("campfire", "farm", "kiln"):
        a.learn(f"design:{d}", "taught", w.tick)
    xy = w.find_site("campfire", a.x + 2, a.y, 4)
    fire = w.place_site("campfire", xy[0], xy[1], a)
    w.complete_structure(fire, a)
    fire.fuel = 0.0
    a.inventory.clear(); a.add("wood", 4)
    n = len(w.structures)
    assert _run(w, a, {"do": "build", "what": "campfire"}) == DONE
    assert len(w.structures) == n and fire.fuel > 0  # relit, not a second fire
    xy = w.find_site("farm", a.x - 4, a.y, 5)
    farm = w.place_site("farm", xy[0], xy[1], a)
    w.complete_structure(farm, a)
    farm.planted = False
    a.add("seeds", 2)
    n = len(w.structures)
    assert _run(w, a, {"do": "build", "what": "farm"}) == DONE
    assert len(w.structures) == n and farm.planted  # sown, not a second farm
    xy = w.find_site("kiln", a.x, a.y + 5, 5)
    w.complete_structure(w.place_site("kiln", xy[0], xy[1], a), a)
    n = len(w.structures)
    assert _run(w, a, {"do": "build", "what": "kiln"}) == DONE and len(w.structures) == n


def test_harvesting_an_empty_farm_sows_it():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("farm", a.x + 3, a.y, 5)
    farm = w.place_site("farm", xy[0], xy[1], a)
    w.complete_structure(farm, a)
    farm.planted = False
    a.inventory.clear(); a.add("seeds", 2)
    assert _run(w, a, {"do": "harvest"}) == DONE
    assert farm.planted and not a.has("seeds")


def test_a_village_stops_at_a_sensible_number_of_stockpiles():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 128, 12)
    a = next(iter(w.agents.values()))
    a.learn("design:stockpile", "taught", w.tick)
    w.structures.clear(); w.occupied.clear()
    for i in range(6):  # six full ones, far from this chit
        xy = w.find_site("stockpile", a.x + 30 + (i % 3) * 5, a.y + 20 + (i // 3) * 5, 6)
        p = w.place_site("stockpile", xy[0], xy[1], a)
        w.complete_structure(p, a)
    n = len(w.structures)
    assert advance_until_done(w, a, {"do": "build", "what": "stockpile"}) == DONE and len(w.structures) == n


def advance_until_done(w, a, step):
    return _run(w, a, step)


def test_gathering_a_made_thing_takes_it_from_the_stockpile():
    from chits.sim.actions import DONE

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    pile = _pile(w, a, 3, {"brick": 8})
    a.inventory.clear()
    assert _run(w, a, {"do": "gather", "what": "brick", "qty": 3}) == DONE
    assert a.inventory.get("brick") == 3 and pile.storage["brick"] == 5


def test_stored_bricks_become_a_brick_house_plan():
    import random
    from chits.brain.instinct import Instinct

    w = World("A", "A", 5, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    _pile(w, a, 3, {"brick": 14})
    a.learn("design:brick_house", "taught", w.tick)
    a.hunger = a.energy = a.warmth = 100.0
    goals = {Instinct()._progress(w, a, random.Random(i))["goal"] for i in range(60)}
    assert "build a brick house" in goals


def test_the_prompt_says_what_tools_and_buildings_are_for():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear(); a.add("stone_pick", 1)
    a.learn("design:road", "taught", w.tick)
    a.learn("design:boat", "taught", w.tick)
    sc = P.scene(w, a)
    assert "stone pick (needed for copper ore" in sc
    assert "walking on roads is much faster" in sc
    assert "boat (" not in sc  # no contact between islands: a boat goes nowhere


def test_a_campfire_left_cold_is_cleared_away():
    from chits.sim.agent import TICKS_PER_DAY
    from chits.sim.world import ASHES_DAYS

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    xy = w.find_site("campfire", a.x, a.y)
    fire = w.place_site("campfire", xy[0], xy[1], a)
    w.complete_structure(fire, a)
    fire.fuel = 0.0
    w._structure_tick(fire, False)
    assert fire.id in w.structures and fire.out_since == w.tick
    w.tick += TICKS_PER_DAY * ASHES_DAYS - 1
    w._structure_tick(fire, False)
    assert fire.id in w.structures  # relit in time, it would have stayed
    w.tick += 2
    w._structure_tick(fire, False)
    assert fire.id not in w.structures


def test_a_home_slept_in_stays_in_repair():
    from chits.sim.actions import advance

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("hut", a.x, a.y)
    hut = w.place_site("hut", xy[0], xy[1], a)
    w.complete_structure(hut, a)
    hut.durability = 50.0
    a.home = hut.id
    a.x, a.y = next(iter(hut.cells()))
    a.energy, a.hunger = 10.0, 90.0
    step = {"do": "sleep"}
    for _ in range(200):
        advance(w, a, step)
        w.tick += 1
    assert hut.durability > 55.0


def test_an_armed_chit_drives_off_a_wolf():
    from chits.sim import animals as AN

    def night_attack(armed, seed):
        w = World("A", "A", seed, "direct", 64, 1)
        c = next(iter(w.agents.values()))
        c.inventory.clear()
        if armed:
            c.add("spear", 1)
        w.tick = 240 * 5 + 230  # late at night
        assert w.is_night
        w.animals = {"w1": {"id": "w1", "kind": "wolf", "x": c.x + 1, "y": c.y, "tame": False}}
        c.health = 100.0
        AN.attacks(w)
        return c.health, w.animals["w1"], [e for e in w.events if e.kind == "wolf_driven_off"]

    drove = sum(1 for s in range(20) if night_attack(True, s)[2])
    assert 6 <= drove <= 18  # usually, not always
    for s in range(5):
        hp, wolf, ev = night_attack(False, s)
        assert hp < 100.0 and not ev  # unarmed: bitten


def test_mealtime_a_hungry_chit_eats_from_the_stores_nearby():
    from chits.sim import actions as ACT

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    a.inventory.clear()
    _pile(w, a, 4, {"grain": 20})
    a.hunger = 30.0
    a.plan = [{"do": "build", "what": "hut"}]
    ACT.reflexes(w, a)
    assert a.plan[0] == {"do": "eat", "_reflex": True}
    a.plan, a.hunger = [{"do": "build", "what": "hut"}], 60.0
    ACT.reflexes(w, a)
    assert a.plan[0]["do"] == "build"
