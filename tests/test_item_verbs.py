"""F35: every item has a verb. One test per use an item has in the simulator beyond being an ingredient (the table in
tests/test_item_uses.py names the test that proves each), and one per oddity the 2026-10-04 review found."""

import random

import pytest

from chits.brain import instinct as I
from chits.brain import prompt as P
from chits.sim import actions
from chits.sim import animals as AN
from chits.sim import buildings as BLD
from chits.sim.items import FUEL_VALUE, ITEMS, MEND_WITH, SHARP_FIBER
from chits.sim.world import Tablet, World

from test_buildings import put, run_step, village


@pytest.fixture(autouse=True)
def _item_uses_on(monkeypatch):
    """F35's item uses are off by default until A/B'd (items.ITEM_USES): these tests are about them, so switch them on."""
    from chits.sim import items as IT_

    monkeypatch.setattr(IT_, "ITEM_USES", True)


def _night(w):
    w.tick = 240 * 5 + 230  # late at night
    assert w.is_night


def _wolf(w, c):
    w.animals = {"w1": {"id": "w1", "kind": "wolf", "x": c.x + 1, "y": c.y, "hp": 10, "tame": False, "pen": ""}}


# ---------------------------------------------------------------------------------------------- fuel
def test_charcoal_feeds_a_fire_and_burns_longer_than_wood():
    w, (a, _) = village()
    fire = put(w, "campfire", a)
    fire.fuel = 0.0
    a.inventory["charcoal"] = 1
    assert run_step(w, a, {"do": "refuel", "target": fire.id}) == actions.DONE, "a fire took only wood"
    assert fire.fuel == FUEL_VALUE["charcoal"] and not a.has("charcoal") and fire.lit
    assert a.stats.get("refueled_charcoal") == 1
    fire.fuel = 0.0
    a.inventory["wood"] = 1
    assert run_step(w, a, {"do": "refuel", "target": fire.id}) == actions.DONE
    assert fire.fuel == FUEL_VALUE["wood"] < FUEL_VALUE["charcoal"]


def test_wood_is_burned_before_charcoal_and_empty_hands_are_told_both():
    w, (a, _) = village()
    fire = put(w, "campfire", a)
    fire.fuel = 40.0
    a.inventory.update({"wood": 1, "charcoal": 1})
    assert run_step(w, a, {"do": "refuel", "target": fire.id}) == actions.DONE
    assert a.has("charcoal") and not a.has("wood")  # the charcoal is kept for the furnace while there is wood
    a.inventory.clear()
    fire.fuel = 10.0
    assert "charcoal" in run_step(w, a, {"do": "refuel", "target": fire.id})


def test_instinct_feeds_a_fire_with_the_charcoal_in_hand():
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    pile.storage["wood"] = 40
    a.inventory["charcoal"] = 2
    assert I._fuel_steps(w, a) == []  # no trip to the stores for wood


# ---------------------------------------------------------------------------------------------- mending
@pytest.mark.parametrize("design,mat", [("stockpile", "cord"), ("furnace", "stone"), ("hut", "fiber"),
                                        ("brick_house", "brick"), ("kiln", "clay"), ("workshop", "stone"),
                                        ("campfire", "stone")])
def test_a_building_is_mended_with_the_plain_stuff_it_is_built_of(design, mat):
    w, (a, _) = village()
    st = put(w, design, a)
    st.durability = 30.0
    a.inventory[mat] = 1
    assert run_step(w, a, {"do": "repair", "target": st.id}) == actions.DONE, f"{mat} did not mend a {design}"
    assert st.durability == 75.0 and not a.has(mat)


def test_the_first_material_mends_first_and_nothing_precious_ever_does():
    assert actions.mend_materials("stockpile") == ["wood", "cord"]
    assert actions.mend_materials("lighthouse") == ["stone", "wood"]  # not its glass or copper
    assert actions.mend_materials("factory") == ["brick"]  # nobody patches a factory with a steam engine
    assert actions.mend_materials("street_lamp") == ["iron"]  # (its first material, as it always was)
    for k in MEND_WITH:
        assert k in ITEMS
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    pile.durability = 30.0
    a.inventory.update({"wood": 1, "cord": 1})
    assert run_step(w, a, {"do": "repair", "target": pile.id}) == actions.DONE
    assert a.has("cord") and not a.has("wood")
    assert not a.stats.get("mended_with_cord")
    mon = put(w, "monument", a)
    mon.durability = 30.0
    a.inventory.clear()
    a.inventory["copper"] = 2
    why = run_step(w, a, {"do": "repair", "target": mon.id})
    assert "stone" in why and a.inventory["copper"] == 2 and mon.durability == 30.0


def test_instinct_mends_with_what_it_carries_instead_of_fetching_wood():
    class Sure:
        def random(self):
            return 0.0

    w, (a, _) = village()
    a.born = -240 * 30
    pile = put(w, "stockpile", a)
    pile.durability = 30.0
    a.inventory["cord"] = 1
    plan = I.Instinct()._maintain(w, a, Sure())
    assert plan and plan["steps"] == [{"do": "repair", "target": pile.id}], plan


def test_instinct_mends_its_home_with_the_fiber_in_hand():
    class Sure:
        def random(self):
            return 0.0

    w, (a, _) = village()
    a.born = -240 * 30
    hut = put(w, "hut", a)
    hut.durability = 30.0
    a.home = hut.id
    a.inventory["fiber"] = 1
    plan = I.Instinct()._shelter(w, a, Sure())
    assert plan and plan["steps"] == [{"do": "repair", "target": hut.id}], plan


# ---------------------------------------------------------------------------------------------- a sharp stone
def _fiber_per_stroke(sharp: bool) -> int:
    w, (a, _) = village(seed=4)
    pos = w.nearest_resource(a.x, a.y, "fiber", 60)
    assert pos is not None
    i = pos[1] * w.w + pos[0]
    w.res_amt[i] = 9
    a.x, a.y = next(iter(w.stand_tiles_for(*pos)))
    if sharp:
        a.inventory["sharp_stone"] = 1
    step = {"do": "gather", "what": "fiber", "qty": 6}
    for _ in range(400):
        w.tick += 1
        actions.advance(w, a, step)
        if a.inventory.get("fiber", 0):
            break
    return a.inventory.get("fiber", 0)


def test_a_sharp_stone_in_hand_cuts_fiber_two_at_a_stroke():
    assert _fiber_per_stroke(False) == 1
    assert _fiber_per_stroke(True) == SHARP_FIBER == 2


# ---------------------------------------------------------------------------------------------- the oddities
@pytest.mark.parametrize("food", ["loaf", "cooked_meat", "bread", "berry_tart", "cooked_fish"])
def test_every_prepared_food_lifts_the_spirits(food):
    w, (a, _) = village()
    a.hunger, a.mood = 20.0, 50.0
    a.inventory[food] = 1
    assert run_step(w, a, {"do": "eat", "what": food}) == actions.DONE
    assert a.mood == 50.0 + actions.MEAL_MOOD, f"{food} gave no cheer"


def test_raw_food_gives_no_cheer():
    w, (a, _) = village()
    a.hunger, a.mood = 20.0, 50.0
    a.inventory["berries"] = 1
    assert run_step(w, a, {"do": "eat", "what": "berries"}) == actions.DONE
    assert a.mood == 50.0


def test_store_all_keeps_the_plough_in_hand():
    w, (a, _) = village()
    pile = put(w, "stockpile", a)
    a.inventory.update({"plough": 1, "stone": 3, "stone_axe": 1})
    assert run_step(w, a, {"do": "store", "what": "all"}) == actions.DONE
    assert a.has("plough") and a.has("stone_axe") and not a.has("stone")
    assert pile.storage.get("plough", 0) == 0 and pile.storage["stone"] == 3


def test_a_hungry_chit_making_room_keeps_its_plough_and_puts_down_a_spare_axe():
    w, (a, _) = village()
    a.inventory.update({"plough": 1, "stone_axe": a.capacity() - 1})
    assert a.free_space() == 0
    actions._drop_for_room(w, a, 1)
    assert a.has("plough") and a.free_space() == 1


def test_full_arms_never_drop_the_plough_as_junk():
    w, (a, _) = village()
    a.inventory["plough"] = a.capacity()
    a.plan = [{"do": "gather", "what": "wood", "qty": 2}]
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "gather" and a.inventory["plough"] == a.capacity()


def test_a_plough_comes_twice_as_fast_off_a_smithys_anvil():
    w, (a, _) = village()
    sm = put(w, "smithy", a)
    a.x, a.y = next(iter(w.stand_tiles_for_structure(sm)))
    assert BLD.craft_speed(w, a, "plough") == BLD.SMITHY_SPEED == BLD.craft_speed(w, a, "iron_axe")
    assert BLD.craft_speed(w, a, "wheel") == 1.0  # iron in it, but not a tool


def test_a_spear_wears_when_it_hunts():
    w, (a, _) = village(seed=5, size=96)
    deer = next(x for x in w.animals.values() if x["kind"] == "deer")
    a.x, a.y = deer["x"], deer["y"]
    a.inventory["spear"] = 1
    for _ in range(8):
        if run_step(w, a, {"do": "hunt", "what": "deer"}, limit=400) == actions.DONE:
            break
        deer = next(x for x in w.animals.values() if x["kind"] == "deer")
        a.x, a.y = deer["x"], deer["y"]
    assert a.stats.get("hunted_deer") == 1
    assert a.tool_wear.get("spear") == 1


def test_a_spear_wears_when_it_drives_off_a_wolf_and_breaks_in_the_end(monkeypatch):
    monkeypatch.setattr(AN, "weapon_odds", lambda world, o: 1.0)
    w, (c, other) = village()
    other.x, other.y = c.x + 20, c.y
    c.inventory["spear"] = 1
    _night(w)
    _wolf(w, c)
    AN.attacks(w)
    assert w.animals["w1"].get("fled") is not None and c.tool_wear.get("spear") == 1
    c.tool_wear["spear"] = actions.tool_wear_limit("spear") - 1
    w.animals["w1"].pop("fled")
    w.animals["w1"].update(x=c.x + 1, y=c.y)
    AN.attacks(w)
    assert not c.has("spear") and any(e.kind == "tool_broke" for e in w.events)


def test_a_fight_wears_what_each_fought_with_but_never_an_artifact():
    from chits.sim.artifacts import ARTIFACTS

    assert "musket" in ARTIFACTS
    w, (a, b) = village()
    b.x, b.y = a.x + 1, a.y
    a.inventory["spear"] = 1
    b.inventory["musket"] = 1
    assert run_step(w, a, {"do": "fight", "to": b.name}) == actions.DONE
    assert a.tool_wear.get("spear") == 1
    assert not b.tool_wear.get("musket") and b.has("musket")


def test_a_stronger_weapon_drives_a_wolf_off_more_surely_but_never_surely():
    from chits.sim.invent import register_invention

    w, (a, b) = village()
    a.inventory["spear"] = 1
    assert AN.weapon_odds(w, a) == AN.WEAPON_ODDS["spear"]  # power 1: as it was
    b.inventory["musket"] = 1
    assert AN.WEAPON_ODDS["weapon"] < AN.weapon_odds(w, b) <= AN.DEFENCE_MAX < 1.0
    register_invention(w, "inv_a_1", "Club", {"wood": 1, "stone": 1}, ("invented",), {"tool": "weapon", "tool_power": 1.0})
    a.inventory.clear()
    a.inventory["inv_a_1"] = 1
    assert AN.weapon_odds(w, a) == AN.WEAPON_ODDS["weapon"]
    register_invention(w, "inv_a_2", "Pike", {"wood": 1, "iron": 1}, ("invented",), {"tool": "weapon", "tool_power": 9.0})
    a.inventory["inv_a_2"] = 1
    assert AN.weapon_odds(w, a) == AN.DEFENCE_MAX


def test_a_carried_key_the_world_does_not_know_never_breaks_the_new_code():
    """A chit can carry another world's invention after a restart: nothing here may assume its lookup succeeds."""

    class Holder:
        def best_tool(self, cls):
            return "inv_from_elsewhere"

    w, (a, _) = village()
    assert w.item("inv_from_elsewhere") is None
    assert AN.weapon_odds(w, Holder()) == 0.0  # unarmed, not a crash
    pile = put(w, "stockpile", a)
    a.inventory.update({"inv_from_elsewhere": 1, "stone": 2})
    assert run_step(w, a, {"do": "store", "what": "all"}) == actions.DONE
    assert a.inventory.get("inv_from_elsewhere") == 1 and pile.storage.get("stone") == 2
    assert pile.storage.get("inv_from_elsewhere", 0) == 0


@pytest.mark.parametrize("light", ["lantern", "lightbulb"])
def test_a_light_in_hand_keeps_the_wolf_from_biting_its_holder(light):
    w, (c, other) = village()
    other.x, other.y = c.x, c.y  # standing in the dark beside the light: still bitten
    c.inventory[light] = 1
    c.health = other.health = 100.0
    _night(w)
    _wolf(w, c)
    AN.attacks(w)
    assert c.health == 100.0 and c.stats.get("light_kept_wolf") == 1, "bitten with a light in hand"
    assert other.health < 100.0
    assert w.animals["w1"].get("fled") is None  # kept off, not driven away


def _chill(w, a, item=None) -> float:
    a.inventory.clear()
    if item:
        a.inventory[item] = 1
    a.warmth = 80.0
    w._needs(a, 0.0)  # a freezing night, out in the open, no fire
    return 80.0 - a.warmth


def test_a_lantern_takes_the_edge_off_the_cold_but_is_no_fire():
    w, (a, _) = village()
    w.structures.clear()
    w.occupied.clear()
    w._zone_tick = None
    bare = _chill(w, a)
    assert bare > 0
    lamp = _chill(w, a, "lantern")
    assert lamp > 0, "a lantern in the bag kept all the cold off, like standing by a fire"
    assert lamp == pytest.approx(bare * World.LIGHT_COLD)
    assert _chill(w, a, "cloak") == pytest.approx(bare * 0.5)


# ---------------------------------------------------------------------------------------------- what the models are told
def test_the_prompt_tells_what_the_things_in_hand_do():
    w, (a, _) = village()
    assert P.PROMPT_VERSION >= "2026-10-04.4"
    guide = P.verb_guide(w)
    assert "charcoal" in guide and "cord or brick" in guide
    a.inventory.update({"plough": 1, "sharp_stone": 1, "lantern": 1, "spear": 1})
    sc = P.scene(w, a)
    assert "plough (doubles the grain" in sc and "sharp stone (cuts 2 plant fiber" in sc
    assert "lantern (no wolf bites you" in sc and "drive off a wolf" in sc
    assert "light and warmth" not in sc  # it is not a fire


def test_the_map_is_told_who_carries_a_light():
    from chits import views

    w, (a, _) = village()
    a.inventory.update({"stone_axe": 1, "lantern": 1})
    brief = views.agent_brief(w, a)
    assert brief["tool"] == "stone_axe" and brief["light"] is True  # (the axe is drawn in hand; the lantern still glows)
    a.inventory.pop("lantern")
    assert views.agent_brief(w, a)["light"] is False


def test_a_side_use_is_no_reason_to_make_a_thing_in_bulk():
    """Charcoal feeds a fire and cord mends a stockpile, but a kiln shift still leaves the wood alone until somebody
    knows what charcoal is for (copper or iron): the new uses must not change what the stations make."""
    w, (a, _) = village()
    w.first.clear()
    for k in ("charcoal", "cord", "brick", "sharp_stone"):
        assert not actions._useful(w, k), k
    assert actions._useful(w, "clothes") and actions._useful(w, "plough") and actions._useful(w, "paper")
    w.first["recipe:copper"] = {"tick": 0, "by": a.id, "name": a.name}
    assert actions._useful(w, "charcoal")


def test_switched_off_nothing_claims_or_does_the_new_uses(monkeypatch):
    """Off (the default until A/B'd), the simulator, the prompt and the encyclopedia are as before F35."""
    from chits import views
    from chits.sim import items as IT_

    monkeypatch.setattr(IT_, "ITEM_USES", False)
    w, (a, _) = village()
    fire = put(w, "campfire", a)
    fire.fuel = 10.0
    a.inventory["charcoal"] = 1
    assert run_step(w, a, {"do": "refuel", "target": fire.id}) == "I need wood to feed the fire"
    assert actions.mend_materials("stockpile") == ["wood"]
    a.inventory.clear()
    a.inventory.update({"lantern": 1, "sharp_stone": 1})
    sc = P.scene(w, a)
    assert "lantern (light and warmth at night)" in sc and "cuts 2 plant fiber" not in sc
    guide = P.verb_guide(w)
    assert "charcoal" not in guide and "cord or brick" not in guide and "lifts your spirits" not in guide
    w.first["recipe:charcoal"] = {"tick": 0, "by": a.id, "name": a.name}
    assert not any(e.startswith("Use:") for e in views.encyclopedia(w, "recipe:charcoal")["effects"])


# ---------------------------------------------------------------------------------------------- uses that were already real
@pytest.mark.parametrize("surface", ["clay_tablet", "paper"])
def test_knowledge_is_written_on_a_tablet_or_on_paper(surface):
    w, (a, _) = village()
    assert w.flags.get("write")
    a.learn("recipe:cord", "discovered", w.tick)
    a.inventory[surface] = 1
    assert run_step(w, a, {"do": "write", "what": "cord"}) == actions.DONE
    assert not a.has(surface)
    assert [t.knowledge for t in w.tablets.values()] == ["recipe:cord"]
    assert isinstance(next(iter(w.tablets.values())), Tablet)


def test_seeds_are_planted_in_a_farm():
    w, (a, _) = village()
    farm = put(w, "farm", a)
    farm.planted = False
    a.inventory["seeds"] = 2
    assert run_step(w, a, {"do": "plant", "target": farm.id}) == actions.DONE
    assert farm.planted and not a.has("seeds")


def test_grain_is_eaten():
    w, (a, _) = village()
    a.hunger = 20.0
    a.inventory["grain"] = 1
    assert run_step(w, a, {"do": "eat", "what": "grain"}) == actions.DONE
    assert a.hunger > 20.0 + ITEMS["grain"].food - 2


def test_warm_clothes_halve_the_cold():
    w, (a, _) = village()
    w.structures.clear()
    w.occupied.clear()
    w._zone_tick = None
    assert _chill(w, a, "clothes") == pytest.approx(_chill(w, a) * 0.5)
