"""The item pipeline: everything that can be made or found has a use, and a way to get it."""

from chits.sim.items import ACTION_USES, DESIGNS, ITEMS, RECIPES
from chits.sim.actions import GATHER_RULES
from chits.sim.artifacts import ARTIFACTS  # registers them in ITEMS, whatever order the tests run in

# Artifacts only arrive by god mode, and what they do is found on pickup and inspection (artifacts.on_pickup /
# on_inspect), so the made-or-found pipeline below is about everything else.
PIPELINE = [k for k in ITEMS if k not in ARTIFACTS]


def uses_of(k):
    it = ITEMS[k]
    uses = [f"recipe {r.key}" for r in RECIPES.values() if any(i == k for i, _ in r.inputs)]
    uses += [f"build {d.key}" for d in DESIGNS.values() if any(m == k for m, _ in d.materials)]
    uses += [f"idea for {d.key}" for d in DESIGNS.values() if ("item", k) in d.prereqs]
    if it.food:
        uses.append("food")
    if it.tool:
        uses.append(f"tool {it.tool}")
    if it.carry_bonus:
        uses.append("carrying")
    if "wearable" in it.props:
        uses.append("wearable")
    if k in ACTION_USES:
        uses.append(ACTION_USES[k])
    return uses


def test_every_item_has_a_use():
    dead = [k for k in PIPELINE if not uses_of(k)]
    assert not dead, f"items nobody can do anything with: {dead}"


# ------------------------------------------------------------------------------------------------ F35: a runtime read
# "Goes into a recipe" is not a use: 21 items passed the test above and did nothing at all in the simulator. An item
# must be read by code that runs: it feeds, it is a tool of a class the simulator asks for, it carries, it is worn, or
# an action uses it (ACTION_USES, each entry proved by the test named in PROOF). What is left is listed here, each
# with the one thing it exists for: pure intermediates and raw stuff a station turns into something else.
INTERMEDIATES = {
    "sand": "raw: fired into brick at a kiln and melted into glass at a furnace",
    "ore": "raw: smelted into copper at a furnace",
    "iron_ore": "raw: smelted into iron at a furnace",
    "copper": "metal: copper tools, the lantern, wire; monuments, bell towers and lighthouses are built with it",
    "iron": "metal: iron tools, the plough, wheels, steel; forges and aqueducts are built with it",
    "steel": "metal: gears and engines; factories and the machine-age buildings are built with it",
    "alloy": "metal: rocket sections",
    "glass": "windows of the two-storey house and the lighthouse's lamp; the lantern and the light bulb",
    "wheel": "part: the cart and the wagon roll on them",
    "gear": "part: the steam engine and the printing press",
    "engine": "part: the factory, the steam pump, the sawmill, the dynamo and rocket sections",
    "wire": "part: magnets, dynamos, light bulbs, the power station and street lamps",
    "magnet": "part: the dynamo",
    "dynamo": "part: the power station and the launch pad",
    "fuel": "the launch pad burns it",
    "rocket_part": "the launch pad is built of them",
    "flour": "ground at a mill to be baked into loaves",
    "wool": "shorn from tame sheep to be woven into cloth",
    "cloth": "woven to be sewn into a cloak",
}

# the test that proves each action use by running the code that does it
PROOF = {
    "clay_tablet": "test_item_verbs.py::test_knowledge_is_written_on_a_tablet_or_on_paper",
    "paper": "test_item_verbs.py::test_knowledge_is_written_on_a_tablet_or_on_paper",
    "seeds": "test_item_verbs.py::test_seeds_are_planted_in_a_farm",
    "ale": "test_town_life.py::test_an_evening_at_the_tavern_cheers_more_with_ale_and_uses_it_up",
    "clothes": "test_item_verbs.py::test_warm_clothes_halve_the_cold",
    "grain": "test_item_verbs.py::test_grain_is_eaten",
    "plough": "test_plough.py::test_plough_is_an_iron_workshop_tool_and_doubles_base_harvest",
    "wood": "test_item_verbs.py::test_charcoal_feeds_a_fire_and_burns_longer_than_wood",
    "charcoal": "test_item_verbs.py::test_charcoal_feeds_a_fire_and_burns_longer_than_wood",
    "stone": "test_item_verbs.py::test_a_building_is_mended_with_the_plain_stuff_it_is_built_of",
    "fiber": "test_item_verbs.py::test_a_building_is_mended_with_the_plain_stuff_it_is_built_of",
    "clay": "test_item_verbs.py::test_a_building_is_mended_with_the_plain_stuff_it_is_built_of",
    "cord": "test_item_verbs.py::test_a_building_is_mended_with_the_plain_stuff_it_is_built_of",
    "brick": "test_item_verbs.py::test_a_building_is_mended_with_the_plain_stuff_it_is_built_of",
    "sharp_stone": "test_item_verbs.py::test_a_sharp_stone_in_hand_cuts_fiber_two_at_a_stroke",
}
MAX_INTERMEDIATES = 19  # the allow-list may shrink, never grow: a new item needs a verb


def direct_uses(k):
    it = ITEMS[k]
    uses = []
    if it.food:
        uses.append("food")
    if it.tool:
        uses.append(f"tool {it.tool}")
    if it.carry_bonus:
        uses.append("carrying")
    if "wearable" in it.props:
        uses.append("wearable")
    if k in ACTION_USES:
        uses.append(ACTION_USES[k])
    return uses


def _sim_source():
    import pathlib

    import chits

    root = pathlib.Path(chits.__file__).parent
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((root / "sim").glob("*.py")))


def test_every_item_is_used_by_code_or_is_a_listed_intermediate():
    idle = [k for k in PIPELINE if not direct_uses(k) and k not in INTERMEDIATES]
    assert not idle, f"items that only ever go into something else, and are not listed as intermediates: {idle}"
    assert len(INTERMEDIATES) <= MAX_INTERMEDIATES
    for k, why in INTERMEDIATES.items():
        assert k in PIPELINE and why.strip(), k
        assert not direct_uses(k), f"{k} has a use of its own ({direct_uses(k)}): take it off the allow-list"
        goes_into = [u for u in uses_of(k) if u.startswith(("recipe ", "build "))]
        assert goes_into, f"{k} is listed as an intermediate but nothing is made or built from it"


def test_every_tool_class_is_one_the_simulator_asks_for():
    src = _sim_source()
    for k in PIPELINE:
        cls = ITEMS[k].tool
        if cls:
            gathers = any(rule["tool"] == cls for rule in GATHER_RULES.values())
            assert gathers or f'best_tool("{cls}")' in src, f"{k}: nothing in the simulator asks for a {cls}"


def test_every_wearable_is_warm_which_is_what_the_cold_reads():
    for k in PIPELINE:
        if "wearable" in ITEMS[k].props:
            assert "warm" in ITEMS[k].props, k  # (World._needs halves the cold for a wearable, warm thing)


def test_every_action_use_names_the_test_that_proves_it():
    import importlib

    assert set(PROOF) == set(ACTION_USES), set(PROOF) ^ set(ACTION_USES)
    for k, ref in PROOF.items():
        assert k in ITEMS, k
        mod, _, fn = ref.partition("::")
        assert callable(getattr(importlib.import_module(mod[:-3]), fn, None)), f"{k}: no test {ref}"


def test_mending_and_fuel_tables_are_the_ones_the_uses_name():
    from chits.sim.actions import mend_materials
    from chits.sim.items import FUEL_VALUE, MEND_WITH, SIDE_USES

    mended_with = {m for d in DESIGNS for m in mend_materials(d)}
    for k in MEND_WITH:
        assert k in mended_with and k in ACTION_USES and "mend" in ACTION_USES[k], k
    for k in FUEL_VALUE:
        assert k in ACTION_USES and "campfire" in ACTION_USES[k], k
    assert set(SIDE_USES) <= set(ACTION_USES)


def test_every_item_can_be_obtained():
    made = {r.key for r in RECIPES.values()}
    obtainable = set(GATHER_RULES) | made | {"meat", "wool", "grain"}  # hunting, tame sheep, harvesting farms
    missing = [k for k in PIPELINE if k not in obtainable]
    assert not missing, f"items with no way to get them: {missing}"


def test_every_recipe_input_and_station_exists():
    for r in RECIPES.values():
        for k, _ in r.inputs:
            assert k in ITEMS, (r.key, k)
        if r.station:
            assert any(d.station == r.station for d in DESIGNS.values()) or r.station == "fire", (r.key, r.station)
