"""F34 stage 1: an invention's effect is a number that comes from what it is made of, it keeps its parts'
properties, housekeeping treats it as what it is, and one carried over the sea works where it lands."""

import json

from chits.sim import actions as A, animals as AN, invent as INV
from chits.sim.invent import judge
from chits.sim.items import ITEMS, RECIPES
from chits.sim.world import World


def _world(wid="A", seed=3, n=2, culture="direct"):
    w = World(wid, wid, seed, culture, 64, n)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.inventory.clear()
        o.plan = []
    return w, a


def run(w, a, step, limit=300):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def _invent(w, a, items, name, purpose):
    for k in items:
        a.add(k, 1)
    before = set(w.inventions)
    run(w, a, {"do": "invent", "with": list(items), "name": name, "purpose": purpose})
    new = set(w.inventions) - before
    assert len(new) == 1, a.last_result
    return new.pop()


def _store(w, a, stored):
    pos = w.find_site("stockpile", a.x + 2, a.y, 8)
    s = w.place_site("stockpile", pos[0], pos[1], a)
    w.complete_structure(s, a)
    s.storage.update(stored)
    return s


def test_the_strength_of_an_effect_comes_from_the_materials():
    _, _, flint, _ = judge({"sharp_stone": 1, "wood": 1}, "a hoe to till the field")
    _, _, copper, _ = judge({"copper": 1, "wood": 1}, "a hoe to till the field")
    assert (flint["farming"], copper["farming"]) == (INV.FARMING_GRAIN["hard"], INV.FARMING_GRAIN["metal"]) == (2, 3)
    _, _, club, _ = judge({"sharp_stone": 1, "wood": 1}, "a club to guard us")
    _, _, mace, _ = judge({"copper": 1, "wood": 1}, "a club to guard us")
    assert club["defence"] < mace["defence"] and club["tool_power"] < mace["tool_power"]
    _, _, mat, _ = judge({"fiber": 2}, "a wrap to keep warm")
    _, _, coat, _ = judge({"cloth": 2}, "a coat to keep warm")
    _, _, thick, _ = judge({"cloth": 2, "wool": 1}, "a coat to keep warm")
    assert mat["warmth"] > coat["warmth"] > thick["warmth"]  # (the share of the cold that gets through)
    _, _, clogs, _ = judge({"wood": 2}, "shoes to run fast")
    _, _, rollers, _ = judge({"wheel": 1, "wood": 1}, "shoes to run fast")
    _, _, lead, _ = judge({"ore": 2, "wood": 2}, "a sledge to travel fast")
    assert rollers["speed"] > clogs["speed"] > lead["speed"] > 1.0
    _, _, sack, _ = judge({"fiber": 2}, "a sack to carry things")
    _, _, yoke, _ = judge({"basket": 1, "pot": 1, "cord": 1}, "a yoke to carry things")
    assert yoke["carry_bonus"] > sack["carry_bonus"] == INV.CARRY_BASE and yoke["carry_bonus"] <= INV.CARRY_MAX
    _, _, plain, _ = judge({"stone": 1, "wood": 1}, "a toy")
    _, _, fine, _ = judge({"copper": 1, "glass": 1}, "a jewel")
    assert fine["mood"] > plain["mood"] == 8
    _, _, salve, _ = judge({"fiber": 1, "berries": 1}, "a poultice to heal")
    _, _, rich, _ = judge({"fiber": 1, "berries": 2}, "a poultice to heal")
    assert rich["heal"] > salve["heal"] == INV.HEAL_BASE


def test_the_number_is_what_the_world_applies():
    w, a = _world()
    a.x, a.y = _ripe(w, a)
    hoe = _invent(w, a, ["sharp_stone", "wood"], "Flint Hoe", "a hoe to till the field")
    assert w.invention_effect(a, "farming") == 2 and w.invention_effect(a, "speed") == 0
    best = _invent(w, a, ["copper", "wood"], "Copper Hoe", "a hoe to till the field")
    assert w.invention_effect(a, "farming") == 3  # the best one it carries counts
    a.inventory.pop(best)
    assert _harvest(w, a) == 6 + 2
    a.inventory.pop(hoe)
    a.inventory.pop("grain"), a.inventory.pop("seeds", None)
    assert _harvest(w, a) == 6

    w, a = _world(seed=5)
    slow = A._speed(w, a)
    clogs = _invent(w, a, ["wood", "wood"], "Clogs", "shoes to run fast")
    mid = A._speed(w, a)
    a.inventory.pop(clogs)
    _invent(w, a, ["wheel", "wood"], "Rollers", "shoes to run fast")
    assert A._speed(w, a) > mid > slow

    for parts, share in ((["fiber", "fiber"], 0.7), (["cloth", "cloth"], 0.5), (["cloth", "cloth", "wool"], 0.4)):
        w, a = _world(seed=7)
        _invent(w, a, parts, "Wrap", "a wrap to keep warm")
        assert w.invention_effect(a, "warmth") == share


def _ripe(w, a):
    spot = w.find_site("farm", a.x, a.y)
    st = w.place_site("farm", *spot, a)
    w.complete_structure(st, a)
    st.planted, st.growth = True, 1.0
    w._test_farm = st
    return st.x, st.y


def _harvest(w, a):
    st = w._test_farm
    st.planted, st.growth = True, 1.0
    a.inventory["cart"] = 1
    step = {"do": "harvest", "target": st.id}
    for _ in range(80):
        out = A.advance(w, a, step)
        if out != A.RUNNING:
            assert out == A.DONE, out
            break
        w.tick += 1
    return a.inventory.get("grain", 0)


def test_an_invented_weapon_is_as_good_as_its_material(monkeypatch):
    w, a = _world(seed=9)
    assert AN.weapon_odds(w, a) == AN.WEAPON_ODDS["spear"]  # (asked only of the armed: the fallback)
    club = _invent(w, a, ["wood", "wood", "stone"], "Club", "a club to fight wolves")
    assert w.item(club).tool == "weapon" and AN.weapon_odds(w, a) == INV.DEFENCE_ODDS["hard"] < AN.WEAPON_ODDS["weapon"]
    w.inventions[club]["effect"]["defence"] = 1  # a save from before the number meant anything
    assert AN.weapon_odds(w, a) == AN.WEAPON_ODDS["weapon"]
    a.inventory.clear()
    a.inventory["musket"] = 1
    # a weapon that is not invented goes by its kind, a little better for a stronger one (F35's item uses); with
    # those switched off (the default until they are A/B'd), as any weapon did
    from chits.sim import items as IT
    monkeypatch.setattr(IT, "ITEM_USES", True)
    assert AN.WEAPON_ODDS["weapon"] < AN.weapon_odds(w, a) <= AN.DEFENCE_MAX
    monkeypatch.setattr(IT, "ITEM_USES", False)
    assert AN.weapon_odds(w, a) == AN.WEAPON_ODDS["weapon"]


def test_an_invention_keeps_all_its_parts_properties_so_inventions_compose():
    w, a = _world(seed=11)
    net = _invent(w, a, ["fiber", "fiber", "wood"], "Fishnet", "catch fish")
    props = w.item(net).props
    assert props[:2] == ("invented", "for fishing")
    for p in ITEMS["fiber"].props + ITEMS["wood"].props:
        assert p in props, p
    assert len(props) == len(set(props)) <= 2 + INV.PROPS_KEPT
    # the net is still long and sturdy, so with something hard it makes a digging tool (it kept three properties, all
    # of them the fiber's, and this was refused)
    ok, pid, _, fb = judge({net: 1, "stone": 1}, "to dig", w.catalog)
    assert ok and pid == "digging", fb
    many = INV.invention_props({"copper": 1, "iron": 1, "wire": 1, "alloy": 1}, "joy")
    assert len(many) == 2 + INV.PROPS_KEPT


def test_storing_the_load_keeps_one_working_invention_and_stores_invented_food():
    w, a = _world(seed=13)
    coat = _invent(w, a, ["cloth", "cloth"], "Coat", "a coat to keep warm")
    dish = _invent(w, a, ["berries", "berries", "grain"], "Mash", "a meal")
    a.inventory[coat], a.inventory[dish] = 3, 6
    a.inventory["stone"] = 4
    assert A.is_food(dish, w.catalog) and not A.is_food(coat, w.catalog) and dish in A.foods_of(w)
    assert A.kept_in_hand(w, coat) == 1 and A.kept_in_hand(w, dish) == 2 and A.kept_in_hand(w, "stone") == 0
    st = _store(w, a, {})
    run(w, a, {"do": "store", "what": "all", "target": st.id})
    assert a.inventory == {coat: 1, dish: 2}, (a.inventory, a.last_result)
    assert st.storage == {coat: 2, dish: 4, "stone": 4}
    # food in the store's food share, not its goods share
    st.storage["stone"] = int(A.STOCKPILE_CAP * A.GOODS_SHARE)
    assert A.stockpile_room(st, None, w.catalog) == 0 and A.stockpile_room(st, dish, w.catalog) > 0


def test_a_hungry_chit_eats_an_invented_dish_from_the_store():
    w, a = _world(seed=15)
    dish = _invent(w, a, ["berries", "berries", "grain"], "Mash", "a meal")
    a.inventory.clear()
    st = _store(w, a, {dish: 3})
    a.hunger = 30.0
    run(w, a, {"do": "eat"})
    assert a.hunger > 30 + w.item(dish).food - 10 and st.storage.get(dish, 0) < 3, a.last_result


def test_making_room_for_food_does_not_drop_a_working_invention_first():
    w, a = _world(seed=17)
    coat = _invent(w, a, ["cloth", "cloth"], "Coat", "a coat to keep warm")
    a.inventory[coat] = 2
    a.inventory["charcoal"] = a.free_space()
    assert a.free_space() == 0
    A._drop_for_room(w, a, 3)
    assert a.inventory[coat] == 2 and a.free_space() >= 3
    a.inventory.pop("charcoal")
    a.inventory["stone_axe"] = a.free_space() + 0
    A._drop_for_room(w, a, a.free_space() + 1)
    assert a.inventory[coat] == 1  # a spare one goes with the spare tools, the last one never
    # hands full while gathering, with nowhere to store: the reflex drops a load, not the coat
    a.inventory.clear()
    a.inventory[coat] = 9
    a.inventory["sand"] = a.free_space()
    a.plan = [{"do": "gather", "what": "wood"}]
    A.reflexes(w, a)
    assert a.plan[0].get("do") == "drop" and a.plan[0]["what"] == "sand", a.plan[0]


def test_an_invented_tool_wears_mends_and_smelts_as_what_it_is_made_of():
    w, a = _world(seed=19)
    net = _invent(w, a, ["fiber", "fiber", "wood"], "Fishnet", "catch fish")
    pick = _invent(w, a, ["copper", "wood"], "Copper Mattock", "to dig")
    assert A.tool_wear_limit(net, w) == A.WEAR_PLAIN and A.tool_wear_limit(pick, w) == A.WEAR_METAL
    assert A.metal_of(w, net) is None and A.metal_of(w, pick) == "copper" and A.metal_of(w, "iron_axe") == "iron"
    a.tool_wear[net] = A.WEAR_PLAIN - 1
    A._wear(w, a, net)
    assert not a.inventory.get(net)  # it broke at a stone tool's age, not a metal one's
    for design in ("workshop", "furnace"):
        pos = w.find_site(design, a.x + 3, a.y, 10)
        w.complete_structure(w.place_site(design, pos[0], pos[1], a), a)
    a.tool_wear[pick] = 100
    a.add("wood", 1)
    run(w, a, {"do": "repair", "what": "Copper Mattock"})
    assert a.tool_wear[pick] == 0 and not a.inventory.get("wood"), a.last_result
    run(w, a, {"do": "smelt", "what": "Copper Mattock"})
    assert a.inventory.get("copper") == 1 and not a.inventory.get(pick), a.last_result
    msg = run(w, a, {"do": "smelt", "what": "Fishnet"})
    assert "only metal tools" in msg


def test_an_invention_carried_over_the_sea_works_and_is_known_by_name_there():
    wa, a = _world("A", seed=21)
    wb, b = _world("B", seed=21, culture="stigmergy")
    clogs = _invent(wa, a, ["wood", "wood"], "Clogs", "shoes to run fast")
    wa.depart(a)
    out = wa.outbox.pop()
    there = wb.arrive(out["agent"], "A", "A", out["inventions"])
    # known there as a thing from over the sea (world.foreign), never as one of that world's own inventions
    assert wb.foreign[clogs]["from"] == "A" and clogs not in wb.inventions and "from" not in wa.inventions[clogs]
    assert wb.invention(clogs)["name"] == "Clogs" and "foreign" not in wa.to_dict() and not wa.foreign
    assert clogs not in ITEMS and clogs not in RECIPES
    bare = A._speed(wb, b)
    assert wb.invention_effect(there, "speed") > 1 and A._speed(wb, there) > bare
    assert wb.invention_by_name("clogs") == clogs
    # made again there by its name, and taught: the others know nothing of it until then
    assert not b.knows_recipe(clogs)
    there.x, there.y = b.x, b.y
    there.add("wood", 2)
    run(wb, there, {"do": "craft", "what": "Clogs"})
    assert there.inventory.get(clogs) == 2, there.last_result
    run(wb, there, {"do": "teach", "to": b.name, "what": "Clogs"}, limit=400)
    assert b.knows_recipe(clogs), there.last_result
    # an islander with the same idea makes its own: it never saw the foreign one
    b.inventory.clear()
    own = _invent(wb, b, ["wood", "wood"], "Runners", "shoes to run fast")
    assert own != clogs and own.startswith("inv_b_") and not wb.inventions[own].get("from")
    # it is in the save, and the observer's entry says where it came from and what it does
    w2 = World.from_dict(json.loads(json.dumps(wb.to_dict())))
    assert w2.foreign[clogs]["from"] == "A" and w2.item(clogs).name == "Clogs" and clogs not in w2.inventions
    carrier = next(c for c in w2.agents.values() if c.inventory.get(clogs))
    assert w2.invention_effect(carrier, "speed") > 1  # it still works after a restart
    from chits import views

    e = views.encyclopedia(wb, f"recipe:{clogs}")
    assert e["invention"]["from"] == "A" and any("15% faster" in line for line in e["effects"]), e["effects"]
    assert "from" not in views.encyclopedia(wb, f"recipe:{own}")["invention"]
    assert "walks 15% faster" in "; ".join(INV.effect_words(wb.foreign[clogs]["effect"]))
    # carried onward (or home again), it travels with whoever holds or knows it
    wb.depart(there)
    assert clogs in wb.outbox[-1]["inventions"]
    # and the island it came from never hears of what was made here
    assert wa.item(own) is None


def test_an_old_save_loads_with_the_strengths_it_had():
    w, a = _world(seed=23)
    old = {"inv_a_1": {"key": "inv_a_1", "name": "Old Coat", "inputs": {"fiber": 2}, "purpose": "warmth", "purpose_text": "",
                       "effect": {"warmth": 0.5}, "props": ["invented", "for warmth", "flexible"], "by": a.id,
                       "by_name": a.name, "tick": 0},
           "inv_a_2": {"key": "inv_a_2", "name": "Old Shoe", "inputs": {"wood": 2}, "purpose": "speed", "effect": {"speed": 1.2},
                       "tick": 0},
           "inv_a_3": {"key": "inv_a_3", "name": "Old Drum", "inputs": {"wood": 2}, "purpose": "joy", "effect": {"mood": 8},
                       "tick": 0}}
    d = json.loads(json.dumps(w.to_dict()))
    d["inventions"] = old
    w2 = World.from_dict(d)
    b = next(iter(w2.agents.values()))
    b.inventory.clear()
    for k in old:
        b.inventory[k] = 1
    assert w2.invention_effect(b, "warmth") == 0.5 and w2.invention_effect(b, "speed") == 1.2
    assert INV.MOOD_PER_POINT * w2.invention_effect(b, "mood") == 0.02
    assert w2.invention_carried("inv_a_1") and not w2.invention_carried("stone")
