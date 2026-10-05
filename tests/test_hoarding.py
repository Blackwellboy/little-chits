"""Hoarding (issue #7, F33). A long live run filled every store (about 1,900 seeds in one world; 990 wood and 840 grain
in the other), and station shifts had no room for their goods. Instinct fetched with no reading of what the village
held: in 60-day runs two thirds of the wood and stone gathered, and most of the charcoal made by hand, were for a site
whose materials lay in the stores. Each good now has a ceiling that grows with the village's people; the urge to fetch
it falls as the stores fill and is nothing at the ceiling; over it, grain is ground, wood burned to charcoal and seed
sown; and stores full of plenty are no reason for another stockpile."""

import random

import pytest

from chits.brain import builder as BI
from chits.brain import civic
from chits.brain import ground as GR
from chits.brain import surplus as SUR
from chits.brain.instinct import Instinct
from chits.sim import actions, food
from chits.sim.items import DESIGNS, item_name
from test_buildings import put, run_step, village


@pytest.fixture(autouse=True)
def plenty(monkeypatch):
    """The readings of the village's stock are behind actions.PLENTY (off by default until the seed-24 starvation
    is understood): every test here runs with them on."""
    monkeypatch.setattr(actions, "PLENTY", True)


def grown(n=2, seed=1):
    """A village of grown chits with one stockpile beside them."""
    w, ags = village(n, seed)
    for o in ags:
        o.born = -240 * 10
    return w, ags[0], put(w, "stockpile", ags[0])


def draws(w, a, n=400, fn="_progress"):
    """The goals of this many of instinct's choices, each drawn with its own dice at the same moment."""
    ins = Instinct()
    ins._world = w
    out = []
    for t in range(n):
        a.hunger = a.energy = a.warmth = 100.0
        p = getattr(ins, fn)(w, a, random.Random(t))
        out.append(p or {"goal": "", "steps": []})
    return out


def goals(w, a, n=400, fn="_progress"):
    return [p["goal"] for p in draws(w, a, n, fn)]


def follow(w, a, steps, limit=4000):
    """Carry a plan out with the game's own step driver."""
    a.plan = [dict(s) for s in steps]
    for _ in range(limit):
        if not a.plan:
            break
        w.tick += 1
        a.hunger = a.energy = a.warmth = 100.0
        actions.run(w, a)
    return a.last_result


# ---------------------------------------------------------------------------- the ceiling
def test_a_goods_ceiling_grows_with_the_villages_people_and_the_urge_is_nothing_at_it():
    w, a, pile = grown()
    top = SUR.ceiling(w, a, "wood")
    assert top == SUR.MIN_CEILING  # (two chits: the floor)
    assert SUR.urge(w, a, "wood") == 1.0 and not SUR.over(w, a, "wood")
    pile.storage["wood"] = int(top // 2)
    assert SUR.urge(w, a, "wood") == pytest.approx(0.5)
    pile.storage["wood"] = int(top)
    assert SUR.urge(w, a, "wood") == 0.0 and SUR.over(w, a, "wood")
    assert SUR.ceiling(w, a, "berries") is None and SUR.urge(w, a, "berries") == 1.0  # (food to pick has no ceiling)
    big, b, _ = grown(30)
    n = SUR.people(big, b.x, b.y)
    assert n > 20 and SUR.ceiling(big, b, "wood") == SUR.USE_PER_DAY["wood"] * SUR.CEILING_DAYS * n > top
    # grain's is in days of everyone's food
    assert SUR.ceiling(big, b, "grain") == SUR.GRAIN_DAYS * food.FOOD_PER_DAY / big.item("grain").food * n
    # a store this chit can't walk to is not its village's stock (actions.village_stores)
    a.reflex_rest["unreach:" + pile.id] = w.tick + 100
    assert SUR.urge(w, a, "wood") == 1.0


def _only_wood_lacking(pile):
    for k in ("stone", "fiber", "clay", "berries"):
        pile.storage[k] = 25  # (not "lacking": the stores right here hold 25)


def test_the_urge_to_collect_a_good_falls_as_the_village_stores_fill():
    w, a, pile = grown()
    _only_wood_lacking(pile)
    empty = goals(w, a, 600).count("collect wood")
    pile.storage["wood"] = 24  # (still under the 25 the stores right here should hold)
    part = goals(w, a, 600).count("collect wood")
    assert empty > 20 and part < 0.85 * empty, (empty, part)


def test_nothing_is_collected_that_the_village_holds_at_its_ceiling_a_little_way_off():
    w, a, pile = grown()
    _only_wood_lacking(pile)
    # a second store out of the "right here" 20 tiles, but one of the village's (within PLENTY_SIGHT)
    far = next(s for s in (put(w, "stockpile", a, near=(a.x + dx, a.y + dy), radius=1)
                           for dx, dy in ((23, 0), (-23, 0), (0, 23), (0, -23)) if w.find_site("stockpile", a.x + dx, a.y + dy, 1))
               if 20 < s.dist(a.x, a.y) <= SUR.PLENTY_SIGHT and w.same_land(a, s))
    assert "collect wood" in goals(w, a, 300)
    far.storage["wood"] = int(SUR.ceiling(w, a, "wood"))
    assert "collect wood" not in goals(w, a, 300)
    # ...and it isn't drawn in place of something the village does lack
    pile.storage["stone"] = 0
    stone = goals(w, a, 300).count("collect stone")
    far.storage["wood"], pile.storage["wood"] = 0, 25  # (the same choice with wood simply not lacking)
    assert stone == goals(w, a, 300).count("collect stone") > 0


def test_a_village_short_of_a_good_still_gathers_it():
    w, a, pile = grown()
    assert SUR.split(w, a, "wood", 8) == (8, 0)
    site = w.place_site("workshop", *w.find_site("workshop", a.x + 4, a.y, 6), a)
    ins = Instinct()
    ins._world = w
    steps = ins._help_site(a, site, "help", "")["steps"]
    assert steps[:2] == [{"do": "gather", "what": "wood", "qty": 8}, {"do": "gather", "what": "stone", "qty": 6}]
    pile.storage["wood"] = 5  # a little in store is left there: shifts and builders need it
    assert SUR.split(w, a, "wood", 8) == (8, 0)
    _only_wood_lacking(pile)
    pile.storage["wood"] = 0
    assert "collect wood" in goals(w, a, 300)


def test_a_site_is_supplied_from_the_stores_in_the_measure_they_are_full():
    w, a, pile = grown()
    site = w.place_site("workshop", *w.find_site("workshop", a.x + 4, a.y, 6), a)
    assert list(site.needs.items())[:2] == [("wood", 10), ("stone", 6)]
    top = int(SUR.ceiling(w, a, "wood"))
    pile.storage.update({"wood": top // 2, "stone": top})
    ins = Instinct()
    ins._world = w
    steps = ins._help_site(a, site, "help", "")["steps"]
    # half the wood from the stores and half cut; no stone gathered at all (and no more taken than its hands hold:
    # the help step fetches what the site still lacks from the stores itself)
    assert a.free_space() == 12
    assert steps == [{"do": "take", "what": "wood", "qty": 4}, {"do": "gather", "what": "wood", "qty": 4},
                     {"do": "take", "what": "stone", "qty": 4}, {"do": "help", "site": site.id}]
    follow(w, a, steps)
    assert "wood" not in site.needs and "stone" not in site.needs
    cut = a.stats.get("gathered_wood", 0)
    assert 4 <= cut < 8 and a.stats.get("gathered_stone", 0) == 0
    assert pile.storage["stone"] == top - 6 and pile.storage["wood"] == top // 2 - (10 - cut)


def test_a_made_thing_the_stores_hold_plenty_of_is_taken_not_made_again():
    w, a, pile = grown()
    for k in ("recipe:charcoal", "recipe:copper"):
        w.learned(a, k, "taught")
    put(w, "kiln", a, near=(a.x + 5, a.y))
    assert "make charcoal" in goals(w, a, 400)
    pile.storage["charcoal"] = int(SUR.ceiling(w, a, "charcoal"))
    assert "make charcoal" not in goals(w, a, 400)
    assert SUR.split(w, a, "charcoal", 3) == (0, 3)
    from chits.brain.instinct import _fetch_steps

    assert _fetch_steps(w, a, "charcoal", 3) == [{"do": "take", "what": "charcoal", "qty": 3}]
    pile.storage["charcoal"] = 0
    assert _fetch_steps(w, a, "charcoal", 3)[-1] == {"do": "craft", "what": "charcoal", "qty": 2}


def test_what_goes_into_a_thing_made_by_hand_comes_from_the_stores_once_they_hold_plenty():
    """Iron for a site was made with freshly burned charcoal, two for each wood, and what was left over was stored:
    one village held 1,490 charcoal after 60 days, 1,111 of it made on the way to a building site."""
    from chits.brain.instinct import _craft_steps

    w, a, pile = grown()
    for k in ("recipe:charcoal", "recipe:copper"):
        w.learned(a, k, "taught")
    put(w, "kiln", a, near=(a.x + 5, a.y))
    put(w, "furnace", a, near=(a.x - 5, a.y))
    a.add("stone_pick", 1)
    burn = {"do": "craft", "what": "charcoal", "qty": 1}
    pile.storage["charcoal"] = int(SUR.ceiling(w, a, "charcoal")) - 1  # (under its ceiling: left where it is)
    steps = _craft_steps(a, "copper", 1, world=w)
    assert burn in steps and not any(s["do"] == "take" for s in steps)
    pile.storage["charcoal"] += 1
    steps = _craft_steps(a, "copper", 1, world=w)
    assert steps[0] == {"do": "take", "what": "charcoal", "qty": 1} and burn not in steps
    assert steps[-1] == {"do": "craft", "what": "copper", "qty": 1}


def test_a_worn_building_is_mended_with_stored_wood_once_the_stores_hold_plenty():
    w, a, pile = grown()
    farm = put(w, "farm", a, near=(a.x + 4, a.y))
    farm.durability = 40.0
    a.job = "builder"
    ins = Instinct()
    assert ins._maintain(w, a, random.Random(1))["steps"][0] == {"do": "gather", "what": "wood", "qty": 2}
    pile.storage["wood"] = int(SUR.ceiling(w, a, "wood"))
    assert ins._maintain(w, a, random.Random(1))["steps"][0] == {"do": "take", "what": "wood", "qty": 2}


def test_loose_goods_the_stores_hold_plenty_of_are_not_carried_in():
    w, a, pile = grown()
    w.put_ground(a.x + 2, a.y, "seeds", 9)
    assert GR.tidy_plan(w, a)["steps"][0] == {"do": "pickup", "what": "seeds"}
    pile.storage["seeds"] = int(SUR.ceiling(w, a, "seeds"))
    assert GR.tidy_plan(w, a) is None


def test_nobody_collects_for_the_villages_work_what_the_stores_hold_plenty_of():
    w, a, pile = grown()
    other = next(o for o in w.agents.values() if o is not a)
    w.learned(other, "recipe:charcoal", "taught")
    p = {"key": "charcoal", "n": 50, "for": ""}
    plan = civic.make_plan(w, a, p)
    assert plan and plan["steps"][0] == {"do": "gather", "what": "wood", "qty": 4}
    pile.storage["wood"] = int(SUR.ceiling(w, a, "wood"))
    assert civic.make_plan(w, a, p) is None


# ---------------------------------------------------------------------------- the sinks
def known(w, a, key):
    """Someone in this world has worked out how to make this (what production counts as a use for its inputs)."""
    w.first[f"recipe:{key}"] = {"tick": 0, "by": a.id, "name": a.name}


def _shifts_until_none(w, a, limit=20):
    n = 0
    while True:
        offered = SUR.sinks(w, a)
        if not offered:
            return n
        assert run_step(w, a, dict(offered[0][1]["steps"][0])) == actions.DONE
        n += 1
        assert n < limit


def test_grain_over_its_ceiling_is_ground_at_the_mill_until_flour_reaches_its_own():
    w, a, pile = grown()
    mill = put(w, "mill", a, near=(a.x + 5, a.y))
    w.learned(a, "recipe:flour", "taught")
    pile.storage["loaf"] = 40  # (food enough: see the food-first test)
    top, ftop = int(SUR.ceiling(w, a, "grain")), int(SUR.ceiling(w, a, "flour"))
    pile.storage["grain"] = top - 1
    assert SUR.sinks(w, a) == [] and not any("flour" in g for g in goals(w, a, 300))
    pile.storage.update({"grain": 150, "flour": 30})  # (30 flour: more than any ordinary bill grinds up to)
    assert SUR.sinks(w, a) == []  # nobody has ever baked a loaf: flour would feed no one
    known(w, a, "loaf")
    offered = SUR.sinks(w, a)
    assert [p["steps"] for _, p in offered] == [[{"do": "work", "at": "mill", "what": "flour", "target": mill.id}]]
    assert f"work at the mill ({item_name('flour')})" in goals(w, a, 400)  # instinct chooses it
    shifts = _shifts_until_none(w, a)
    flour = pile.storage["flour"]
    assert shifts >= 2 and ftop <= flour < ftop + 20  # real shifts, and none begun at the ceiling
    assert pile.storage["grain"] == 150 - (flour - 30) and mill.produced == {"flour": flour - 30} and a.stats["shifts"] == shifts
    # ...and with grain back at its ceiling the grinding stops, whatever room flour has
    pile.storage.update({"flour": 0, "grain": top + 5})
    assert _shifts_until_none(w, a) == 1 and pile.storage["grain"] < top and pile.storage["flour"] < ftop


def test_wood_over_its_ceiling_is_burned_to_charcoal_at_the_kiln_until_charcoal_reaches_its_own():
    w, a, pile = grown()
    kiln = put(w, "kiln", a, near=(a.x + 5, a.y))
    w.learned(a, "recipe:charcoal", "taught")
    top, ctop = int(SUR.ceiling(w, a, "wood")), int(SUR.ceiling(w, a, "charcoal"))
    pile.storage["wood"] = top - 1
    assert SUR.sinks(w, a) == []
    pile.storage.update({"wood": 120, "charcoal": 30})  # (30 charcoal: more than any ordinary bill burns up to)
    assert SUR.sinks(w, a) == []  # nobody has ever smelted anything: the charcoal would go into nothing
    known(w, a, "copper")
    assert [p["steps"] for _, p in SUR.sinks(w, a)] == [[{"do": "work", "at": "kiln", "what": "charcoal", "target": kiln.id}]]
    assert f"work at the kiln ({item_name('charcoal')})" in goals(w, a, 400)  # instinct chooses it
    shifts = _shifts_until_none(w, a)
    coal = pile.storage["charcoal"]
    assert shifts >= 2 and ctop <= coal < ctop + 22
    assert pile.storage["wood"] == 120 - (coal - 30) // 2 and kiln.produced == {"charcoal": coal - 30}
    pile.storage.update({"charcoal": 0, "wood": top + 5})
    assert _shifts_until_none(w, a) == 1 and pile.storage["wood"] < top and pile.storage["charcoal"] < ctop
    # a chit that doesn't know how is offered nothing: instinct knows only what the chit knows
    pile.storage["wood"] = 120
    other = next(o for o in w.agents.values() if o is not a)
    assert SUR.sinks(w, other) == []


def test_no_sink_without_its_station_in_reach():
    w, a, pile = grown()
    for k in ("recipe:flour", "recipe:charcoal"):
        w.learned(a, k, "taught")
    known(w, a, "loaf"), known(w, a, "copper")
    pile.storage.update({"grain": 100, "wood": 100, "loaf": 20})
    assert SUR.over(w, a, "grain") and SUR.over(w, a, "wood") and SUR.sinks(w, a) == []


def test_seed_over_its_ceiling_is_sown_from_the_stores():
    w, a, pile = grown()
    farm = put(w, "farm", a, near=(a.x + 4, a.y))
    farm.planted = False  # (a field harvested by a chit with no seed to sow it again)

    def plant():
        return next(p for p in draws(w, a, 400) if p["goal"] == "plant the farm")["steps"]

    assert plant() == [{"do": "gather", "what": "seeds", "qty": 2}, {"do": "plant", "target": farm.id}]
    pile.storage["seeds"] = 200
    steps = plant()
    assert steps == [{"do": "take", "what": "seeds", "qty": 2}, {"do": "plant", "target": farm.id}]
    follow(w, a, steps)
    assert farm.planted and pile.storage["seeds"] == 198 and not a.stats.get("gathered_seeds")


def test_seed_over_its_ceiling_opens_a_new_field():
    w, a, pile = grown()
    farm = put(w, "farm", a, near=(a.x + 4, a.y))
    farm.planted = True
    w.learned(a, "design:farm", "taught")
    pile.storage["wood"] = 20
    name = f"build a {DESIGNS['farm'].name}"
    pile.storage["seeds"] = int(SUR.ceiling(w, a, "seeds")) - 1
    assert name not in goals(w, a, 400)  # one field feeds the chits here
    pile.storage["seeds"] = 200
    plan = next(p for p in draws(w, a, 400) if p["goal"] == name)
    follow(w, a, plan["steps"])
    fields = [s for s in w.structures.values() if s.design == "farm"]
    assert len(fields) == 2 and pile.storage["seeds"] == 197  # the new field took its three seeds from the stores


def test_flour_a_shift_ground_is_baked_before_more_grain_is_ground():
    w, a, pile = grown()
    put(w, "mill", a, near=(a.x + 5, a.y))
    put(w, "kiln", a, near=(a.x - 5, a.y))  # (a kiln is a fire to bake at)
    for k in ("recipe:flour", "recipe:loaf"):
        w.learned(a, k, "taught")
    pile.storage["flour"] = 10
    (_, plan), = BI._mill_and_bake(w, a)
    assert plan["steps"][:2] == [{"do": "take", "what": "flour", "qty": 4}, {"do": "craft", "what": "loaf", "qty": 2}]
    follow(w, a, plan["steps"])
    assert pile.storage["flour"] == 6 and pile.storage.get("loaf", 0) + a.inventory.get("loaf", 0) == 2


# ---------------------------------------------------------------------------- food first
def test_food_first_grain_is_not_ground_while_the_stores_are_short_of_food(monkeypatch):
    # (a one-day grain reserve, so the stores can be over it and short of food at once: at the game's four days, being
    # over the reserve already means more than three days of food; the guard is what is tested here)
    monkeypatch.setattr(SUR, "GRAIN_DAYS", 1.0)
    w, a, pile = grown(20)
    put(w, "mill", a, near=(a.x + 5, a.y))
    w.learned(a, "recipe:flour", "taught")
    known(w, a, "loaf")
    pile.storage.update({"grain": int(SUR.ceiling(w, a, "grain")) + 10, "flour": 30})
    assert SUR.over(w, a, "grain") and food.short(w, a)  # over a day of food in grain, under three days of food
    assert SUR.sinks(w, a) == [] and not any("flour" in g for g in goals(w, a, 300))
    assert "fill the stores" in goals(w, a, 60, "_communal")  # ...and the stores are filled first, as before
    pile.storage["loaf"] = 60
    assert not food.short(w, a) and len(SUR.sinks(w, a)) == 1 and any("flour" in g for g in goals(w, a, 300))


# ---------------------------------------------------------------------------- no more stockpiles for plenty
def _can_build_a_stockpile(w, a):
    a.knows.pop("design:warehouse", None)
    w.learned(a, "design:stockpile", "taught")
    for k, n in DESIGNS["stockpile"].material_map.items():
        a.add(k, n)


def test_stores_full_of_plenty_are_no_reason_for_another_stockpile():
    w, a, pile = grown()
    _can_build_a_stockpile(w, a)
    full = int(actions.STOCKPILE_CAP * actions.GOODS_SHARE)
    pile.storage["pot"] = full  # full of what has no ceiling: more room is the answer
    assert actions.stockpile_room(pile) == 0 and not SUR.glut(w, a)
    assert Instinct._more_storage(w, a)["goal"] == "build a stockpile"
    assert "build a stockpile" in goals(w, a, 300)
    pile.storage.clear()
    pile.storage["wood"] = full  # full of wood, far over its ceiling: less wood is the answer
    assert actions.stockpile_room(pile) == 0 and SUR.glut(w, a)
    assert "build a stockpile" not in goals(w, a, 300)
    pile.storage["wood"] = int(SUR.ceiling(w, a, "wood")) + SUR.GLUT_ROOM  # (over by no more than a store's spare room)
    pile.storage["pot"] = full - pile.storage["wood"]
    assert actions.stockpile_room(pile) == 0 and not SUR.glut(w, a)


# ---------------------------------------------------------------------------- berry pips
def test_pips_are_not_kept_far_from_the_stores_when_the_stores_at_home_hold_seed_enough():
    """Berries are picked a long walk from the stores, where no store's seed is in sight: every village in the 60-day
    runs held about 200 seeds, 30 in each store (what the mice leave), with pips the only thing still coming in."""
    w, a, pile = grown()
    hut = put(w, "hut", a)
    a.home = hut.id
    pile.storage["seeds"] = actions.SEED_PLENTY
    assert actions.seeds_plenty(w, a.x, a.y)
    far = (a.x + 40, a.y) if a.x + 40 < w.w else (a.x - 40, a.y)
    assert not actions.seeds_plenty(w, *far)  # (out there no store is in sight)
    assert actions.seeds_plenty(w, *far, a)  # ...but its village holds plenty
    pile.storage["seeds"] = actions.SEED_PLENTY - 1
    assert not actions.seeds_plenty(w, *far, a)


def test_a_picker_far_from_home_keeps_no_pips_while_its_village_holds_seed_enough():
    from types import SimpleNamespace

    from test_seed_surplus import picks_with_pips

    w, a, _ = grown()
    here = SimpleNamespace(x=a.x, y=a.y)
    far = next((x, y) for x, y in ((a.x - 36, a.y), (a.x + 36, a.y), (a.x, a.y - 36), (a.x, a.y + 36))
               if w.inb(x, y) and w.find_site("stockpile", x, y, 3) and w.find_site("hut", x, y, 3))
    pile, hut = put(w, "stockpile", a, near=far, radius=3), put(w, "hut", a, near=far, radius=3)
    for s in list(w.structures.values()):
        if s is not pile and s is not hut:
            del w.structures[s.id]  # (only the stores far off, by its home)
    pile.storage["seeds"] = actions.SEED_PLENTY
    assert pile.dist(a.x, a.y) > 30
    a.home = None
    assert picks_with_pips(w, a, here, 60) > 0  # a stranger out here keeps the pips: no store of seed in sight
    a.home = hut.id
    assert picks_with_pips(w, a, here, 60) == 0  # one whose village holds plenty doesn't
