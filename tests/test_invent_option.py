"""F34 stage 4: a chit that chooses with one token is offered one invention it could make now. A chit without a model
never is."""

import json

from chits.brain import inventor as IV, prompt as P
from chits.brain.instinct import Instinct
from chits.sim import invent as INV
from chits.sim.world import World


def _world(seed=3, brain="brainA"):
    w = World("A", "A", seed, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = o.health = o.mood = 95.0
        o.inventory.clear()
        o.plan = []
        o.brain = brain
    w.tick = 240 * 2 + 120  # midday
    return w, a


def _invents(opts):
    return [o for o in opts if any(s.get("do") == "invent" for s in o["steps"])]


def run(w, a, plan, limit=300):
    a.plan = [dict(s) for s in plan["steps"]]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_a_choosing_chit_is_offered_one_invention_it_can_really_make():
    w, a = _world()
    a.inventory.update({"fiber": 2, "wood": 1})
    opts = Instinct().options(w, a)
    inv = _invents(opts)
    assert len(inv) == 1, [o["goal"] for o in opts]
    step = inv[0]["steps"][0]
    # (the fewest pieces that make it: one fiber on a stick is a line on a frame)
    assert step == {"do": "invent", "with": ["fiber", "wood"], "name": "Plant Fiber Net", "purpose": "to catch fish"}
    assert "a net or a line on a frame" in inv[0]["goal"] and "works as a spear" in inv[0]["goal"]
    # the model sees it as one line it can pick with a letter
    text = P.choice_messages(w, a, opts)[1]["content"]
    assert "invent a Plant Fiber Net" in text and "invent fiber + wood to catch fish" in text
    # and picking it works: the simulator judges the same table the option was drafted from
    run(w, a, inv[0])
    assert len(w.inventions) == 1 and a.best_tool("spear"), a.last_result
    key = next(iter(w.inventions))
    assert w.inventions[key]["name"] == "Plant Fiber Net" and w.inventions[key]["rule"] == "net"


def test_a_chit_without_a_model_is_never_offered_one_and_nothing_random_is_drawn():
    w, a = _world(brain="instinct")
    a.inventory.update({"fiber": 2, "wood": 1})
    assert IV.option(w, a) is None and not _invents(Instinct().options(w, a))
    a.brain = "brainA"
    before = json.dumps(w.to_dict(), sort_keys=True, default=str)
    assert IV.option(w, a) is not None
    assert json.dumps(w.to_dict(), sort_keys=True, default=str) == before  # drafting it changes nothing in the world
    child = a
    child.born = w.tick  # a child plays; it does not invent
    assert IV.option(w, child) is None


def test_the_option_answers_what_the_chit_lacks_and_is_not_offered_for_what_it_has():
    w, a = _world(seed=5)
    assert IV.option(w, a) is None  # empty hands
    a.inventory.update({"fiber": 2, "wood": 1, "spear": 1})
    opt = IV.option(w, a)  # it has a spear: the same parts are offered as what it still lacks
    assert opt and opt["steps"][0]["purpose"] != "to catch fish", opt
    assert "fishing" not in IV.wanted(w, a) and "digging" in IV.wanted(w, a)
    a.inventory.clear()
    a.inventory.update({"stone": 1, "wood": 1})
    assert IV.option(w, a)["steps"][0]["purpose"] == "to dig stone and ore"
    a.inventory.clear()
    a.inventory.update({"berries": 3})  # food is found by cooking, not offered as an invention; nothing else fits
    assert IV.option(w, a) is None
    # tools, containers and an invention that is working for the chit are never offered as parts
    a.inventory.clear()
    a.inventory.update({"stone_axe": 2, "basket": 2})
    assert IV.parts(w, a) == {} and IV.option(w, a) is None


def test_an_invention_it_already_knows_is_not_offered_again_and_a_taken_name_is_avoided():
    w, a = _world(seed=7)
    a.inventory.update({"fiber": 2, "wood": 1})
    run(w, a, IV.option(w, a))
    assert len(w.inventions) == 1
    a.inventory.pop(next(iter(w.inventions)))  # it lost the net, and has the parts again
    a.inventory.update({"fiber": 2, "wood": 1})
    opt = IV.option(w, a)
    assert opt is None or opt["steps"][0]["purpose"] != "to catch fish"  # it knows that one: it can craft it
    # another chit, who does not know it, with the same parts: offered under a name that is still free, and making it
    # gives the village's net (the same idea), not a second invention
    b = [o for o in w.agents.values() if o is not a][0]
    b.inventory.update({"fiber": 2, "wood": 1})
    opt = IV.option(w, b)
    assert opt["steps"][0]["name"] == f"{b.name}'s Net"
    run(w, b, opt)
    assert len(w.inventions) == 1 and b.best_tool("spear"), b.last_result


def test_every_purpose_text_and_rule_noun_is_one_the_judge_understands():
    assert set(IV.PURPOSE_TEXT) == {p[0] for p in INV.PURPOSES} - {"food"}
    for pid, text in IV.PURPOSE_TEXT.items():
        assert INV._named(text)[0] == pid, text
    assert set(IV.NOUN) == set(INV.RULE)
