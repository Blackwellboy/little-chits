"""Issue #5: worn metal tools can be mended (a new haft at a workshop) and metal tools smelted back into their metal,
so iron goes into steel rather than into replacing picks; instinct and model prompts know how."""

from chits.brain import instinct as I
from chits.brain import prompt as P
from chits.sim import actions
from chits.sim.world import World

from test_machine_age import build


def setup(*designs):
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = a.energy = a.warmth = 100
    home = (a.x, a.y)
    for d in designs:
        build(w, a, d, home)
    return w, a


def run(w, a, step, ticks=120):
    a.plan = [step]
    for _ in range(ticks):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    return a.last_result


def test_metal_tools_and_their_metal_come_from_the_recipes():
    assert actions.METAL_OF == {"copper_axe": "copper", "copper_pick": "copper", "iron_axe": "iron", "iron_pick": "iron",
                                "plough": "iron"}  # (the plough has no tool class, but wears out: Codex, #18)


def test_a_worn_metal_tool_is_mended_at_a_workshop_with_one_wood():
    w, a = setup("workshop")
    a.inventory.update({"iron_pick": 1, "wood": 2})
    a.tool_wear["iron_pick"] = 100
    run(w, a, {"do": "repair", "what": "iron pick"})
    assert a.tool_wear["iron_pick"] == 0 and a.inventory["wood"] == 1 and a.has("iron_pick")


def test_mending_needs_wood_a_workshop_and_wear():
    w, a = setup("workshop")
    a.inventory.update({"iron_pick": 1})
    a.tool_wear["iron_pick"] = 100
    assert "wood" in run(w, a, {"do": "repair", "what": "iron pick"})
    a.inventory["wood"] = 1
    a.tool_wear["iron_pick"] = 0
    assert "doesn't need mending" in run(w, a, {"do": "repair", "what": "iron pick"})
    w2, b = setup()
    b.inventory.update({"iron_pick": 1, "wood": 1})
    b.tool_wear["iron_pick"] = 100
    assert "no workshop" in run(w2, b, {"do": "repair", "what": "iron pick"})


def test_a_metal_tool_smelts_back_into_its_metal_at_a_furnace():
    w, a = setup("furnace")
    a.inventory.update({"copper_pick": 1})
    a.tool_wear["copper_pick"] = 30
    run(w, a, {"do": "smelt", "what": "copper pick"})
    assert not a.has("copper_pick") and a.inventory.get("copper") == 1 and "copper_pick" not in a.tool_wear
    a.inventory.update({"stone_pick": 1})
    assert "only metal tools" in run(w, a, {"do": "melt", "what": "stone pick"})  # (an alias of smelt)


def test_instinct_mends_a_half_worn_tool_and_smelts_one_it_has_outgrown():
    w, a = setup("workshop", "furnace")
    a.inventory.update({"iron_pick": 1, "wood": 1})
    a.tool_wear["iron_pick"] = actions.tool_wear_limit("iron_pick") // 2
    p = I.tool_care_plan(w, a)
    assert p and p["steps"][-1] == {"do": "repair", "what": "iron_pick"}
    a.tool_wear["iron_pick"] = 0
    assert I.tool_care_plan(w, a) is None  # (nothing to do)
    a.inventory["copper_pick"] = 1
    p = I.tool_care_plan(w, a)
    assert p and p["steps"] == [{"do": "smelt", "what": "copper_pick"}]


def test_a_models_scene_says_which_tool_is_worn():
    w, a = setup()
    a.inventory.update({"iron_pick": 1, "copper_axe": 1})
    a.tool_wear["iron_pick"] = 100
    scene = P.scene(w, a)
    assert "iron pick (worn)" in scene and "copper axe (worn)" not in scene
    assert '"do":"smelt"' in P.system_prompt(w, a)


def test_a_worn_plough_is_mended_like_any_metal_tool():
    # it has no tool class, so a worn plough was never mended and broke, taking its iron with it (Codex, #18)
    w, a = setup("workshop")
    a.inventory.update({"plough": 1, "wood": 1})
    a.tool_wear["plough"] = actions.tool_wear_limit("plough") // 2
    plan = I.tool_care_plan(w, a)
    assert plan and plan["steps"][-1] == {"do": "repair", "what": "plough"}


def test_a_replaced_tool_is_smelted_not_mended_first():
    # a worn copper pick beside an iron one was given a new haft, and then melted down (Codex, #18)
    w, a = setup("workshop", "furnace")
    a.inventory.update({"copper_pick": 1, "iron_pick": 1, "wood": 1})
    a.tool_wear["copper_pick"] = actions.tool_wear_limit("copper_pick") // 2
    plan = I.tool_care_plan(w, a)
    assert plan and plan["steps"] == [{"do": "smelt", "what": "copper_pick"}]
