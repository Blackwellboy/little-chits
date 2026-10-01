"""Fixes from the 2026-09-28 audit of live games: discovery blockers, reflex loops, clay on big maps."""

import json

from chits.brain.parse import parse_plan
from chits.sim import actions, terrain as T
from chits.sim.world import World


def chit(size=64, seed=1):
    w = World("A", "A", seed, "direct", size, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    return w, a


def test_picking_up_seeds_gives_the_farm_idea():
    """Agent.add records the item, so notice_items never saw a change and never checked for ideas."""
    w, a = chit()
    a.knows.pop("design:farm", None)
    a.add("seeds", 2)
    w.notice_items(a)
    assert a.knows_design("farm")


def test_experiments_accept_doubles_in_every_shape():
    for with_ in (["stone", "stone"], [{"item": "stone", "qty": 2}], ["2 stone"]):
        plan = parse_plan(json.dumps({"thought": "t", "goal": "g", "plan": [{"do": "experiment", "with": with_}]}))
        assert actions._experiment_bag(plan["steps"][0]) == ["stone", "stone"], with_


def test_a_full_handed_experiment_makes_exactly_the_recipe_amount():
    w, a = chit()
    a.inventory.update({"stone": 2, "wood": 10})  # 12/12: hands full
    s = {}
    for _ in range(40):
        res = actions._do_experiment(w, a, {"do": "experiment", "with": ["stone", "stone"]}, s)
        if res != actions.RUNNING:
            break
    assert a.inventory.get("sharp_stone") == 1 and a.inventory.get("stone", 0) == 0, (res, a.inventory)


def test_making_a_known_recipe_proves_it():
    w, a = chit()
    a.learn("recipe:sharp_stone", "taught", w.tick)
    a.inventory["stone"] = 2
    s = {}
    for _ in range(40):
        if actions._do_experiment(w, a, {"do": "experiment", "with": ["stone", "stone"]}, s) != actions.RUNNING:
            break
    assert a.knows["recipe:sharp_stone"]["status"] == "worked"


def test_an_invention_cannot_take_a_base_items_name():
    w, a = chit()
    a.inventory.update({"fiber": 1, "wood": 1})
    msg = actions._do_invent(w, a, {"do": "invent", "with": ["fiber", "wood"], "name": "Wood", "purpose": "catch fish"}, {})
    assert "already taken" in msg and w.norm_item("wood") == "wood"


def test_a_shelter_reflex_with_nowhere_to_go_lets_the_chits_plan_run():
    w, a = chit()
    w.weather = "storm"
    a.plan = [{"do": "gather", "what": "wood", "qty": 3}]
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "shelter"
    actions.run(w, a)  # nowhere to shelter: fails
    assert a.plan[0]["do"] == "gather"
    actions.reflexes(w, a)  # ...and doesn't fire again straight away
    assert a.plan[0]["do"] == "gather"
    w.tick += actions.REFLEX_REST + 1
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "shelter"


def test_big_new_islands_get_more_rivers_and_clay_and_old_saves_keep_their_map():
    assert T.river_count(128, 128) == 3 and T.river_count(512, 512) > 3 and T.river_count(512, 512, version=1) == 3
    clay = lambda gen: sum(1 for k in gen[1] if k == T.R_CLAY)
    assert clay(T.generate(22, 512, 512)) > 2 * clay(T.generate(22, 512, 512, version=1))
    assert T.generate(5, 128, 128, version=1) == T.generate(5, 128, 128)  # small maps unchanged
    old = T.generate(5, 256, 256, version=1)
    w = World("A", "A", 5, "direct", 256, 2)
    d = w.to_dict()
    d.pop("terrain_version")  # a save from before versioning
    assert bytes(World.from_dict(d).tiles) == bytes(old[0])


def test_a_chit_spoken_to_is_reminded_until_it_answers():
    from chits.brain import prompt as P

    w = World("A", "A", 3, "direct", 64, 3)
    a, b, _ = list(w.agents.values())
    b.x, b.y = a.x, a.y
    s = {"ticks": 0}
    actions._do_say(w, a, {"do": "say", "to": b.name, "text": "Shall we build a fire?"}, s)
    b.last_result = "Gathered 6 berries"  # the next finished step used to wipe the message
    assert f"{a.name} spoke to you" in P.scene(w, b) and "Shall we build a fire?" in P.scene(w, b)
    actions._do_say(w, b, {"do": "say", "to": a.name, "text": "Yes!"}, {"ticks": 0, "close": True})
    assert b.spoken_to == {} and f"{a.name} spoke to you" not in P.scene(w, b)


def test_a_cut_off_reflection_makes_no_law_ambition_or_faith():
    from chits.brain.mind import apply_reflection

    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    w.leader = a.id
    cut = ('{"lessons":[{"text":"Keep the fire fed at night","from":[]}],"ambition":"Build a great hall",'
           '"decree":"Every skill learned must')
    apply_reflection(w, a, cut)
    assert w.laws == [] and a.ambition == ""
    apply_reflection(w, a, cut + ' be taught to two others"}')
    assert len(w.laws) == 1 and a.ambition == "Build a great hall"


def test_the_same_faith_in_other_words_is_joined_not_copied():
    w = World("A", "A", 3, "direct", 64, 3)
    a, b, _ = list(w.agents.values())
    w.found_belief(a, "The Warmth of Shared Flame", "A fire kept alive together is our home and our strength")
    assert w.found_belief(b, "The Warmth of Shared Fire", "Our home and our strength is a fire kept together") is None
    assert len(w.beliefs) == 1 and b.belief == a.belief


def test_approval_voting_can_elect_a_chief_in_a_big_village():
    w = World("A", "A", 3, "direct", 64, 20)
    ags = list(w.agents.values())
    for i, a in enumerate(ags):
        a.born, a.affinity = -240 * (10 + i), {}
    # four neighbourhoods each like their own two locals; everyone also likes the healer
    healer = ags[0]
    for i, v in enumerate(ags[1:], 1):
        v.affinity[healer.id] = 12.0
        v.affinity[ags[1 + (i % 4)].id] = 30.0
    w.choose_leader("test")
    assert w.leader == healer.id


def test_repeated_lessons_are_kept_once():
    from chits.brain.mind import apply_reflection

    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    apply_reflection(w, a, json.dumps({"lessons": ["Drop stone and wood when carrying food home"]}))
    apply_reflection(w, a, json.dumps({"lessons": ["Carrying food home matters more: drop wood and stone"]}))
    assert len(a.lessons) == 1 and a.lessons[0].startswith("Carrying food")


def test_replies_to_an_old_match_are_not_recorded_in_the_new_one():
    from chits.brain.mind import Mind

    m = Mind()
    seen = []
    m.on_decision = seen.append
    old = {"match": m.match, "outcome": "pending"}
    m.new_match()
    m._resolve(old, "adopted", 5)
    m._resolve({"match": m.match, "outcome": "pending"}, "adopted", 6)
    assert [r["tick_resolved"] for r in seen] == [6]


def test_a_chit_can_see_a_neighbours_food_to_offer_a_trade():
    from chits.brain import prompt as P

    w = World("A", "A", 3, "direct", 64, 3)
    a, b, _ = list(w.agents.values())
    b.x, b.y = a.x + 1, a.y
    b.inventory.clear()
    b.inventory.update({"berries": 4, "wood": 6, "stone": 1})
    line = next(l for l in P.scene(w, a).splitlines() if l.startswith("- Chits:"))
    assert "6 wood" in line and "4 berries" in line and "1 stone" not in line
