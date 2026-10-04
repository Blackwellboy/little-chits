"""F34 stage 2: what a combination of parts can be is worked out from what each part can do, and the purpose text
only chooses among those readings. The first engine stays behind invent.COMPOSE = False."""

import pytest

from chits.brain import prompt as P
from chits.sim import invent as INV
from chits.sim.invent import judge, readings, verdict
from chits.sim.items import FUNCTION_OF, FUNCTIONS, ITEMS, Item, described_as, functions, match_recipe
from chits.sim.world import World


@pytest.fixture
def old(monkeypatch):
    monkeypatch.setattr(INV, "COMPOSE", False)


def _world(seed=3):
    w = World("A", "A", seed, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.hunger = a.energy = a.warmth = a.health = 95.0
    a.inventory.clear()
    a.plan = []
    return w, a


def run(w, a, step, limit=300):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def test_the_functional_vocabulary_is_small_and_every_word_of_it_is_given_and_used():
    assert 12 <= len(FUNCTIONS) <= 20 and len(set(FUNCTIONS)) == len(FUNCTIONS)
    given = {f for fs in FUNCTION_OF.values() for f in fs}
    assert given == set(FUNCTIONS)  # nothing in the table outside the vocabulary, nothing in it that no property gives
    by_items = {f for it in ITEMS.values() for f in functions(it)}
    assert by_items == set(FUNCTIONS), set(FUNCTIONS) - by_items  # ...and some real item has each
    used = {f for r in INV.RULES for need in r.needs for f in need} | {r.every for r in INV.RULES if r.every}
    used |= {"metal", "hard", "burns-hot"}  # (read by the strength table: the material tiers, and a brighter light)
    assert used == set(FUNCTIONS), set(FUNCTIONS) ^ used
    assert judge({"charcoal": 1, "pot": 1}, "a lamp")[2]["tool_power"] > judge({"wood": 1, "pot": 1}, "a lamp")[2]["tool_power"]
    assert functions(ITEMS["fiber"]) == {"binds"}
    assert functions(ITEMS["sharp_stone"]) == {"cuts", "pierces", "hard", "rigid"}
    assert {"holds", "holds-liquid", "rigid"} <= functions(ITEMS["pot"])
    assert described_as("binds") == ["stringy", "binding", "flexible"]
    # a pack's item, or anything else with properties, has them too: they are read from the properties
    assert functions(Item("reed", "reed", ("long", "stringy"))) == {"long", "binds"}
    assert functions(None) == frozenset()


def test_the_rule_table_is_of_a_size_to_read_and_every_purpose_has_a_rule():
    assert 20 <= len(INV.RULES) <= 32 and len(INV.RULE) == len(INV.RULES)
    assert {r.purpose for r in INV.RULES} == {p[0] for p in INV.PURPOSES} == set(INV.IN_WORDS)
    for r in INV.RULES:
        assert r.what and (r.needs or r.every or r.purpose == "joy"), r.key
        assert all(need <= set(FUNCTIONS) for need in r.needs), r.key
    # a station rule comes before the plain rule of its purpose (it is the better thing)
    for i, r in enumerate(INV.RULES):
        if r.station:
            assert any(o.purpose == r.purpose and not o.station for o in INV.RULES[i + 1:]), r.key


def test_one_bag_of_parts_can_be_several_things_and_the_purpose_chooses():
    bag = {"fiber": 2, "wood": 1}
    can = readings(bag)
    assert {"fishing", "speed", "carrying", "warmth", "healing", "joy"} <= set(can), sorted(can)
    assert "cutting" not in can and "food" not in can and "light" not in can
    made = {}
    for text in ("a net to catch fish", "sandals to walk quick", "a sack to carry", "a wrap to keep warm"):
        ok, pid, eff, _ = judge(bag, text)
        assert ok, text
        made[pid] = eff
    assert set(made) == {"fishing", "speed", "carrying", "warmth"}
    assert made["fishing"]["tool"] == "spear" and made["carrying"]["carry_bonus"] == 5 and made["speed"]["speed"] > 1


def test_the_purpose_no_longer_gates_by_its_first_keyword(old):
    # the first engine: the first bucket whose keyword is in the text is the only one tried
    assert judge({"fiber": 2, "wood": 1}, "a fishing net, not a weapon")[:2] == (False, "defence")
    assert judge({"cloth": 2}, "a warm cloak to wear when I farm the field")[:2] == (False, "farming")
    assert judge({"wheel": 1, "wood": 2}, "a cart to carry more")[:2] == (True, "speed")
    assert not judge({"wood": 1, "sharp_stone": 1}, "a pointed stick to catch fish")[0]
    INV.COMPOSE = True  # (the fixture puts it back)
    assert judge({"fiber": 2, "wood": 1}, "a fishing net, not a weapon")[:2] == (True, "fishing")
    assert judge({"cloth": 2}, "a warm cloak to wear when I farm the field")[:2] == (True, "warmth")
    assert judge({"wheel": 1, "wood": 2}, "a cart to carry more")[:2] == (True, "carrying")
    assert judge({"wheel": 1, "wood": 2}, "a cart to travel fast")[:2] == (True, "speed")
    assert judge({"wood": 1, "sharp_stone": 1}, "a pointed stick to catch fish")[:2] == (True, "fishing")


def test_what_the_parts_cannot_do_is_refused_with_what_they_could_do():
    ok, pid, eff, fb = judge({"wood": 1, "stone": 1}, "something to heat the hut")
    assert not ok and pid == "warmth" and eff == {}
    assert "could make something for" in fb and "digging" in fb and "light" in fb
    ok, pid, _, fb = judge({"wood": 1, "sharp_stone": 1}, "a blanket to keep warm")
    assert not ok and pid == "warmth" and "catching fish" in fb and "cutting" in fb
    for word in ("spear", "stone axe", "stone pick", "->", "recipe"):  # what they could do, never what the base recipe is
        assert word not in fb, word
    # the nearest miss says what was missing, in the properties a chit can see
    ok, pid, _, fb = judge({"berries": 2}, "a net to catch fish")
    assert not ok and pid == "fishing" and "stringy or binding or flexible" in fb and "food" in fb
    # nothing understood: the purposes the world knows, and still what these parts could be
    ok, pid, _, fb = judge({"wood": 2}, "fly to the moon")
    assert not ok and pid is None and "catching fish" in fb and "could make something for speed" in fb
    # the first engine accepted these: one soft or edible part was enough for any wrap or remedy
    for bag, text in (({"berries": 1, "wood": 1}, "a blanket to keep warm"), ({"fish": 1, "wood": 1}, "a remedy to cure the sick"),
                      ({"fiber": 1, "stone": 1}, "a bag to carry things")):
        assert not judge(bag, text)[0], text


def test_each_need_is_met_by_a_different_piece():
    assert not judge({"wood": 1, "berries": 1}, "a torch for light")[0]  # one stick cannot be the flame and the handle
    assert judge({"wood": 2}, "a torch for light")[0]
    assert not judge({"fiber": 1, "stone": 1}, "a sack to carry")[0] and judge({"fiber": 2}, "a sack to carry")[0]


def test_a_tools_strength_comes_from_its_head(old):
    bag = {"sharp_stone": 1, "copper": 1, "wood": 1}
    assert judge(bag, "a knife to cut")[2]["tool_power"] == round(1.5 * INV.TOOL_TIER["metal"], 2)  # any metal in it counted
    INV.COMPOSE = True
    # the flint is the edge and the copper a weight on the handle: it cuts as flint does
    assert judge(bag, "a knife to cut")[2]["tool_power"] == round(INV.BLADE_POWER * INV.TOOL_TIER["hard"], 2)
    assert judge(bag, "a hoe to till")[2]["farming"] == INV.FARMING_GRAIN["metal"]  # (as a hoe the copper is the head)
    assert judge({"iron": 1, "wood": 1}, "an axe to chop")[2]["tool_power"] == round(INV.BLADE_POWER * INV.TOOL_TIER["metal"], 2)


def test_a_station_makes_more_of_the_same_parts():
    ok, pid, _, fb = judge({"copper": 1, "wood": 1}, "a blade to cut")
    assert not ok and pid == "cutting" and "workshop" in fb  # unworked copper has no edge; the bench would give it one
    ok, pid, eff, _ = judge({"copper": 1, "wood": 1}, "a blade to cut", None, "workshop")
    assert ok and eff["tool"] == "axe" and 2.4 < eff["tool_power"] < ITEMS["copper_axe"].tool_power
    v = verdict({"copper": 1, "wood": 1}, "a blade to cut", None, ("workshop", "fire"))
    assert v["rule"] == "forged_blade" and v["station"] == "workshop"
    assert verdict({"sharp_stone": 1, "wood": 1}, "a blade to cut", None, ("workshop",))["station"] is None
    plain = judge({"berries": 2, "grain": 1}, "a meal")[2]["food"]
    cooked = judge({"berries": 2, "grain": 1}, "a meal", None, "fire")[2]["food"]
    assert cooked > plain == 55
    assert judge({"berries": 1, "pot": 1}, "a tonic to heal", None, "fire")[2]["heal"] == INV.TONIC_HEAL


@pytest.mark.parametrize("compose", [True, False])
def test_every_case_the_plan_pins_holds_in_both_engines(monkeypatch, compose):
    monkeypatch.setattr(INV, "COMPOSE", compose)
    ok, pid, eff, _ = judge({"fiber": 2, "wood": 1}, "catch fish")
    assert ok and pid == "fishing" and eff["tool"] == "spear"
    ok, pid, eff, fb = judge({"berries": 2}, "catch fish")
    assert not ok and pid == "fishing" and any(p in fb for p in ("stringy", "binding", "flexible"))
    ok, pid, eff, _ = judge({"stone": 1, "wood": 1}, "make music")
    assert ok and pid == "joy" and eff["mood"] == 8
    ok, pid, eff, _ = judge({"berries": 2, "grain": 1}, "a tasty meal")
    assert ok and pid == "food" and eff["food"] == 55
    ok, pid, eff, fb = judge({"wood": 1, "berries": 1}, "food for winter")
    assert not ok and "edible" in fb
    ok, pid, eff, fb = judge({"wood": 2}, "fly to the moon")
    assert not ok and pid is None
    for word in ("catching fish", "cutting", "digging", "carrying", "keeping warm", "light", "food", "joy"):
        assert word in fb
    ok, _, _, fb = judge({"wood": 1}, "make music")
    assert not ok and "2" in fb and "4" in fb
    assert judge({"copper": 1, "wood": 1}, "a hoe to till the field")[2]["farming"] == 3
    assert judge({"wood": 2}, "a shoe to run fast")[:2] == (True, "speed")
    assert match_recipe({"fiber": 2, "wood": 1}, None) is None  # (invention never touches the base recipes)


def test_the_world_records_which_rule_made_an_invention_and_second_generation_inventions_work():
    w, a = _world(seed=5)
    for k, n in (("fiber", 2), ("wood", 1), ("sharp_stone", 1)):
        a.add(k, n)
    run(w, a, {"do": "invent", "with": ["fiber", "fiber", "wood"], "name": "Fishnet", "purpose": "a net to catch fish"})
    net = next(iter(w.inventions))
    assert w.inventions[net]["rule"] == "net" and w.inventions[net]["purpose"] == "fishing"
    # the net is still long and it binds: with a flint it makes a weapon on a shaft, and that is an invention too
    run(w, a, {"do": "invent", "with": ["Fishnet", "sharp stone"], "name": "Net Flail", "purpose": "a weapon to fight wolves"})
    assert len(w.inventions) == 2, a.last_result
    flail = [k for k in w.inventions if k != net][0]
    assert w.inventions[flail]["rule"] == "club" and w.item(flail).tool == "weapon" and w.inventions[flail]["inputs"] == {net: 1, "sharp_stone": 1}
    assert {"long", "binds", "cuts"} <= functions(w.item(flail))
    # a refusal costs nothing and the chit remembers what the parts could be
    a.add("stone", 1)
    a.add("wood", 1)
    msg = run(w, a, {"do": "invent", "with": ["stone", "wood"], "name": "Hut Heater", "purpose": "something to heat the hut"})
    assert "could make something for" in msg and a.inventory.get("stone") == 1 and len(w.inventions) == 2
    assert any("could make something for" in m.text for m in a.memories)


def test_the_guide_tells_the_truth_about_the_new_engine():
    w, a = _world()
    guide = P.verb_guide(w)
    line = next(l for l in guide.splitlines() if '"do":"invent"' in l)
    for phrase in ("What the parts can do decides", "Your purpose chooses", "what they could make", "Better material"):
        assert phrase in line, phrase
    assert "the world decides if their properties suit the purpose" not in line  # (the first engine's story)
    compact = P.compact_system_prompt(w, a)
    assert "INVENT" in compact and "what its parts can do" in compact
    assert P.PROMPT_VERSION >= "2026-10-04.5"
