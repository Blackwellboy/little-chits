"""The 2026-10-04 review, F32's leftovers: the ten dead zones and town rank.

A building was "one close by already" from farther than its effect reaches (a granary 12 tiles off for a store it keeps
fresh only within 10), so between the two what it is for went unserved and a second one was refused. Each of the ten now
has a builder that asks what is unserved (a store whose food nothing keeps, farms no well waters, children no school
reaches, homes out of earshot of a bell or out of reach of a tavern, healer, park or square, trees no sawmill reaches,
fish no harbour reaches), sites the building to serve it, and is reused from no farther than it reaches.

Town rank: tavern, bakery, healer, tailor, park, plaza, palisade and apartment block need a town (a village of 20 with
a working hall), at the build and in the builder; one already standing keeps working anywhere."""

import random

import pytest

from chits.brain import builder as BI
from chits.brain import prompt as P
from chits.sim import actions as A
from chits.sim import buildings as BLD
from chits.sim import settlements as SE
from chits.sim import terrain as T
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS
from test_buildings import grass, village
from test_pioneers import _full_village
from test_towns import put, village_of

NOON = 4 * TICKS_PER_DAY + 120  # (nothing is started in the dark)


@pytest.fixture(autouse=True)
def switched_on(monkeypatch):
    """Both are off by default until an A/B holds (buildings.NEED_SITING, buildings.TOWN_GATE): these tests are of them."""
    monkeypatch.setattr(BLD, "NEED_SITING", True)
    monkeypatch.setattr(BLD, "TOWN_GATE", True)
TEN = ("well", "granary", "school", "bell_tower", "sawmill", "plaza", "tavern", "healer", "park", "harbour")


def meadow(n=4, size=128):
    """Open grass 45 tiles round the first chit, everyone standing with it, at noon."""
    w, ags = village(n=n, size=size)
    a = ags[0]
    grass(w, a, 45)
    for o in ags:
        o.x, o.y, o.home = a.x, a.y, None
    w.tick = NOON
    return w, a


def at(w, a, design, x, y, done=True):
    """One of this design exactly here (a site when not `done`)."""
    w.tick += 1  # (the working buildings are looked up once a tick)
    st = w.place_site(design, x, y, a)
    if done:
        w.complete_structure(st, a)
    if design == "farm":
        st.planted, st.growth = True, 0.0
    return st


def able(a, w, design):
    a.learn(f"design:{design}", "taught", w.tick)
    a.inventory.update(DESIGNS[design].material_map)


def wants(w, a, design):
    """The build step the builder proposes for this design, if it proposes one."""
    for _, p in BI.building_options(w, a, random.Random(1)):
        st = p["steps"][-1]
        if st.get("do") == "build" and st.get("what") == design:
            return st
    return None


def begin(w, a, step):
    """Run the build step once: the site it started (or None), and what the build answered."""
    s = {}
    res = A._do_build(w, a, dict(step), s)
    return w.structures.get(s.get("site") or ""), (s.get("note") or res)


def near_of(step):
    x, y = step["near"].split(",")
    return int(x), int(y)


# ---------------------------------------------------------------------------- the table
def test_all_ten_are_reused_from_no_farther_than_they_reach(monkeypatch):
    for d in TEN:
        assert d in BLD.AT_REACH and A.reuse_within(d) == BLD.EFFECT_RADIUS[d], d
    monkeypatch.setattr(BLD, "NEED_SITING", False)  # (off: as before, farther than they reach)
    for d in TEN:
        assert A.reuse_within(d) == A.REUSE_WITHIN[d] > BLD.EFFECT_RADIUS[d], d


@pytest.mark.parametrize("design", TEN)
def test_one_just_out_of_reach_is_not_one_close_by(design):
    w, a = meadow()
    a.learn(f"design:{design}", "taught", w.tick)
    r = BLD.EFFECT_RADIUS[design]
    st = at(w, a, design, a.x + 20, a.y)
    x = st.x - r - 1
    assert st.dist(x, a.y) == r + 1 and A._use_existing(w, a, design, {}, x, a.y) is None
    assert st.dist(x + 1, a.y) == r and A._use_existing(w, a, design, {}, x + 1, a.y) == A.DONE


# ---------------------------------------------------------------------------- well
def _fields(w, a):
    return [at(w, a, "farm", a.x + 3, a.y - 3), at(w, a, "farm", a.x + 3, a.y + 1)]


def test_a_well_is_built_for_fields_no_well_waters_and_stands_where_it_waters_them():
    w, a = meadow(n=60)  # (a well for every ten people: the share is not what stops the second)
    able(a, w, "well")
    f1, f2 = _fields(w, a)
    # a well 7 tiles from the fields waters neither (it reaches 6), and stood "close by" (8): no second well, ever
    well = at(w, a, "well", f1.x - 7, a.y)
    assert BLD.gap(f1, well) == 7 and BLD.gap(f2, well) == 7 and BLD.growth_mult(w, f1) == 1.0
    step = wants(w, a, "well")
    assert step and near_of(step) in ((f1.x, f1.y), (f2.x, f2.y)) and step["_within"] == BLD.WELL_RADIUS
    site, said = begin(w, a, step)
    assert site is not None and site.design == "well", said
    assert BLD.gap(site, f1) <= BLD.WELL_RADIUS and BLD.gap(site, f2) <= BLD.WELL_RADIUS
    # ...and while that one is going up, nobody plans a third
    assert wants(w, a, "well") is None


def test_no_well_for_watered_fields_or_for_one_dry_field():
    w, a = meadow(n=60)
    able(a, w, "well")
    f1, f2 = _fields(w, a)
    assert wants(w, a, "well") is not None
    well = at(w, a, "well", f1.x + f1.w + 2, a.y)  # (waters both, though it stands 11 tiles from the chit)
    assert BLD.growth_mult(w, f1) > 1.0 and BLD.growth_mult(w, f2) > 1.0
    a.x = well.x - 11
    assert well.dist(a.x, a.y) > 10 and len(BI._farms(w, a, BI.WELL_LOOK)) == 2
    assert wants(w, a, "well") is None  # ("none within 10 tiles of me" asked for one here)
    w2, b = meadow()
    able(b, w2, "well")
    at(w2, b, "farm", b.x + 3, b.y)
    assert BI.WELL_MIN_FARMS == 2 and wants(w2, b, "well") is None
    far = at(w2, b, "farm", b.x - 10, b.y)  # a second dry field, too far from the first for one well to water both
    assert len(BI._farms(w2, b, BI.WELL_LOOK)) == 2 and wants(w2, b, "well") is None


# ---------------------------------------------------------------------------- granary
def _pile(w, a, food=30, pots=0):
    pile = at(w, a, "stockpile", a.x + 2, a.y)
    pile.storage.update({"berries": food})
    if pots:
        pile.storage["pot"] = pots
    return pile


def test_a_granary_is_built_for_a_store_just_out_of_anothers_reach():
    w, a = meadow(n=60)
    able(a, w, "granary")
    pile = _pile(w, a)
    far = at(w, a, "granary", pile.x + pile.w + 10, pile.y)
    assert BLD.gap(pile, far) == 11 and not BLD.keeps_fresh(w, pile)
    step = wants(w, a, "granary")
    assert step and near_of(step) == (pile.x, pile.y) and step["_within"] == BLD.GRANARY_RADIUS
    site, said = begin(w, a, step)  # (reused from 12 tiles, the plan was answered "one close by already" every time)
    assert site is not None and site is not far and BLD.gap(site, pile) <= BLD.GRANARY_RADIUS, said


def test_no_granary_for_a_store_one_keeps_or_whose_pots_hold_its_food():
    w, a = meadow(n=60)
    able(a, w, "granary")
    pile = _pile(w, a)
    assert wants(w, a, "granary") is not None
    at(w, a, "granary", pile.x + pile.w + 8, pile.y)
    w.tick += 1
    assert BLD.keeps_fresh(w, pile) and wants(w, a, "granary") is None
    w2, b = meadow()
    able(b, w2, "granary")
    _pile(w2, b, food=30, pots=2)  # (two pots keep 20 of it: 10 left to rot is not worth a granary)
    assert BI.GRANARY_MIN_FOOD == 20 and BLD.POT_KEEPS == 10 and wants(w2, b, "granary") is None
    w3, c = meadow()
    able(c, w3, "granary")
    _pile(w3, c, food=40, pots=2)
    assert wants(w3, c, "granary") is not None


# ---------------------------------------------------------------------------- school
def _children(w, a, n, x, y):
    kids = [o for o in w.agents.values() if o is not a][:n]
    for k in kids:
        k.born = w.tick - TICKS_PER_DAY
        k.x, k.y = x, y
    return kids


def test_a_school_is_built_for_children_none_reaches():
    w, a = meadow(n=60)
    able(a, w, "school")
    kx, ky = a.x + 3, a.y
    _children(w, a, 3, kx, ky)
    far = at(w, a, "school", kx + 12, ky)  # (it reaches 8; it stood "close by" from 15, and within 20 of the chit)
    assert far.dist(kx, ky) == 12
    step = wants(w, a, "school")
    assert step and near_of(step) == (kx, ky) and step["_within"] == BLD.SCHOOL_RADIUS
    site, said = begin(w, a, step)
    assert site is not None and site is not far and site.dist(kx, ky) <= BLD.SCHOOL_RADIUS, said


def test_no_school_for_children_one_reaches_or_for_one_child():
    w, a = meadow(n=60)
    able(a, w, "school")
    kx, ky = a.x + 3, a.y
    _children(w, a, 3, kx, ky)
    assert wants(w, a, "school") is not None
    at(w, a, "school", kx + 6, ky)
    assert wants(w, a, "school") is None
    w2, b = meadow(n=60)
    able(b, w2, "school")
    _children(w2, b, 1, b.x + 3, b.y)
    assert BI.SCHOOL_MIN_CHILDREN == 2 and wants(w2, b, "school") is None


# ---------------------------------------------------------------------------- bell tower
def _hamlet(w, a, per_home, homes=4):
    """Huts in a tight block beside the chit, so many living in each."""
    huts = [at(w, a, "hut", a.x + 2 + 3 * (i % 2), a.y + 3 * (i // 2)) for i in range(homes)]
    people = [o for o in w.agents.values()]
    for i, o in enumerate(people):
        o.home = huts[i // per_home].id if i // per_home < homes else None
    return huts


def test_a_bell_is_built_for_homes_out_of_earshot_and_not_for_homes_that_hear_one():
    w, a = meadow(n=60)
    able(a, w, "bell_tower")
    huts = _hamlet(w, a, 15)
    step = wants(w, a, "bell_tower")
    assert step and near_of(step) in {(h.x, h.y) for h in huts} and step["_within"] == BLD.BELL_RADIUS
    # one that every home hears: the world's share (60 // 30) allowed a second, and it was planned with no reason
    bell = at(w, a, "bell_tower", a.x + 4, a.y + 8)
    assert all(bell.dist(h.x, h.y) <= BLD.BELL_RADIUS for h in huts) and BI._count(w, "bell_tower") < len(w.agents) // 30
    assert wants(w, a, "bell_tower") is None
    # one no home hears, 22 tiles off: it stood "close by" (25), so the homes never got theirs
    w2, b = meadow(n=60)
    able(b, w2, "bell_tower")
    huts = _hamlet(w2, b, 15)
    far = at(w2, b, "bell_tower", min(h.x for h in huts) - 22 - DESIGNS["bell_tower"].size[0] + 1, b.y)
    assert all(far.dist(h.x, h.y) > BLD.BELL_RADIUS for h in huts)
    step = wants(w2, b, "bell_tower")
    assert step and far.dist(*near_of(step)) <= 25
    site, said = begin(w2, b, step)
    assert site is not None and site is not far and site.dist(*near_of(step)) <= BLD.BELL_RADIUS, said


def test_no_bell_for_a_handful_out_of_earshot():
    w, a = meadow(n=60)
    able(a, w, "bell_tower")
    _hamlet(w, a, 2)  # (eight people housed: the rest have no home yet)
    assert BI.BELL_MIN_PEOPLE == 10 and wants(w, a, "bell_tower") is None


# ---------------------------------------------------------------------------- sawmill
def _stand(w, a, trees):
    """A stand of this many trees beside the chit; the tree nearest it."""
    spots = [(a.x + 3 + i % 3, a.y - 1 + i // 3) for i in range(trees)]
    for x, y in spots:
        i = y * w.w + x
        w.tiles[i], w.res_kind[i], w.res_amt[i] = T.FOREST, T.R_WOOD, 5
    w.rebuild_block()
    return w.nearest_resource(a.x, a.y, "wood", BI.SAW_LOOK)


def test_a_sawmill_is_built_for_a_stand_none_reaches():
    w, a = meadow(n=60)
    able(a, w, "sawmill")
    tree = _stand(w, a, 9)
    far = at(w, a, "sawmill", tree[0] + 14, tree[1])  # (it reaches 12; "close by" from 15, and within 20 of the chit)
    assert far.dist(*tree) == 14 and not BLD.sawn(w, *tree)
    step = wants(w, a, "sawmill")
    assert step and near_of(step) == tree and step["_within"] == BLD.SAW_RADIUS
    site, said = begin(w, a, step)
    assert site is not None and site is not far and site.dist(*tree) <= BLD.SAW_RADIUS, said


def test_no_sawmill_for_trees_one_reaches_or_for_a_few_trees():
    w, a = meadow(n=60)
    able(a, w, "sawmill")
    tree = _stand(w, a, 9)
    assert wants(w, a, "sawmill") is not None
    at(w, a, "sawmill", tree[0] + 10, tree[1])
    assert wants(w, a, "sawmill") is None
    w2, b = meadow()
    able(b, w2, "sawmill")
    _stand(w2, b, 3)
    assert BI.SAW_MIN_TREES == 6 and wants(w2, b, "sawmill") is None


# ---------------------------------------------------------------------------- a town's tavern, healer, park and square
def _town(east_only=None):
    """A town of 60 on open ground: its hall, five huts beside it and five more 15 tiles east of it, six living in
    each. With `east_only`: that many in one eastern hut and everyone else in the hut nearest the hall."""
    w, a = meadow(n=60)
    hx, hy = a.x, a.y + 2
    hall = at(w, a, "town_hall", hx, hy)
    west = [at(w, a, "hut", hx - 4, hy - 6 + 3 * i) for i in range(5)]
    east = [at(w, a, "hut", hx + 15, hy - 6 + 3 * i) for i in range(5)]
    people = list(w.agents.values())
    for i, o in enumerate(people[:30]):
        o.home = west[i // 6].id
    for i, o in enumerate(people[30:]):
        o.home = east[i // 6].id
    if east_only is not None:
        for i, o in enumerate(people):
            o.home = east[2].id if i >= 60 - east_only else west[2].id
    w.tick += 1
    assert village_of(w, a).rank == "town" and BLD.town_of(w, hall.x, hall.y) is not None
    return w, a, hall, west, east


def _town_wants(w, a, design):
    opts = BI.town_options(w, a) if design == "plaza" else BI.town_life_options(w, a)
    return next((p["steps"][-1] for _, p in opts if p["steps"][-1].get("what") == design), None)


@pytest.mark.parametrize("design", ["tavern", "healer", "park", "plaza"])
def test_a_town_builds_a_second_for_homes_the_first_does_not_reach(design):
    w, a, hall, west, east = _town()
    able(a, w, design)
    r = BLD.EFFECT_RADIUS[design]
    step = _town_wants(w, a, design)  # the first goes up by the hall, where 30 live within reach
    assert step and step["_within"] == r and hall.dist(*near_of(step)) <= 4, step
    first = at(w, a, design, hall.x, hall.y + hall.h + 2)
    assert all(first.dist(h.x, h.y) > r for h in east)
    # 30 more live out of its reach, in the same town: there was "one in the town", and the build said "one close by"
    step = _town_wants(w, a, design)
    assert step and near_of(step) in {(h.x, h.y) for h in east}, step
    site, said = begin(w, a, step)
    assert site is not None and site is not first and site.dist(*near_of(step)) <= r, said
    w.complete_structure(site, a)
    w.tick += 1
    served = [h for h in east if site.dist(h.x, h.y) <= r]
    assert served, (site.x, site.y)


@pytest.mark.parametrize("design", ["tavern", "healer", "park", "plaza"])
def test_a_town_builds_no_second_for_homes_in_reach_or_for_a_few(design):
    r, _, least = BI.NEED[design]
    w, a, hall, west, east = _town(east_only=least)
    able(a, w, design)
    first = at(w, a, design, hall.x, hall.y + hall.h + 2)
    assert first.dist(west[2].x, west[2].y) <= r < first.dist(east[2].x, east[2].y)
    step = _town_wants(w, a, design)
    assert step and near_of(step) == (east[2].x, east[2].y)
    at(w, a, design, east[2].x - 3, east[2].y)  # (one beside that home too)
    assert _town_wants(w, a, design) is None
    # one fewer living out east: not enough to be worth a building
    w, a, hall, west, east = _town(east_only=least - 1)
    able(a, w, design)
    at(w, a, design, hall.x, hall.y + hall.h + 2)
    assert _town_wants(w, a, design) is None


# ---------------------------------------------------------------------------- harbour
def _pond(w, x, y):
    """A pond with fish in it."""
    for dx in range(2):
        for dy in range(2):
            w.tiles[(y + dy) * w.w + x + dx] = T.SHALLOW
    i = y * w.w + x
    w.res_kind[i], w.res_amt[i] = T.R_FISH, 3
    w.rebuild_block()
    return x, y


def _harbour_wants(w, a):
    return next((p["steps"][-1] for _, p in BI.city_options(w, a) if p["steps"][-1].get("what") == "harbour"), None)


def test_a_harbour_is_built_for_fish_none_reaches():
    w, a, hall, west, east = _town()
    able(a, w, "harbour")
    fish = _pond(w, hall.x + 6, hall.y + 12)
    assert w.nearest_resource(hall.x, hall.y, "fish", BI.HARBOUR_LOOK) == fish
    far = at(w, a, "harbour", fish[0] - 15 - 1, fish[1])  # (it reaches 12; "close by" from 20, and the town had "one")
    assert far.dist(*fish) == 15 and not BLD.fished(w, *fish)
    step = _harbour_wants(w, a)
    assert step and near_of(step) == fish
    site, said = begin(w, a, step)
    assert site is not None and site is not far and site.dist(*fish) <= BLD.HARBOUR_RADIUS, said


def test_a_harbour_is_not_raised_out_of_reach_of_the_fish_it_is_for():
    # fish reached by a one-tile causeway, no room for a quay beside it: the harbour search widened to 60 tiles, stood
    # 30 from the fish, caught none of it and used up the town's allowance (Codex, #95)
    w, a, hall, west, east = _town()
    able(a, w, "harbour")
    fx, fy = hall.x + 6, hall.y + 12
    for y in range(fy - 2, fy + 3):
        for x in range(fx - 2, fx + 3):
            i = y * w.w + x
            w.tiles[i], w.res_kind[i], w.res_amt[i] = T.ROCK, 0, 0
    w.tiles[fy * w.w + fx] = T.SHALLOW
    w.res_kind[fy * w.w + fx], w.res_amt[fy * w.w + fx] = T.R_FISH, 3
    for x in (fx - 1, fx - 2):
        w.tiles[fy * w.w + x] = T.GRASS
    _pond(w, hall.x - 25, hall.y)  # (open shore, out of the fish's reach)
    step = _harbour_wants(w, a)
    assert step and near_of(step) == (fx, fy) and step["_within"] == BLD.HARBOUR_RADIUS, step
    assert w.find_site("harbour", fx, fy, BLD.HARBOUR_RADIUS) is not None  # (the old search went this far)
    site, said = begin(w, a, step)
    assert site is None and f"no clear ground within {BLD.HARBOUR_RADIUS}" in said, (site and (site.x, site.y), said)
    assert not any(s.design == "harbour" for s in w.structures.values())


def test_no_harbour_for_fish_one_reaches_or_beyond_a_towns_share():
    w, a, hall, west, east = _town()
    able(a, w, "harbour")
    fish = _pond(w, hall.x + 6, hall.y + 12)
    assert _harbour_wants(w, a) is not None
    at(w, a, "harbour", fish[0] - 10, fish[1])
    assert BLD.fished(w, *fish) and _harbour_wants(w, a) is None
    # a second shoal out of its reach, but two harbours are this town's share (60 people, one for every 30)
    more = _pond(w, fish[0] + 8, fish[1])
    assert not BLD.fished(w, *more)
    assert _harbour_wants(w, a) is not None and near_of(_harbour_wants(w, a)) == more
    at(w, a, "harbour", hall.x - 20, hall.y)
    assert BI.HARBOUR_PEOPLE == 30 and _harbour_wants(w, a) is None


# ---------------------------------------------------------------------------- "_within"
def test_a_building_sited_for_something_goes_up_within_reach_of_it_or_not_at_all():
    w, a = meadow()
    able(a, w, "well")
    px, py = a.x + 12, a.y
    for y in range(py - 9, py + 10):  # rock all round the place: the nearest clear ground is 10 tiles off
        for x in range(px - 9, px + 10):
            w.tiles[y * w.w + x] = T.ROCK
    w.rebuild_block()
    site, said = begin(w, a, {"do": "build", "what": "well", "near": f"{px},{py}", "_within": 6})
    assert site is None and "no clear ground within 6" in said, said
    a.reflex_rest.clear()
    site, said = begin(w, a, {"do": "build", "what": "well", "near": f"{px},{py}"})  # (unsited: anywhere near will do)
    assert site is not None, said


# ---------------------------------------------------------------------------- town rank
def _hall_village(n):
    w, v = _full_village(n)
    a = w.agents[v.residents[0]]
    hall = put(w, "town_hall", a, (int(v.x), int(v.y)))
    w.tick = (w.tick // TICKS_PER_DAY + 1) * TICKS_PER_DAY + 120
    a.x, a.y = hall.x, hall.y + hall.h + 1
    return w, a, hall


@pytest.mark.parametrize("design", [d for d in BLD.TOWN_ONLY if d != "apartment"])
def test_town_life_is_refused_outside_a_town_and_built_in_one(design):
    # in a hamlet with no hall
    w, a = meadow()
    able(a, w, design)
    site, said = begin(w, a, {"do": "build", "what": design})
    assert site is None and "only a town can build a " + DESIGNS[design].name in said, said
    # in a village of ten with a hall (no town yet)
    w, a, hall = _hall_village(10)
    assert village_of(w, a).rank == "village"
    able(a, w, design)
    site, said = begin(w, a, {"do": "build", "what": design})
    assert site is None and "only a town" in said, said
    # in a town
    w, a, hall = _hall_village(24)
    assert village_of(w, a).rank == "town"
    able(a, w, design)
    site, said = begin(w, a, {"do": "build", "what": design})
    assert site is not None and site.design == design, said


def test_the_builder_plans_town_life_only_in_a_town():
    for n, town in ((10, False), (24, True)):
        w, a, hall = _hall_village(n)
        for d in ("tavern", "bakery", "healer", "tailor", "park", "plaza", "palisade"):
            able(a, w, d)
        from chits.sim import animals as AN

        AN._add(w, "wolf", a.x + 8, a.y)
        got = {p["steps"][-1].get("what") for _, p in BI.building_options(w, a, random.Random(1))
               if p["steps"][-1].get("do") == "build"}
        if town:
            assert {"tavern", "bakery", "healer", "tailor", "park", "plaza", "palisade"} <= got, got
        else:
            assert not got & set(BLD.TOWN_ONLY), got


def test_town_life_already_standing_keeps_working_outside_a_town():
    w, a = meadow(n=4)
    tv = at(w, a, "tavern", a.x + 2, a.y)
    w.tick += 1
    assert BLD.town_of(w, tv.x, tv.y) is None
    for o in w.agents.values():
        o.mood = 50.0
    BLD._tavern(w)
    assert all(o.mood == 50.0 + BLD.TAVERN_MOOD for o in w.agents.values())
    hl = at(w, a, "healer", a.x + 2, a.y + 4)
    w.tick += 1
    assert BLD.heal_mult(w, a) == BLD.HEALER_MULT
    # a site begun before the rule can be finished: the build joins it
    able(a, w, "park")
    half = at(w, a, "park", a.x - 4, a.y, done=False)
    site, said = begin(w, a, {"do": "build", "what": "park"})
    assert site is half, said


def test_an_apartment_block_needs_a_town_too():
    from test_buildings import Lucky

    for n, town in ((10, False), (24, True)):
        w, a, hall = _hall_village(n)
        home = w.structures[a.home]
        home.design = "two_storey_house"
        for o in list(w.agents.values())[:9]:
            o.home = home.id  # (crowded: nine in a house for eight)
        a.learn("design:apartment", "taught", w.tick)
        a.inventory.update(BLD.salvage_needs("two_storey_house", "apartment"))
        a.x, a.y = next(iter(w.stand_tiles_for_structure(home)))
        s = {}
        res = BLD.do_upgrade(w, a, {"do": "upgrade", "to": "apartment"}, s)
        plan = BI.upgrade_plan(w, a, Lucky())
        if town:
            assert home.upgrade.get("to") == "apartment", res
        else:
            assert "only a town can build a apartment block" in res and not home.upgrade, res
            assert plan is None
    # one already being rebuilt carries on wherever it stands
    w, a, hall = _hall_village(10)
    home = w.structures[a.home]
    home.design = "two_storey_house"
    home.upgrade = {"to": "apartment", "needs": {}, "work": 0.0, "total": 5.0, "by": {}, "tick": w.tick}
    a.x, a.y = next(iter(w.stand_tiles_for_structure(home)))
    s = {}
    for _ in range(400):
        w.tick += 1
        if BLD.do_upgrade(w, a, {"do": "upgrade"}, s) != A.RUNNING:
            break
    assert home.design == "apartment"


def test_the_words_a_model_reads_say_only_a_town(monkeypatch):
    w, a = meadow()
    for d in BLD.TOWN_ONLY:
        a.learn(f"design:{d}", "taught", w.tick)
    text = P.scene(w, a)
    build = next(x for x in text.split("\n") if x.startswith("YOU KNOW HOW TO BUILD: "))
    for d in BLD.TOWN_ONLY:
        entry = next(x for x in build.split(": ", 1)[1].split("; ") if x.startswith(DESIGNS[d].name + " ("))
        assert entry.endswith("(only a town can build one))"), entry
    monkeypatch.setattr(BLD, "TOWN_GATE", False)  # (off, the prompt says nothing it does not do)
    assert "only a town" not in P.scene(w, a)
    assert P.PROMPT_VERSION >= "2026-10-04.4"
    assert SE.TOWN_POP == 20
