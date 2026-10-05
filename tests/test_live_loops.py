"""Two failure loops of the 2026-10-05 live game (World A, a model writing plans), both from steps the parser let
through: "None can't be gathered from the land" (gather, 113 tries by day 107) and "some of those aren't real items"
(experiment, 71 by day 97). Only frozen syntax: a step with nothing to act on is rejected, as unreadable ones are, and
inputs written as words are read one fixed way. Nothing is guessed."""

from chits.brain.parse import parse_plan


# ------------------------------------------------------------------ gather/craft/take with nothing to act on
def test_a_gather_step_with_nothing_to_gather_is_rejected_and_the_rest_of_the_plan_kept():
    plan = parse_plan('{"plan":[{"do":"gather"},{"do":"gather","what":"wood","qty":3},{"do":"build","what":"hut"}]}')
    assert [s["do"] for s in plan["steps"]] == ["gather", "build"]
    assert plan["steps"][0]["what"] == "wood"
    assert plan["rejected"] == 1


def test_craft_and_take_with_nothing_named_are_rejected_too():
    for raw in ('{"do":"craft"}', '{"do":"take","from":"s3"}', '{"do":"gather","what":null}', '{"do":"gather","what":""}',
                '{"do":"gather","type":"wood"}', '"gather"'):
        plan = parse_plan('{"plan":[%s,{"do":"explore"}]}' % raw)
        assert [s["do"] for s in plan["steps"]] == ["explore"], raw
        assert plan["rejected"] == 1, raw


def test_the_thing_written_into_the_verb_is_the_steps_object():
    plan = parse_plan('{"plan":[{"do":"gather wood","qty":3},{"do":"gather_berries"},{"action":"fetch clay"}]}')
    assert [(s["do"], s["what"]) for s in plan["steps"]] == [("gather", "wood"), ("gather", "berries"), ("take", "clay")]


# ------------------------------------------------------------------ experiments written as words
def test_an_experiment_written_without_commas_names_real_items_and_its_station():
    plan = parse_plan('{"plan":["experiment with berries iron ore at fire"]}')
    st = plan["steps"][0]
    assert st["with"] == ["berries", "iron ore"] and st["at"] == "fire"


def test_a_station_left_on_the_last_input_and_a_name_it_clause():
    # as the live game logged it: ["glass", " copper ore", " sharp stone furnace", " name it"]
    st = parse_plan('{"plan":["experiment glass, copper ore, sharp stone furnace, name it"]}')["steps"][0]
    assert st["with"] == ["glass", "copper ore", "sharp stone"] and st["at"] == "furnace" and "name" not in st
    st = parse_plan('{"plan":["experiment clay, sand at kiln, called Glaze"]}')["steps"][0]
    assert st["with"] == ["clay", "sand"] and st["at"] == "kiln" and st["name"] == "Glaze"


def test_inputs_given_as_one_string_in_json_are_read_the_same_way():
    st = parse_plan('{"plan":[{"do":"experiment","with":"wood plant fiber fire"}]}')["steps"][0]
    assert st["with"] == ["wood", "plant fiber"] and st["at"] == "fire"


def test_the_models_own_station_stands_and_unknown_inputs_are_left_for_the_simulator():
    st = parse_plan('{"plan":[{"do":"experiment","with":"clay, sand fire","at":"kiln"}]}')["steps"][0]
    assert st["at"] == "kiln" and st["with"] == ["clay", "sand"]
    st = parse_plan('{"plan":[{"do":"experiment","with":"moonbeam dust, wood"}]}')["steps"][0]
    assert st["with"] == ["moonbeam dust", "wood"] and "at" not in st  # (the world says it isn't real)
    st = parse_plan('{"plan":[{"do":"invent","with":["Nura\'s Sack","wood"],"name":"Pack"}]}')["steps"][0]
    assert st["with"] == ["Nura's Sack", "wood"]  # an invention's name isn't split


def test_a_listed_name_ending_in_a_station_is_one_name():
    # (Codex on #113): an invention called "Stone Mill" is one name; the parser can't see this world's inventions
    st = parse_plan('{"plan":[{"do":"invent","with":["Stone Mill","wood"],"name":"Gristwheel"}]}')["steps"][0]
    assert st["with"] == ["Stone Mill", "wood"] and "at" not in st
    st = parse_plan('{"plan":[{"do":"experiment","with":["Stone Mill","clay pot"]}]}')["steps"][0]
    assert st["with"] == ["Stone Mill", "clay pot"] and "at" not in st
    st = parse_plan('{"plan":[{"do":"experiment","with":["clay","at fire"]}]}')["steps"][0]
    assert st["with"] == ["clay"] and st["at"] == "fire"  # (just a station: no invention takes a building's name)
