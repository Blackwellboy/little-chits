"""Bigger homes, the bridge and the useful buildings (sim/buildings.py): each one does what its blurb says."""

import random

from chits.brain import builder as BI
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import actions
from chits.sim import animals as AN
from chits.sim import buildings as BLD
from chits.sim import terrain as T
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS, ITEMS, RECIPES, match_recipe, normalize_design
from chits.sim.world import World

NEW = ("longhouse", "two_storey_house", "bridge", "well", "granary", "mill", "smithy", "watchtower", "school",
       "bell_tower")


class Lucky:
    """An rng for instinct that always rolls low (so a plan that happens 'sometimes' happens now)."""

    def random(self):
        return 0.01

    def choice(self, seq):
        return seq[0]


def village(n=2, seed=1, size=64):
    w = World("A", "A", seed, "direct", size, n)
    ags = list(w.agents.values())
    for a in ags:
        a.plan = []
        a.inventory.clear()
        a.hunger = a.energy = a.warmth = a.health = 90.0
    return w, ags


def put(w, design, a, near=None, radius=7):
    """A finished building of this design near (x, y)."""
    x, y = near or (a.x, a.y)
    pos = w.find_site(design, x, y, radius)
    st = w.place_site(design, pos[0], pos[1], a)
    w.complete_structure(st, a)
    return st


def run_step(w, a, step, limit=3000):
    res = actions.RUNNING
    for _ in range(limit):
        w.tick += 1
        res = actions.advance(w, a, step)
        if res != actions.RUNNING:
            break
    return res


def test_every_new_building_has_an_idea_a_blurb_and_a_name():
    for k in NEW:
        d = DESIGNS[k]
        assert d.blurb and d.prereqs and d.work > 0, k
        assert normalize_design(d.name) == k, k
    assert normalize_design("granary") == "granary" and normalize_design("mill") == "mill"
    assert normalize_design("two story house") == "two_storey_house"
    w, (a, _) = village()
    assert not a.knows_design("longhouse")
    a.learn("recipe:cord", "discovered", w.tick)
    w.check_insights(a)  # knowing the hut and cord sparks the longhouse
    assert a.knows_design("longhouse") and a.knows_design("bridge") is False  # a bridge also needs the stone axe


def test_homes_hold_more_and_the_two_storey_house_is_warm():
    assert BLD.HOME_CAP["longhouse"] == 6 and BLD.HOME_CAP["two_storey_house"] == 8
    assert "two_storey_house" in BLD.WARM_HOMES and "longhouse" in BLD.HOMES
    w, (a, _) = village()
    h = put(w, "two_storey_house", a)
    a.x, a.y = h.x, h.y
    assert w.in_home(a) is h and w.sheltered(a)
    a.warmth = 50.0
    w._needs(a, -0.6)  # a winter storm night: a hut lets the cold in, this house doesn't
    assert a.warmth > 50.0


def test_mill_grinds_grain_and_a_loaf_is_more_filling_than_bread():
    assert match_recipe({"grain": 1}, "mill").key == "flour"
    assert match_recipe({"grain": 1}, None) is None
    assert match_recipe({"flour": 2}, "fire").key == "loaf"
    assert ITEMS["loaf"].food > ITEMS["bread"].food and "loaf" in actions.FOODS
    w, (a, _) = village()
    mill = put(w, "mill", a)
    assert "mill" in mill.stations()
    a.x, a.y = next(iter(w.stand_tiles_for_structure(mill)))
    a.inventory["grain"] = 1
    w.tick += 1
    assert run_step(w, a, {"do": "experiment", "with": ["grain"], "at": "mill"}) == actions.DONE
    assert a.knows_recipe("flour") and a.inventory.get("flour") == 1


def grass(w, a, r):
    """Open grassland around the chit, so nothing in the way depends on the map."""
    for y in range(max(0, a.y - r), min(w.h, a.y + r + 1)):
        for x in range(max(0, a.x - r), min(w.w, a.x + r + 1)):
            i = y * w.w + x
            w.tiles[i], w.res_kind[i], w.res_amt[i] = T.GRASS, 0, 0
    w.rebuild_block()


def _farm(w, a, near, radius=3):
    f = put(w, "farm", a, near, radius)
    f.planted, f.growth = True, 0.0
    return f


def test_a_well_waters_farms_within_6_tiles_and_rests_the_tired():
    w, (a, b) = village()
    grass(w, a, 24)
    w.weather = "clear"
    well = put(w, "well", a)
    near = _farm(w, a, (well.x + 3, well.y))
    far = _farm(w, a, (well.x + 18, well.y))
    assert BLD.gap(near, well) <= 6 < BLD.gap(far, well)
    w.tick += 1
    for _ in range(100):
        w._structure_tick(near, False)
        w._structure_tick(far, False)
    assert abs(near.growth / far.growth - 1.3) < 0.01
    # rest: two sleepers out in the open, one beside the well
    for c in (a, b):
        c.activity, c.energy = "sleeping", 20.0
    a.x, a.y = next(iter(w.stand_tiles_for_structure(well)))
    b.x, b.y = next(iter(w.stand_tiles_for_structure(far)))
    w._needs(a, 0.6)
    w._needs(b, 0.6)
    assert a.energy - 20.0 > 1.25 * (b.energy - 20.0)


def test_stored_food_rots_unless_a_granary_is_near_or_pots_hold_it():
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    pile.storage = {"berries": 100, "wood": 20}
    w.tick += 1
    BLD._spoil(w)
    assert pile.storage == {"berries": 98, "wood": 20}  # 2% of the food, none of the wood
    pile.storage = {"berries": 100, "pot": 10}  # ten pots keep a hundred fresh
    BLD._spoil(w)
    assert pile.storage["berries"] == 100
    pile.storage = {"fish": 30, "grain": 70}
    put(w, "granary", a, (pile.x, pile.y))
    w.tick += 1
    for _ in range(5):
        BLD._spoil(w)
    assert pile.storage == {"fish": 30, "grain": 70}
    assert BLD.keeps_fresh(w, pile)


def test_the_most_perishable_food_rots_first():
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    pile.storage = {"grain": 150, "meat": 50}
    w.tick += 1
    BLD._spoil(w)
    assert pile.storage == {"grain": 150, "meat": 46}  # raw meat goes off before dry grain


def test_a_smithy_makes_metal_tools_twice_as_fast():
    def ticks_to_make(design):
        w, (a, _) = village()
        st = put(w, design, a)
        a.learn("recipe:copper_axe", "discovered", w.tick)
        a.x, a.y = next(iter(w.stand_tiles_for_structure(st)))
        a.inventory.update({"copper": 1, "wood": 1})
        w.tick += 1
        s = {}
        for n in range(1, 200):
            actions._do_craft(w, a, {"do": "craft", "what": "copper_axe"}, s)
            if a.has("copper_axe"):
                return n
        raise AssertionError("never made it")

    at_smithy, at_workshop = ticks_to_make("smithy"), ticks_to_make("workshop")
    assert at_smithy * 2 <= at_workshop + 1, (at_smithy, at_workshop)
    assert "workshop" in DESIGNS["smithy"].station


def _night(w):
    w.tick = TICKS_PER_DAY * 4 + 20  # 2 am
    assert w.is_night


def test_a_watchtower_drives_wolves_off_and_stops_their_bites():
    for tower in (False, True):
        w, (a, _) = village()
        grass(w, a, 12)
        w.animals.clear()
        if tower:
            tw = put(w, "watchtower", a)
            a.x, a.y = next(iter(w.stand_tiles_for_structure(tw)))
        _night(w)
        wolf = AN._add(w, "wolf", a.x + 4, a.y)
        for _ in range(3):
            AN.move(w)
        d = max(abs(wolf["x"] - a.x), abs(wolf["y"] - a.y))
        assert (d > 4) if tower else (d < 4), (tower, d)
        wolf["x"], wolf["y"] = a.x + 1, a.y
        a.health = 80.0
        AN.attacks(w)
        assert (a.health == 80.0) if tower else (a.health < 80.0)
    assert any(e.kind == "wolf" and e.data.get("driven_off") for e in w.events)


def test_children_near_a_school_learn_what_the_grown_ups_know():
    for school in (False, True):
        w, (kid, adult) = village()
        kid.born = w.tick - TICKS_PER_DAY  # a day old
        kid.knows = {k: v for k, v in kid.knows.items() if not k.startswith("recipe:")}
        adult.learn("recipe:cord", "discovered", w.tick)
        if school:
            sc = put(w, "school", adult)
            kid.x, kid.y = adult.x, adult.y = next(iter(w.stand_tiles_for_structure(sc)))
        for _ in range(40):
            w.tick += 1
            BLD._school(w)
        assert kid.knows_recipe("cord") == school


def test_the_bell_gathers_everyone_near_and_shares_the_chiefs_plan():
    w, (chief, other) = village()
    bell = put(w, "bell_tower", chief)
    for c in (chief, other):
        c.x, c.y = next(iter(w.stand_tiles_for_structure(bell)))
        c.mood = 40.0
    w.leader, chief.objective, other.objective = chief.id, "store food for winter", ""
    w.tick = TICKS_PER_DAY * 2 + BLD.BELL_TICK
    BLD.step(w)
    assert chief.mood == other.mood == 48.0
    assert other.objective == "store food for winter"
    assert any(e.kind == "bell" for e in w.events)


def _roomy_hut(w, a):
    """A hut on ground with room to grow into a longhouse."""
    pos = w.find_site("longhouse", a.x, a.y, 10)
    hut = w.place_site("hut", pos[0], pos[1], a)
    w.complete_structure(hut, a)
    return hut


def test_upgrading_a_hut_into_a_longhouse_keeps_everyone_living_there():
    w, ags = village(4)
    a = ags[0]
    hut = _roomy_hut(w, a)
    for c in ags[:4]:
        c.home = hut.id
    a.learn("design:longhouse", "taught", w.tick)
    a.inventory.update({"wood": 8, "cord": 4, "stone": 6})  # the hut's own 8 wood go into the new walls
    assert BLD.salvage_needs("hut", "longhouse") == {"wood": 8, "cord": 4, "stone": 6}
    assert run_step(w, a, {"do": "upgrade", "to": "longhouse"}) == actions.DONE
    assert w.structures[hut.id] is hut and hut.design == "longhouse" and (hut.w, hut.h) == (3, 2)
    assert all(c.home == hut.id for c in ags[:4]) and not hut.upgrade
    assert all(w.occupied[cy * w.w + cx] == hut.id for cx, cy in hut.cells())
    assert BLD.birth_home(w, ags[0], ags[1])[1] == 1.0  # four in a home for six: room for a child again
    assert any(e.kind == "built" and e.data.get("upgraded_from") == "hut" for e in w.events)


def test_building_a_bigger_home_beside_your_own_upgrades_it_instead():
    w, ags = village(2)
    a = ags[0]
    hut = _roomy_hut(w, a)
    a.home = hut.id
    a.learn("design:brick_house", "taught", w.tick)
    a.inventory.update({"brick": 12})
    n = len(w.structures)
    assert run_step(w, a, {"do": "build", "what": "brick_house"}) == actions.DONE
    assert len(w.structures) == n and hut.design == "brick_house" and a.home == hut.id


def test_an_upgrade_waits_for_its_materials_and_others_can_help():
    w, (a, b) = village()
    hut = _roomy_hut(w, a)
    a.home = b.home = hut.id
    a.learn("design:longhouse", "taught", w.tick)
    assert run_step(w, a, {"do": "upgrade"}) == actions.DONE  # nothing to bring: it starts, and waits
    assert hut.upgrade["to"] == "longhouse" and hut.design == "hut"
    b.inventory.update({"wood": 8, "cord": 4, "stone": 6})
    assert run_step(w, b, {"do": "help", "site": hut.id}) == actions.DONE  # b doesn't know longhouses; it helps
    assert hut.design == "longhouse"


def test_a_crowded_home_has_fewer_children():
    w, ags = village(6)
    hut = put(w, "hut", ags[0])
    for c in ags[:2]:
        c.home = hut.id
    assert BLD.birth_home(w, ags[0], ags[1]) == (hut, 1.0)
    ags[2].home = hut.id  # full
    assert BLD.birth_home(w, ags[0], ags[1])[1] == 0.5
    ags[3].home = ags[4].home = hut.id  # two past full
    assert BLD.birth_home(w, ags[0], ags[1])[1] == 0.0
    a, b = ags[0], ags[1]
    for x, y in ((a, b), (b, a)):
        x.like(y.id, 60)
        x.born = w.tick - 10 * TICKS_PER_DAY
    b.x, b.y = a.x, a.y
    born = len(w.agents)
    for _ in range(30):
        w.tick += 1
        w._births()
    assert len(w.agents) == born  # five in a hut for three: no child


def _split(w, a):
    """Cut the island in two with a channel of shallow water two tiles wide, 3 tiles east of the chit."""
    cx = a.x + 3
    for y in range(w.h):
        for x in range(a.x - 2, cx + 5):
            i = y * w.w + x
            water = x in (cx, cx + 1)
            if water or abs(y - a.y) <= 3:
                w.tiles[i] = T.SHALLOW if water else T.GRASS
                w.res_kind[i], w.res_amt[i] = 0, 0
    w.rebuild_block()
    return cx


def test_a_bridge_makes_the_far_bank_reachable():
    w, (a, _) = village(seed=3)
    cx = _split(w, a)
    far = w.place_site("campfire", cx + 3, a.y, a)
    assert not w.same_land(a, far) and w.find_path(a.x, a.y, {(cx + 3, a.y)}) is None
    a.learn("design:bridge", "taught", w.tick)
    a.inventory.update({"wood": 10, "cord": 3})
    assert run_step(w, a, {"do": "build", "what": "bridge"}) == actions.DONE
    br = next(s for s in w.structures.values() if s.design == "bridge")
    assert br.complete and (br.w, br.h) == (2, 1) and all(w.tiles[y * w.w + x] == T.SHALLOW for x, y in br.cells())
    assert w.same_land(a, far) and w.find_path(a.x, a.y, {(cx + 3, a.y)}) is not None
    # the bridge crumbles away: the far bank is cut off again
    br.durability = 0
    w.remove_structure(br)
    assert not w.same_land(a, far)


def test_a_starving_chit_eats_before_carrying_its_load_to_the_store():
    # a bridge can put a stockpile within reach by a very long walk: one chit starved on the way with food in hand
    w, (a, _) = village()
    a.plan = [{"do": "store", "what": "all", "target": "s1", "_reflex": True}]
    a.inventory["berries"] = 3
    a.hunger = 5.0
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "eat"


def _round_the_channel(w, a):
    """A channel of water from 25 tiles north of the chit down to the sea, 2 tiles east of it: the far bank is 5 tiles
    away as the crow flies and a long walk round the channel's head on foot (as a bridge to land that wraps round a
    mountain can make it: chits starved on 150-tile walks to farms 25 tiles away). Returns that far tile."""
    for y in range(max(0, a.y - 29), min(w.h, a.y + 3)):
        for x in range(a.x - 2, a.x + 8):
            i = y * w.w + x
            w.tiles[i], w.res_kind[i], w.res_amt[i] = T.GRASS, 0, 0
    for y in range(a.y - 25, w.h):
        for x in (a.x + 2, a.x + 3):
            i = y * w.w + x
            w.tiles[i], w.res_kind[i], w.res_amt[i] = T.SHALLOW, 0, 0
    for i in range(w.w * w.h):
        if w.res_kind[i] == T.R_BERRIES:
            w.res_kind[i], w.res_amt[i] = 0, 0
    w.rebuild_block()
    far = (a.x + 5, a.y)
    path = w.find_path(a.x, a.y, w.stand_tiles_for(*far))
    assert path is not None and len(path) > 45, path
    return far


def test_food_a_long_way_round_is_not_food_nearby():
    w, (a, _) = village(seed=3)
    fx, fy = _round_the_channel(w, a)
    w.res_kind[fy * w.w + fx], w.res_amt[fy * w.w + fx] = T.R_BERRIES, 5
    start = (a.x, a.y)
    res = run_step(w, a, {"do": "gather", "what": "berries", "qty": 3}, limit=20)
    assert res != actions.RUNNING and max(abs(a.x - start[0]), abs(a.y - start[1])) <= 4, (res, a.x, a.y)


def test_a_ripe_farm_a_long_way_round_is_not_the_nearest_food():
    w, (a, _) = village(seed=3)
    fx, fy = _round_the_channel(w, a)
    farm = w.place_site("farm", fx, fy, a)
    w.complete_structure(farm, a)
    farm.planted, farm.growth = True, 1.0
    assert actions._farm_ready(w, a) is farm
    res = run_step(w, a, {"do": "harvest", "target": farm.id}, limit=20)
    assert res != actions.RUNNING and res != actions.DONE, res
    assert actions._farm_ready(w, a) is None  # not the food to run for, for a day


def test_a_store_a_long_way_round_is_left_for_another_day():
    w, (a, _) = village(seed=3)
    fx, fy = _round_the_channel(w, a)
    pile = w.place_site("stockpile", fx, fy, a)
    w.complete_structure(pile, a)
    a.inventory["wood"] = 5
    assert run_step(w, a, {"do": "store", "what": "all", "target": pile.id}, limit=20) == actions.DONE
    assert a.inventory["wood"] == 5 and actions._stockpile_with_room(w, a) is None


def test_instinct_bridges_to_clay_across_the_water():
    w, (a, _) = village(seed=3)
    cx = _split(w, a)
    for i in range(w.w * w.h):
        if w.res_kind[i] == T.R_CLAY:
            w.res_kind[i], w.res_amt[i] = 0, 0
    i = a.y * w.w + cx + 3
    w.res_kind[i], w.res_amt[i] = T.R_CLAY, 20
    a.learn("design:bridge", "taught", w.tick)
    a.inventory.update({"wood": 10, "cord": 3})
    plan = BI.bridge_plan(w, a, Lucky())
    assert plan and plan["steps"][-1]["what"] == "bridge", plan
    assert run_step(w, a, plan["steps"][-1]) == actions.DONE
    assert w.same_land_xy(a, cx + 3, a.y)


def test_instinct_rebuilds_a_crowded_home_bigger():
    w, ags = village(4)
    a = ags[0]
    hut = _roomy_hut(w, a)
    for c in ags:
        c.home = hut.id
    a.learn("design:longhouse", "taught", w.tick)
    assert BI.upgrade_plan(w, a, Lucky()) is None  # no cord anywhere, and it can't make any: not yet
    pile = put(w, "stockpile", a, (hut.x, hut.y))
    pile.storage = {"wood": 20, "cord": 6, "stone": 10}
    ags[3].home = None
    assert BI.upgrade_plan(w, a, Lucky()) is None  # three in a hut for three: full, not crowded
    ags[3].home = hut.id
    plan = Instinct()._shelter(w, a, Lucky())
    assert plan and plan["steps"][-1]["do"] == "upgrade", plan
    assert run_step(w, a, plan["steps"][-1]) == actions.DONE and hut.design == "longhouse"


def test_the_prompt_says_what_they_do():
    w, ags = village(4)
    a = ags[0]
    hut = put(w, "hut", a)
    for c in ags:
        c.home = hut.id
    guide = P.verb_guide(w).replace(" ", "")
    assert '"do":"upgrade"' in guide and '"what":"bridge"' in guide
    text = P.scene(w, a)
    assert "4 living here, room for 3 (crowded)" in text
    a.learn("design:well", "taught", w.tick)
    assert "farms within 6 tiles grow a third faster" in P.scene(w, a)


# ---------------------------------------------------------------------------- with production and village projects
def test_a_mill_is_a_station_of_its_own_and_a_smithy_speeds_a_shift():
    assert actions._station_word("mill") == ("mill", None) and actions._station_word("windmill") == ("mill", None)
    assert actions._station_word("factory") == ("factory", None)

    def shift_ticks(design):
        """Ticks of work for one copper axe in a shift, the chit at the station with what it needs in hand."""
        w, (a, _) = village()
        st = put(w, design, a)
        put(w, "stockpile", a, near=(st.x + 3, st.y))  # (a shift needs room in a store for its goods)
        w.learned(a, "recipe:copper_axe", "taught")
        w.first["recipe:copper_axe"] = {"tick": 0, "by": a.id, "name": a.name}
        a.x, a.y = next(iter(w.stand_tiles_for_structure(st)))
        a.inventory.update({"copper": 1, "wood": 1})
        step = {"do": "work", "at": "workshop", "what": "copper_axe", "target": st.id}
        for n in range(1, 3000):
            w.tick += 1
            res = actions.advance(w, a, step)
            if st.produced.get("copper_axe"):
                return n
            assert res == actions.RUNNING, res
        raise AssertionError(step.get("_s"))

    at_smithy, at_workshop = shift_ticks("smithy"), shift_ticks("workshop")
    assert at_smithy * 1.6 <= at_workshop, (at_smithy, at_workshop)


def test_drafting_a_bridge_changes_nothing_about_the_chit():
    w, (a, _) = village()
    a.learn("design:bridge", "insight", w.tick)
    before = dict(a.reflex_rest)
    for i in range(5):
        BI.bridge_plan(w, a, Lucky())
    assert a.reflex_rest == before


def test_a_family_in_a_two_storey_house_doesnt_want_a_brick_house():
    from chits.sim import wants

    w, (a, b) = village()
    w.first["recipe:brick"] = {"tick": 0, "by": b.id, "name": b.name}
    a.familiar.add("brick")
    for design, wanted in (("hut", True), ("two_storey_house", False)):
        home = put(w, design, a, near=(a.x + (0 if design == "hut" else 8), a.y))
        a.home = home.id
        keys = {o["key"] for _, o in wants.options(w, a) if o["kind"] == "home"}
        assert ("brick_house" in keys) is wanted, design
