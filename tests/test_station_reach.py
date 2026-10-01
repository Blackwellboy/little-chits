"""Instinct planned crafts at stations out of reach: the live World B crafted charcoal for its copper with no kiln
nearby 590 times in 8 minutes (the loop detector's first catch on the live game)."""

from chits.brain import instinct as I
from chits.sim import actions
from chits.sim.world import World


def setup():
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = a.energy = a.warmth = 100
    for k in ("recipe:copper", "recipe:charcoal"):
        a.learn(k, "taught", w.tick)
    a.inventory.update({"ore": 1, "wood": 2})
    return w, a


def building(w, a, design):
    x, y = w.find_site(design, a.x, a.y)
    st = w.place_site(design, x, y, a)
    w.complete_structure(st, a)
    return st


def crafts(steps):
    return [s["what"] for s in steps or [] if s["do"] == "craft"]


def test_an_input_made_at_a_station_out_of_reach_is_not_planned():
    w, a = setup()
    building(w, a, "furnace")
    assert not w.nearest_station(a.x, a.y, "kiln", actions.STATION_REACH)
    assert I._supply_steps(a, {"copper": 1}, w) is None  # no kiln: no charcoal, so no copper this way
    assert I._supply_steps(a, {"copper": 1}) is not None  # (without a world to look at, as before)


def test_with_the_station_in_reach_or_the_input_in_store_it_is():
    w, a = setup()
    building(w, a, "furnace")
    building(w, a, "kiln")
    assert crafts(I._supply_steps(a, {"copper": 1}, w)) == ["charcoal", "copper"]
    w, a = setup()
    building(w, a, "furnace")
    pile = building(w, a, "stockpile")
    pile.storage["charcoal"] = 3
    steps = I._supply_steps(a, {"copper": 1}, w)
    assert crafts(steps) == ["copper"] and {"do": "take", "what": "charcoal", "qty": 1} in steps


def test_crafting_a_thing_checks_its_inputs_stations_too():
    w, a = setup()
    building(w, a, "furnace")
    assert I._craft_steps(a, "copper", world=w) == []
    assert crafts(I._craft_steps(a, "copper")) == ["charcoal", "copper"]  # (no world: as before)
    building(w, a, "kiln")
    assert crafts(I._craft_steps(a, "copper", world=w)) == ["charcoal", "copper"]


def test_instinct_never_loops_on_a_missing_station():
    # the live path: a chit that knows the copper axe wants copper, has a furnace, and no kiln in reach
    # (housed, by a fire, hands free: before the fix 146 of these 400 plans crafted charcoal)
    w, a = setup()
    a.learn("recipe:copper_axe", "taught", w.tick)
    a.inventory.clear()
    a.inventory.update({"ore": 1, "wood": 1})
    building(w, a, "furnace")
    building(w, a, "campfire")
    a.home = building(w, a, "hut").id
    goals = set()
    for t in range(400):
        w.tick += 7
        p = I.Instinct().plan(w, a)
        goals.add(p["goal"])
        assert "charcoal" not in crafts(p["steps"]), p
    assert "study the furnace" in goals  # (it still plans around the furnace it has)


def test_helping_at_a_site_doesnt_plan_an_input_it_cant_make_here():
    # (_help_site had no world of its own: the first cut of this fix raised NameError there, caught by the A/B)
    w, a = setup()
    a.learn("recipe:brick", "taught", w.tick)
    a.inventory.update({"clay": 4})
    site = w.place_site("kiln", *w.find_site("kiln", a.x, a.y), a)
    site.needs = {"brick": 2}
    ins = I.Instinct()
    ins._world = w
    assert crafts(ins._help_site(a, site, "help", "t")["steps"]) == []  # no kiln standing yet: no brick
    building(w, a, "kiln")
    assert crafts(ins._help_site(a, site, "help", "t")["steps"]) == ["brick"]


def test_one_station_reach_everywhere():
    # audit F5: planners gave up on stations at 15, 20 or 25 tiles while the actions walk 45 (on the live save,
    # 65% of World A's chances at the steam engine ended on "no forge within 25")
    import pathlib
    import re

    from chits.brain import instinct as ins_mod

    root = pathlib.Path(actions.__file__).resolve().parents[1]
    literal = re.compile(r"nearest_station\([^)]*,\s*\d+\s*\)")
    found = [f"{p.relative_to(root)}: {m.group(0)}" for p in root.rglob("*.py") for m in literal.finditer(p.read_text())]
    assert found == [], found
    assert actions.WORK_REACH == actions.STATION_REACH  # can I use it: one reach
    assert ins_mod.WORK_NEAR == actions.STATION_NEAR < actions.STATION_REACH  # would I go by choice: nearer


def test_a_forge_thirty_tiles_off_is_in_the_models_suggestions():
    # the experiments a model is offered listed fire, kiln, furnace and workshop within 20 tiles: never a forge
    from chits.brain import prompt as P
    from test_machine_age import machine_age_village

    w, forge, pile = machine_age_village()
    a = min(w.agents.values(), key=lambda o: max(abs(o.x - pile.center()[0]), abs(o.y - pile.center()[1])))
    assert 25 < max(abs(a.x - forge.center()[0]), abs(a.y - forge.center()[1])) <= actions.STATION_REACH
    assert any("forge" in x for x in P.untried_pairs(w, a, n=60))


def test_f30_directed_craft_can_use_a_far_station_that_is_too_far_for_a_spare_shift():
    """F30: F5 changed an accounting bucket, not just total manufacture.

    A directed needed craft may walk out to STATION_REACH, while an optional production shift is considered only
    within STATION_NEAR. So a station 20-45 tiles away can produce through a normal craft (made_*) where it cannot
    be selected as a spare work shift (produced_*).
    """
    w = World("A", "A", 31, "direct", 96, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.learn("recipe:brick", "taught", w.tick)
    a.inventory.update({"clay": 2, "sand": 2})

    # Put a kiln beyond the voluntary-shift radius but inside the directed-use radius.
    spot = w.find_site("kiln", min(w.w - 5, a.x + 30), a.y, 8, reach=(a.x, a.y))
    assert spot is not None
    kiln = w.place_site("kiln", *spot, a)
    w.complete_structure(kiln, a)
    dist = max(abs(kiln.center()[0] - a.x), abs(kiln.center()[1] - a.y))
    assert actions.STATION_NEAR < dist <= actions.STATION_REACH

    # Give that kiln a real village store with inputs and output room, so distance is the only reason a shift
    # can disappear from consideration.
    pxy = w.find_site("stockpile", kiln.x + 3, kiln.y, 8, reach=(a.x, a.y))
    assert pxy is not None
    pile = w.place_site("stockpile", *pxy, a)
    w.complete_structure(pile, a)
    pile.storage.update({"clay": 20, "sand": 20})

    # A requested brick can still be physically made there...
    steps = I._craft_steps(a, "brick", 1, world=w)
    assert any(s.get("do") == "craft" and s.get("what") == "brick" for s in steps)
    # ...and the exact same station has a valid brick production bill if we ask out to the directed-use radius...
    wide, _ = actions.plan_bill(w, a, {"kiln"}, prefer="brick", radius=actions.STATION_REACH)
    assert wide is not None and wide.st.id == kiln.id and wide.r.key == "brick"
    # ...but instinct will not volunteer that spare work shift from the nearer-by-choice radius.
    near, _ = actions.plan_bill(w, a, {"kiln"}, prefer="brick", radius=I.WORK_NEAR)
    assert near is None
