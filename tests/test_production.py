"""Production at stations: a chit works a shift at a kiln, furnace, workshop or fire, fetching a bill's inputs from the
stores around it and putting the goods back. Stations used to be only places for experiments, and stores piled up."""

import json
import random

import pytest

from chits import views
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import actions as ACT
from chits.sim import terrain as T
from chits.sim.world import Structure, World


def _world(seed=5):
    w = World("A", "A", seed, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.plan = []
    a.inventory.clear()
    return w, a


def _build(w, a, design, dx, dy=0, storage=None, radius=6):
    xy = w.find_site(design, a.x + dx, a.y + dy, radius, reach=(a.x, a.y))
    st = w.place_site(design, xy[0], xy[1], a)
    w.complete_structure(st, a)
    st.storage.update(storage or {})
    return st


def _run(w, a, step, ticks=700):
    r = ACT.RUNNING
    for _ in range(ticks):
        r = ACT.advance(w, a, step)
        if r != ACT.RUNNING:
            return r
        w.tick += 1
    return r


def test_a_kiln_fires_bricks_from_the_stores():
    w, a = _world()
    evs = []
    w.listeners.append(evs.append)
    kiln = _build(w, a, "kiln", 6)
    kiln.durability = 50.0
    pile = _build(w, a, "stockpile", -4, 0, {"clay": 20, "sand": 20})
    w.learned(a, "recipe:brick", "taught")
    step = {"do": "work", "at": "kiln"}
    busy = 0  # ticks the kiln showed as worked (for the renderer's smoke) while the shift ran
    for _ in range(700):
        r = ACT.advance(w, a, step)
        busy += kiln.worked_until > w.tick
        if r != ACT.RUNNING:
            break
        w.tick += 1
    assert r == ACT.DONE, step["_s"]
    assert busy >= 10
    assert pile.storage.get("brick", 0) >= 2 and pile.storage["brick"] % 2 == 0
    assert pile.storage["clay"] == 20 - pile.storage["brick"] // 2 and pile.storage["sand"] == pile.storage["clay"]
    assert pile.storage["clay"] >= ACT.KEEP_STOCK["clay"]  # some clay is always left for builders and experiments
    assert kiln.produced == {"brick": pile.storage["brick"]} and a.stats["produced_brick"] == pile.storage["brick"]
    assert not a.inventory  # the goods went into the store, not the chit's arms
    assert kiln.durability > 50  # a kiln in use is kept up as it's used
    assert 0 < kiln.worked_until <= w.tick  # it was marked as working, and the shift is over
    assert views.structure_view(kiln, w)["worked_until"] == kiln.worked_until
    made = [e for e in evs if e.kind == "produced"]
    assert len(made) == 1 and made[0].importance == 2 and "brick" in made[0].text and a.name in made[0].text
    # a second shift soon after is not reported again (the chronicle isn't flooded), but it still counts
    w.tick += 5
    assert _run(w, a, {"do": "operate", "at": "the kiln"}) == ACT.DONE
    assert kiln.produced["brick"] > made[0].data["n"] and len([e for e in evs if e.kind == "produced"]) == 1


def test_a_furnace_smelts_copper_from_stored_ore_and_charcoal():
    w, a = _world()
    furnace = _build(w, a, "furnace", 5)
    pile = _build(w, a, "stockpile", -4, 0, {"ore": 10, "charcoal": 10})
    w.learned(a, "recipe:copper", "taught")
    a.add("wood", 5)  # hands already part full: the load goes down in the store to make room
    step = {"do": "work", "at": "furnace"}
    assert _run(w, a, step) == ACT.DONE, step["_s"]
    got = pile.storage.get("copper", 0)
    assert got >= 2 and furnace.produced == {"copper": got}
    assert pile.storage["ore"] == 10 - got and pile.storage["charcoal"] == 10 - got
    assert "copper" in step["_s"]["note"] and "furnace" in step["_s"]["note"]


def _iron_age(w, a, *known):
    """A world in the Iron Age (its next era is the Machine Age: a steam engine), whose worker knows `known`."""
    for k in ("recipe:pot", "recipe:clay_tablet", "recipe:copper", "recipe:iron"):
        w.first[k] = {"tick": 0, "by": a.id, "name": a.name}
    assert w.era()[1] == "Iron Age"
    for k in known:
        w.learned(a, f"recipe:{k}", "taught")


@pytest.mark.parametrize("design,key,storage", [
    ("kiln", "brick", {"clay": 20, "sand": 20}),
    ("furnace", "iron", {"ore": 14, "charcoal": 14}),
    ("forge", "steel", {"iron": 10, "charcoal": 10}),
    ("forge", "engine", {"steel": 6, "gear": 6, "pot": 3}),
    ("workshop", "gear", {"steel": 6}),
    ("workshop", "iron_axe", {"iron": 6, "wood": 20}),
    ("workshop", "iron_pick", {"iron": 6, "wood": 20, "cord": 6}),
    ("workshop", "wheel", {"iron": 6, "wood": 20}),
])
def test_bills_cover_the_road_to_the_machine_age(design, key, storage):
    w, a = _world()
    _iron_age(w, a, key)
    if key == "wheel":
        w.first["recipe:cart"] = {"tick": 0, "by": a.id, "name": a.name}  # wheels are made once someone knows the cart
    station = _build(w, a, design, 6)
    pile = _build(w, a, "stockpile", -4, 0, dict(storage))
    step = {"do": "work", "at": design}
    assert _run(w, a, step) == ACT.DONE, step["_s"]
    assert station.produced.get(key, 0) >= 1 and pile.storage.get(key, 0) >= storage.get(key, 0) + 1, (station.produced, pile.storage)


def test_the_road_to_the_next_era_comes_first():
    w, a = _world()
    _iron_age(w, a, "copper", "glass", "iron", "gear", "iron_axe")
    path = ACT.era_path(w)
    assert {"engine", "steel", "gear", "iron", "charcoal", "brick"} <= set(path)  # no forge yet: its bricks too
    # at the furnace: iron (on the way to a forge, steel and an engine), not copper or glass
    furnace = _build(w, a, "furnace", 6)
    _build(w, a, "stockpile", -4, 0, {"ore": 20, "charcoal": 20, "sand": 20})
    bill, _ = ACT.plan_bill(w, a, {"furnace"})
    assert bill.r.key == "iron" and bill.path and bill.st is furnace
    # with a forge standing, bricks are off the list; at the workshop gears come before iron axes, even with a few
    # gears already in store
    _build(w, a, "forge", -8, 4)
    assert "brick" not in ACT.era_path(w)
    _build(w, a, "workshop", 3, 6)
    _build(w, a, "stockpile", 6, 6, {"steel": 8, "gear": 2, "iron": 8, "wood": 30})
    bill, _ = ACT.plan_bill(w, a, {"workshop"})
    assert bill.r.key == "gear" and bill.path


def test_a_shift_leaves_raw_materials_for_builders_and_experimenters():
    w, a = _world()
    _build(w, a, "kiln", 6)
    pile = _build(w, a, "stockpile", -4, 0, {"clay": ACT.KEEP_STOCK["clay"] + 2, "sand": 20})
    w.learned(a, "recipe:brick", "taught")
    assert _run(w, a, {"do": "work", "at": "kiln"}) == ACT.DONE
    assert pile.storage["clay"] == ACT.KEEP_STOCK["clay"] and pile.storage["brick"] == 4


def test_no_room_in_the_stores_no_shift_and_full_hands_still_eat():
    w, a = _world()
    kiln = _build(w, a, "kiln", 6)
    pile = _build(w, a, "stockpile", -4, 0, {"clay": 20, "sand": 20, "stone": ACT.STOCKPILE_CAP * 7 // 10 - 40})
    w.learned(a, "recipe:brick", "taught")
    r = _run(w, a, {"do": "work", "at": "kiln"})
    assert "no room for brick" in r and not kiln.produced and not a.inventory
    # a chit whose hands are full of goods (a kiln shift's charcoal) puts some down to take food from the stores
    pile.storage.update({"berries": 10})
    a.add("charcoal", a.capacity())
    a.hunger = 10.0
    assert _run(w, a, {"do": "eat"}) == ACT.DONE and a.hunger > 10 and a.inventory.get("charcoal", 0) < a.capacity()


def test_no_known_bill_is_a_clear_message_and_nothing_happens():
    w, a = _world()
    kiln = _build(w, a, "kiln", 6)
    pile = _build(w, a, "stockpile", -4, 0, {"clay": 10, "sand": 10})
    a.plan = [{"do": "work", "at": "kiln"}, {"do": "rest"}]
    ACT.run(w, a)  # the step driver, as in the game: a failure must not raise or stop the world
    assert "don't know how to make anything at a kiln" in a.last_result
    assert a.plan == [] and not kiln.produced and pile.storage == {"clay": 10, "sand": 10}
    # knowing the recipe but lacking an input says what is missing, and a non-station says where work happens
    w.learned(a, "recipe:brick", "taught")
    pile.storage.pop("sand")
    r = _run(w, a, {"do": "work", "at": "kiln"})
    assert "brick needs clay + sand" in r and "stores" in r
    assert "isn't a place to work" in _run(w, a, {"do": "work", "at": "farm"})


def test_a_station_across_water_is_not_chosen():
    w, a = _world()
    # a pond beside the chit with an islet in it: a kiln on the islet is the nearest, but nobody can walk there
    cx, cy = a.x + 6, a.y
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            i = (cy + dy) * w.w + cx + dx
            w.tiles[i] = T.GRASS if max(abs(dx), abs(dy)) <= 1 else T.DEEP
            w.res_kind[i], w.res_amt[i] = T.R_NONE, 0
    w.rebuild_block()
    islet = w.place_site("kiln", cx, cy, a)
    w.complete_structure(islet, a)
    far = _build(w, a, "kiln", -12, 0, radius=3)
    pile = _build(w, a, "stockpile", -4, 0, {"clay": 30, "sand": 30})
    w.learned(a, "recipe:brick", "taught")
    assert not w.same_land(a, islet) and w.same_land(a, far)
    assert islet.dist(a.x, a.y) < far.dist(a.x, a.y)
    step = {"do": "work", "at": "kiln"}
    assert _run(w, a, step) == ACT.DONE, step["_s"]
    assert far.produced.get("brick") and not islet.produced and pile.storage.get("brick")
    # asked for the islet kiln by id, it still works the one it can reach
    assert _run(w, a, {"do": "work", "at": islet.id}) == ACT.DONE and not islet.produced


def test_instinct_works_a_station_and_crafters_lean_to_it():
    ins = Instinct()

    def share(job):
        w, a = _world(11)
        a.born = -240 * 10
        _build(w, a, "kiln", 5)
        _build(w, a, "stockpile", -4, 0, {"clay": 40, "sand": 40})
        w.learned(a, "recipe:brick", "taught")
        a.job, a.job_source = job, "chosen"
        hits = 0
        for t in range(200):
            w.tick = 1000 + t * 7
            a.hunger = a.energy = a.warmth = 100.0
            p = ins._progress(w, a, random.Random(t))
            if p and p["steps"][0]["do"] == "work":
                hits += 1
                assert p["steps"][0]["at"] == "kiln" and "kiln" in p["goal"]
        return hits / 200

    base, crafter = share(""), share("crafter")
    assert base > 0.05 and crafter > 1.5 * base, (base, crafter)


def test_work_is_in_the_verb_guide_and_old_saves_still_load():
    w, a = _world()
    assert '"do":"work","at":"kiln"' in P.verb_guide(w).replace(" ", "")
    for alias in ("work", "operate", "man", "tend", "run"):
        assert ACT.normalize_verb(alias) == "work"
    kiln = _build(w, a, "kiln", 6)
    kiln.produced["pot"] = 3
    d = kiln.to_dict()
    old = {k: v for k, v in d.items() if k not in ("worked_until", "produced")}  # a save from before production
    s = Structure.from_dict(old)
    assert s.worked_until == -1 and s.produced == {}
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.structures[kiln.id].produced == {"pot": 3}


def test_the_inspector_shows_who_is_at_work_and_what_the_station_has_made(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_SPEED", "0")  # paused: the test sets the scene itself
    from chits import app as APP

    with TestClient(APP.app) as c:
        w = APP.rt.worlds["A"]
        a = next(iter(w.agents.values()))
        kiln = _build(w, a, "kiln", 6)
        url = f"/api/worlds/A/structures/{kiln.id}"
        idle = c.get(url).json()
        assert idle["working"] is False and idle["workers"] == [] and idle["produced"] is None
        kiln.produced = {"brick": 6, "clay_tablet": 2}
        kiln.worked_until = w.tick + 40
        a.plan = [{"do": "work", "at": "kiln", "_s": {"st": kiln.id, "phase": "work"}}]
        busy = c.get(url).json()
        assert busy["working"] is True and busy["workers"] == [a.name] and busy["produced"] == {"brick": 6, "clay_tablet": 2}
        assert {k: busy["item_names"][k] for k in ("brick", "clay_tablet")} == {"brick": w.item_name("brick"), "clay_tablet": w.item_name("clay_tablet")}
        assert busy["item_names"]["clay_tablet"] != "clay_tablet"
