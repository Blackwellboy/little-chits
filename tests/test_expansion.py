"""Spreading out (the audit of day 1,361): the live worlds used a few percent of a 512 island. The world held 60 chits,
every child was born in the big village and all six daughter villages died with their founders, World B's model-minded
pioneers founded 1 village in 14 tries, the ore lay inside rock nobody could walk on, sand ran out near home, and chits
went to dig ore with no pick."""

import random

from chits.brain import instinct as I
from chits.brain import outposts as OP
from chits.brain.mind import Mind
from chits.sim import buildings as BLD
from chits.sim import pioneers as PI
from chits.sim import terrain as T
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import BOND_TO_BREED, World


class Always(random.Random):
    def random(self):
        return 0.0


def _village(n=44):
    w = World("A", "A", 5, "direct", 128, n)
    ags = list(w.agents.values())
    for o in ags:
        o.hunger = o.energy = o.warmth = o.health = 95.0
    cx, cy = ags[0].x, ags[0].y
    for i in range(0, len(ags), 2):
        hut = w.place_site("hut", *w.find_site("hut", cx, cy, 16, reach=(cx, cy)), ags[i])
        w.complete_structure(hut, ags[i])
        for o in ags[i:i + 2]:
            o.home = hut.id
    w.tick = PI.START_DAY * TICKS_PER_DAY
    return w


def _pair(w, a, b):
    for x, y in ((a, b), (b, a)):
        x.like(y.id, BOND_TO_BREED + 5)
        x.last_birth_tick = -10 ** 6
        x.parents = []
    b.x, b.y = a.x, a.y
    b.home = a.home


def test_the_world_holds_more_chits_and_small_villages_have_their_children_first(monkeypatch):
    import chits.sim.world as W

    from types import SimpleNamespace

    assert W.POP_CAP == 60 and W.World.pop_cap(SimpleNamespace(w=512, h=512)) == W.POP_CAP_BIG == 90
    assert W.World.pop_cap(SimpleNamespace(w=128, h=128)) == 60  # small islands as before
    w = _village(20)
    ags = sorted(w.agents.values(), key=lambda a: a.id)
    big, small = ags[:2], ags[2:4]
    _pair(w, *big)
    _pair(w, *small)
    rng = Always(1)
    w.rng_for = lambda name, key=None: rng
    monkeypatch.setattr(W, "POP_CAP", len(w.agents) + 1)  # room for one child
    sizes = {a.id: PI.VILLAGE_ROOM - 5 for a in ags}  # (below the room where a village waits)
    sizes.update({a.id: 6 for a in small})
    monkeypatch.setattr(PI, "village_sizes", lambda world: (sizes, 2))
    w._births()
    child = max(w.agents.values(), key=lambda a: a.born)
    assert set(child.parents) == {small[0].id, small[1].id}  # the small village's couple, though the big one came first


def test_a_full_village_waits_while_another_has_room_but_never_when_it_is_the_only_one(monkeypatch):
    w = _village(20)
    ags = sorted(w.agents.values(), key=lambda a: a.id)
    _pair(w, ags[0], ags[1])
    rng = Always(1)
    w.rng_for = lambda name, key=None: rng
    sizes = {a.id: PI.VILLAGE_ROOM for a in ags}
    n = len(w.agents)
    monkeypatch.setattr(PI, "village_sizes", lambda world: (sizes, 2))
    w._births()
    assert len(w.agents) == n
    monkeypatch.setattr(PI, "village_sizes", lambda world: (sizes, 1))
    w._births()
    assert len(w.agents) == n + 1


def test_pioneers_are_young_and_go_as_couples():
    w = _village(44)
    [v] = PI.villages(w)
    ags = [w.agents[i] for i in v.residents]
    shy = [a for a in ags if not a.is_child(w.tick)][-2:]  # the least bold two, who would have stayed behind
    for a in shy:
        a.traits.update({"curiosity": 0.0, "caution": 1.0})
        a.born = w.tick - 20 * TICKS_PER_DAY
    _pair(w, *shy)
    old = next(a for a in ags if a not in shy)
    old.born = w.tick - (PI.PARTY_AGE + 1) * TICKS_PER_DAY
    old.traits.update({"curiosity": 1.0, "caution": 0.0})
    party = PI._party(w, v)
    assert len(party) == PI.PARTY and shy[0] in party and shy[1] in party
    assert old not in party and all(a.age(w.tick) < PI.PARTY_AGE for a in party)


def _rock_with_ore(w):
    """A block of rock beside the first chit, with a vein of ore two tiles in; a mine at its face."""
    a = next(iter(w.agents.values()))
    for i, k in enumerate(w.res_kind):  # no other ore on this map
        if k == T.R_ORE:
            w.res_amt[i] = 0
    x0, y0 = a.x + 4, a.y - 3
    for y in range(y0, y0 + 7):
        for x in range(x0, x0 + 7):
            i = y * w.w + x
            w.tiles[i], w.res_kind[i], w.res_amt[i] = T.ROCK, T.R_NONE, 0
    vein = (y0 + 3) * w.w + x0 + 3
    w.res_kind[vein], w.res_amt[vein] = T.R_ORE, 6
    for y in range(y0 - 1, y0 + 8):
        for x in (x0 - 1, x0 - 2, x0 - 3):
            i = y * w.w + x
            w.tiles[i], w.res_kind[i], w.res_amt[i] = T.GRASS, T.R_NONE, 0
    w.structures.clear()
    w.occupied.clear()
    w.rebuild_block()
    mine = w.place_site("mine", x0 - 3, y0 + 2, a)
    w.complete_structure(mine, a)
    return a, vein, mine


def test_a_mine_tunnels_into_the_rock_towards_the_ore_and_the_tunnel_is_kept():
    w = World("A", "A", 3, "direct", 64, 3)
    a, vein, mine = _rock_with_ore(w)
    vx, vy = vein % w.w, vein // w.w
    assert not w.stand_tiles_for(vx, vy)  # sealed in the rock
    for _ in range(4):
        BLD._mines(w)
    assert w.stand_tiles_for(vx, vy), "the tunnel reached the ore"
    assert all(w.tunnels[i] == mine.id and i in w.roads for i in w.tunnels) and len(w.tunnels) <= 4
    assert any(w.nearest_resource(a.x, a.y, k, 26) is not None for k in ("ore", "iron_ore"))
    assert any(e.kind == "tunnel" for e in w.events)
    w2 = World.from_dict(w.to_dict())
    assert w2.tunnels == w.tunnels and w2.stand_tiles_for(vx, vy)


def test_a_mine_digs_no_tunnel_where_there_is_no_ore_and_stops_at_its_limit(monkeypatch):
    w = World("A", "A", 3, "direct", 64, 3)
    a, vein, mine = _rock_with_ore(w)
    w.res_amt[vein] = 0
    BLD._mines(w)
    assert not w.tunnels
    w.res_amt[vein] = 6
    monkeypatch.setattr(BLD, "MINE_TUNNEL_MAX", 1)
    for _ in range(3):
        BLD._mines(w)
    assert len(w.tunnels) == 1


def test_a_mill_grinds_stone_into_sand_when_the_stockpiles_run_short():
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    mill = w.place_site("mill", *w.find_site("mill", a.x, a.y, 12), a)
    w.complete_structure(mill, a)
    pile = w.place_site("stockpile", *w.find_site("stockpile", mill.x, mill.y, 8), a)
    w.complete_structure(pile, a)
    pile.storage.update({"stone": 20})
    BLD._mills(w)
    assert pile.storage["sand"] == BLD.MILL_SAND and pile.storage["stone"] == 20 - BLD.MILL_SAND
    pile.storage["sand"] = BLD.SAND_SHORT
    BLD._mills(w)
    assert pile.storage["sand"] == BLD.SAND_SHORT  # enough: stone stays stone
    assert any(e.kind == "mill_sand" for e in w.events)


def test_a_chit_fetches_what_it_remembers_from_far_away():
    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    home = w.structures[a.home]
    pile = w.place_site("stockpile", *w.find_site("stockpile", home.x, home.y, 8), a)
    w.complete_structure(pile, a)
    a.knows["recipe:brick"] = {"status": "worked"}
    a.hunger = a.energy = a.health = 95.0
    a.inventory.clear()
    for i, k in enumerate(w.res_kind):  # no sand anywhere near home
        if k == T.R_SAND:
            w.res_amt[i] = 0
    fx, fy = home.x + 50, home.y
    a.remember(w.tick, f"I found sand at ({fx},{fy})", 3, "place")
    p = OP.trip_plan(w, a)
    assert p and p["steps"][0] == {"do": "go", "to": f"{fx},{fy}"} and p["steps"][1]["what"] == "sand"
    assert p["steps"][-1] == {"do": "store", "what": "sand", "target": pile.id}
    a.reflex_rest["scarce:sand"] = w.tick + TICKS_PER_DAY  # (instinct drops other plans that gather it)
    assert OP.trip_plan(w, a) is not None
    a.goal = "fetch sand from far away"
    b = next(o for o in w.agents.values() if o is not a and not o.is_child(w.tick))
    b.knows["recipe:brick"] = {"status": "worked"}
    b.remember(w.tick, f"I found sand at ({fx},{fy})", 3, "place")
    b.hunger = b.energy = b.health = 95.0
    b.inventory.clear()
    assert OP.trip_plan(w, b) is None  # one trip at a time for a village this size
    a.goal = ""
    a.hunger = 40.0
    assert OP.trip_plan(w, a) is None  # only a fed chit goes


def test_no_trip_plan_is_thrown_away_for_gathering_something_scarce():
    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.reflex_rest["scarce:sand"] = w.tick + TICKS_PER_DAY
    trip = {"goal": "fetch sand from far away", "thought": "", "steps": [
        {"do": "go", "to": "1,1"}, {"do": "gather", "what": "sand", "qty": 6, "_far": True}]}
    near = {"goal": "sand", "thought": "", "steps": [{"do": "gather", "what": "sand", "qty": 6}]}
    inst = I.Instinct()
    for plan, kept in ((trip, True), (near, False)):
        inst._survive = lambda world, a, rng, p=plan: dict(p, steps=[dict(s) for s in p["steps"]])
        out = inst.plan(w, a)
        assert (out["goal"] == plan["goal"]) == kept


def test_a_pick_comes_before_the_ore():
    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.inventory.clear()
    a.inventory.update({"wood": 2, "stone": 2, "cord": 2})
    a.knows["recipe:stone_pick"] = {"status": "worked"}
    steps = I._supply_steps(a, {"ore": 2}, w)
    assert [s["do"] for s in steps] == ["craft", "gather"] and steps[0]["what"] == "stone_pick"
    got = I.tools_first(w, a, [{"do": "gather", "what": "ore", "qty": 2}, {"do": "store", "what": "ore"}])
    assert got[0] == {"do": "craft", "what": "stone_pick", "qty": 1} and got[1]["what"] == "ore"
    a.inventory["stone_pick"] = 1
    assert I._supply_steps(a, {"ore": 2}, w) == [{"do": "gather", "what": "ore", "qty": 2}]
    assert len(I.tools_first(w, a, [{"do": "gather", "what": "ore", "qty": 2}])) == 1
    a.inventory.pop("stone_pick")
    a.knows.pop("recipe:stone_pick")
    assert I._supply_steps(a, {"ore": 2}, w) == [{"do": "gather", "what": "ore", "qty": 2}]  # no way to a pick: as before


def test_a_pick_that_cant_be_finished_leaves_no_half_made_steps(monkeypatch):
    from types import SimpleNamespace

    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.inventory.clear()
    a.knows["recipe:stone_pick"] = {"status": "worked"}
    real = I._rec
    fake = SimpleNamespace(key="stone_pick", qty=1, inputs=(("stone", 1), ("unobtainium", 1)), station=None)
    monkeypatch.setattr(I, "_rec", lambda agent, key: fake if key == "stone_pick" else real(agent, key))
    # the stone is gathered before the pick's second input turns out to be impossible: that step isn't kept
    assert I._supply_steps(a, {"ore": 2}, w) == [{"do": "gather", "what": "ore", "qty": 2}]


def test_a_pioneers_duty_comes_before_its_model():
    w = _village(44)
    PI.daily(w)
    em = w.civic["emigration"]
    a = w.agents[em["members"][0]]
    a.inventory.update({"wood": 20, "stone": 6, "fiber": 8})
    w.tick = (w.tick // TICKS_PER_DAY + 1) * TICKS_PER_DAY + 100  # morning
    for strict, duty in ((False, True), (True, False)):
        m = Mind(None)
        m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1"})
        m.assign(w, "test")
        m.strict = strict
        asked = []
        m._ask = lambda world, agent, brain: asked.append(agent.id)
        a.plan, a.pending_plan, a.thinking, a.plan_source = [], None, False, ""
        m.hook(w, a)
        assert (a.plan_source == "instinct-duty") == duty and (asked == []) == duty, strict
        assert not duty or a.plan[-1]["do"] == "build"


def test_a_models_plan_to_dig_ore_gets_a_pick_first():
    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.inventory.clear()
    a.inventory.update({"wood": 2, "stone": 2, "cord": 2})
    a.knows["recipe:stone_pick"] = {"status": "worked"}
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1"})
    m.assign(w, "test")
    m._ask = lambda world, agent, brain: None
    a.plan, a.thinking = [], False
    a._decision = None
    a.pending_plan = {"steps": [{"do": "gather", "what": "ore", "qty": 2}], "goal": "copper"}
    m.hook(w, a)
    assert a.plan_source.startswith("model") and a.plan[0]["what"] == "stone_pick" and a.plan[1]["what"] == "ore"


def test_a_curious_chit_picks_up_and_studies_a_strange_object_once():
    from chits.brain import ground as GR

    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.traits["curiosity"] = 0.9
    w.put_ground(a.x + 3, a.y, "meteorite", 1)
    p = GR.curio_plan(w, a)
    assert p["steps"] == [{"do": "pickup", "what": "meteorite"}, {"do": "inspect", "what": "meteorite"}]
    assert GR.curio_plan(w, a) is None  # not again for a few days
    w.put_ground(a.x - 3, a.y, "alien_ship", 1)
    assert GR.curio_plan(w, a)["steps"] == [{"do": "go", "to": f"{a.x - 3},{a.y}"}, {"do": "inspect", "what": "alien_ship"}]
    b = next(o for o in w.agents.values() if o is not a and not o.is_child(w.tick))
    b.x, b.y = a.x, a.y
    b.traits["curiosity"] = 0.1
    assert GR.curio_plan(w, b) is None  # an incurious chit leaves it be


def test_loose_goods_are_carried_in_and_used_but_not_when_there_is_nowhere_to_put_them():
    from chits.brain import ground as GR

    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.inventory.clear()
    a.hunger = 90.0
    home = w.structures[a.home]
    w.put_ground(home.x + 2, home.y, "charcoal", 40)
    assert GR.tidy_plan(w, a) is None  # no stockpile yet: it would only be dropped again
    pile = w.place_site("stockpile", *w.find_site("stockpile", home.x, home.y, 8), a)
    w.complete_structure(pile, a)
    p = GR.tidy_plan(w, a)
    assert p["steps"] == [{"do": "pickup", "what": "charcoal"}, {"do": "store", "what": "charcoal", "target": pile.id}]
    a.x, a.y = home.x, home.y
    steps = I._supply_steps(a, {"charcoal": 3}, w)
    assert steps == [{"do": "pickup", "what": "charcoal"}]  # the loose charcoal, not a trip to make more


def test_full_hands_and_full_stockpiles_build_another_stockpile_instead_of_dropping():
    w = _village(10)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    a.knows["design:stockpile"] = {"status": "worked"}
    home = w.structures[a.home]
    pile = w.place_site("stockpile", *w.find_site("stockpile", home.x, home.y, 8), a)
    w.complete_structure(pile, a)
    pile.storage.update({"stone": 10 ** 4})  # full
    a.inventory.clear()
    a.inventory.update({"wood": 12, "cord": 2, "stone": 20})
    while a.free_space() > 3:
        a.inventory["stone"] += 1
    p = I.Instinct()._declutter(w, a, random.Random(1))
    assert p["goal"] == "build a stockpile" and p["steps"][-1] == {"do": "build", "what": "stockpile", "near": f"{home.x},{home.y}"}
    site = w.place_site("stockpile", *w.find_site("stockpile", home.x, home.y, 8), a)  # one going up already
    assert I.Instinct()._declutter(w, a, random.Random(1))["goal"] == "lighten my load"
    w.complete_structure(site, a)
    site.storage.update({"stone": 10 ** 4})
    for _ in range(4):
        extra = w.place_site("stockpile", *w.find_site("stockpile", home.x, home.y, 20), a)
        w.complete_structure(extra, a)
        extra.storage.update({"stone": 10 ** 4})
    assert I.Instinct()._declutter(w, a, random.Random(1))["goal"] == "lighten my load"  # six is enough here


def test_a_full_stockpile_is_rebuilt_as_a_warehouse_that_keeps_its_goods_and_holds_four_times_as_much():
    from chits.sim import actions
    from chits.sim.items import DESIGNS

    w = _village(14)
    a = next(a for a in w.agents.values() if not a.is_child(w.tick))
    home = w.structures[a.home]
    pile = w.place_site("stockpile", *w.find_site("stockpile", home.x, home.y, 8), a)
    w.complete_structure(pile, a)
    pile.storage.update({"stone": 200})
    before = actions.stockpile_room(pile)
    a.knows["design:stockpile"] = a.knows["design:warehouse"] = {"status": "worked"}
    a.inventory.clear()
    a.inventory.update({"wood": 12, "stone": 10, "cord": 3})
    while a.free_space() > 3:
        a.inventory["stone"] += 1
    p = I.Instinct()._declutter(w, a, random.Random(1))
    assert p["steps"] == [{"do": "upgrade", "to": "warehouse", "target": pile.id}]
    a.x, a.y = pile.x, pile.y
    step = dict(p["steps"][0])
    for _ in range(6000):
        w.tick += 1
        a.hunger = a.energy = a.warmth = 95.0
        res = actions.advance(w, a, step)
        if res != actions.RUNNING:
            break
    assert pile.design == "warehouse" and pile.storage["stone"] == 200, (res, pile.design)
    assert actions.stockpile_room(pile) > before + 3 * actions.STOCKPILE_CAP * 0.5
    assert pile in w.structures_near(a.x, a.y, 25, "stockpile")  # a warehouse is where the stockpiles are looked for
    assert DESIGNS["warehouse"].size == (2, 2)
