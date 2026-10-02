"""Ore by element (issue #4). One "ore" made copper and iron both; now each deposit is copper or iron ore (about two in
three iron), fixed by its place and the world's seed. Copper smelts from copper ore, iron from iron ore, a mine's seam
gives both, and a chit gathering one kind goes to a deposit of that kind."""

from chits.sim import actions
from chits.sim import terrain as T
from chits.sim.items import IRON_ORE_SHARE, ITEMS, RECIPES, match_recipe, normalize_item
from chits.sim.world import World


def test_iron_smelts_from_iron_ore_and_copper_from_copper_ore():
    assert dict(RECIPES["iron"].inputs) == {"iron_ore": 2, "charcoal": 2}
    assert dict(RECIPES["copper"].inputs) == {"ore": 1, "charcoal": 1}
    assert match_recipe({"ore": 2, "charcoal": 2}, "furnace") is None  # (copper ore no longer makes iron)
    assert ITEMS["iron_ore"].name == "iron ore" and ITEMS["ore"].name == "copper ore"
    assert normalize_item("iron ore") == "iron_ore" and normalize_item("copper ore") == "ore"


def test_each_deposit_is_one_ore_fixed_by_its_place_and_iron_is_the_commoner():
    kinds = []
    for seed in (7, 8, 9, 10):
        w = World("A", "A", seed, "direct", 128, 2)
        tiles = [i for i in range(w.w * w.h) if w.res_kind[i] == T.R_ORE]
        mine = [w.ore_item(i) for i in tiles]
        assert mine == [World("A", "A", seed, "direct", 128, 2).ore_item(i) for i in tiles]  # (the same every load)
        kinds += mine
    assert len(kinds) > 80
    share = 100 * kinds.count("iron_ore") / len(kinds)
    assert 50 < share < 80, share  # iron the commoner, copper not rare


def test_a_chit_gathering_iron_ore_digs_an_iron_deposit():
    w = World("A", "A", 7, "direct", 128, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["stone_pick"] = 1
    pos = w.nearest_resource(a.x, a.y, "iron_ore", 200)
    assert pos is not None and w.ore_item(pos[1] * w.w + pos[0]) == "iron_ore"
    a.x, a.y = next(iter(w.stand_tiles_for(*pos)))
    s = {}
    res = actions.RUNNING
    for _ in range(2000):
        w.tick += 1
        a.hunger = a.energy = a.warmth = 95.0
        res = actions._do_gather(w, a, {"do": "gather", "what": "iron_ore", "qty": 2}, s)
        if res != actions.RUNNING:
            break
    assert res == actions.DONE and a.inventory.get("iron_ore") == 2 and not a.inventory.get("ore")
