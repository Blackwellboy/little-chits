"""Model plumbing: tolerant parsing, prompts, and the Mind driving chits through a real HTTP model server."""

import asyncio
import json
import socket
import threading
import time

import pytest

from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.brain.mind import Mind
from chits.brain.parse import ParseError, parse_lessons, parse_plan
from chits.sim.world import World

MESSY = [
    '{"thought":"hi","goal":"eat","plan":[{"do":"eat"}]}',
    '<think>long hidden reasoning {not json}</think>\n{"thought":"x","goal":"g","plan":[{"do":"gather","what":"wood","qty":3}]}',
    'Sure! Here you go:\n```json\n{"thought": "t", "goal": "g", "plan": [{"do": "explore", "dir": "N"},]}\n```',
    "{'thought': 'single quotes', 'goal': 'g', 'plan': [{'do': 'rest'}]}",
    '{"thought":"strings","plan":["gather wood x5","build hut","experiment stone + stone"]}',
    '{"goal":"g","steps":[{"action":"chop","item":"wood","amount":"4"}]}',
    '{"goal":"g","plan":[{"gather":"berries"}]}',
    '{"thought":"cut off","goal":"g","plan":[{"do":"gather","what":"stone","qty":2},{"do":"craft","what":"sharp stone"',
]


@pytest.mark.parametrize("text", MESSY)
def test_parse_messy_replies(text):
    p = parse_plan(text)
    assert p["steps"] and all("do" in s for s in p["steps"])


def test_parse_normalizes_steps():
    p = parse_plan(MESSY[4])
    assert p["steps"][0] == {"do": "gather", "what": "wood", "qty": 5}
    assert p["steps"][2]["do"] == "experiment"
    p = parse_plan(MESSY[5])
    assert p["steps"][0] == {"do": "gather", "what": "wood", "qty": 4}


def test_parse_rejects_garbage():
    with pytest.raises(ParseError):
        parse_plan("I will go look for berries now.")
    with pytest.raises(ParseError):
        parse_plan('{"plan": [{"do": "fly"}]}')


def test_lessons():
    assert parse_lessons('{"lessons":["Store food before winter.","Fires need wood."]}') == ["Store food before winter.", "Fires need wood."]


def test_prompt_is_local_and_honest():
    w = World("B", "B", 3, "stigmergy", 96, 6)
    a = next(iter(w.agents.values()))
    msgs = P.messages(w, a)
    sys_, user = msgs[0]["content"], msgs[1]["content"]
    assert "CANNOT talk" in sys_ and '"do":"say"' not in sys_ and '"do":"teach"' not in sys_
    assert a.name in user and "Hunger" in user
    # it never leaks the recipe book
    assert "stone axe" not in user and "furnace" not in user.split("YOU KNOW HOW TO BUILD")[0]


def test_instinct_plans_are_valid():
    w = World("A", "A", 11, "direct", 96, 8)
    ins = Instinct()
    for a in w.agents.values():
        p = ins.plan(w, a)
        assert 1 <= len(p["steps"]) <= 6 and p["goal"]


def test_instinct_never_gathers_into_full_hands():
    """A homeless chit with its arms full of hut materials and food used to plan "gather" forever and fail
    every time ("my hands are full"). After such a failure, its plan must make room before any gather."""
    from chits.sim.items import DESIGNS

    w = World("A", "A", 11, "direct", 96, 8)
    ins = Instinct()
    mats = list(DESIGNS["hut"].material_map)
    for i, a in enumerate(w.agents.values()):
        a.home = None
        a.inventory.clear()
        fill = [mats[i % len(mats)], "berries"]
        while a.free_space() > 0:
            k = fill[len(a.inventory) % 2] if a.free_space() >= a._item(fill[0]).weight else "berries"
            a.inventory[k] = a.inventory.get(k, 0) + 1
        a.hunger = 30 + 15 * (i % 4)
        a.last_result = "Could not gather wood x2: my hands are full"
        p = ins.plan(w, a)
        room = a.free_space()
        for s in p["steps"]:
            if s["do"] in ("drop", "store", "eat"):
                break
            if s["do"] == "gather":
                assert a._item(w.norm_item(s["what"])).weight <= room, (a.inventory, p)
                break


def test_speed_rating_says_whether_a_model_keeps_up():
    from chits.diag import speed_rating

    assert speed_rating(8, 2000, 50)["level"] == "good"      # 8 × 15 s / 2 s = 60 chits
    assert speed_rating(4, 2000, 50)["level"] == "ok"        # 30 of 50
    slow = speed_rating(4, 26000, 50)                        # about 2 chits: the old 3090 setup
    assert slow["level"] == "slow" and slow["capacity"] == 2 and "Too slow for 50 chits" in slow["text"]
    assert speed_rating(4, 0, 50)["level"] == "unknown" and speed_rating(4, 2000, 0)["level"] == "unknown"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def fake_llm():
    import uvicorn
    import fake_llm as F

    F.STATE["latency"] = 0.02
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    th.join(timeout=5)


async def test_mind_drives_chits_with_a_model(fake_llm, tmp_path):
    mind = Mind(tmp_path / "brains.json")
    mind.upsert({"id": "fake", "label": "Fake", "base_url": fake_llm, "max_concurrency": 8})
    w = World("A", "A", 21, "direct", 96, 8)
    mind.assign(w, "fake")
    for _ in range(400):
        w.step(mind.hook)
        await asyncio.sleep(0.002)
    await asyncio.sleep(0.3)
    b = mind.brains["fake"]
    assert b.stats.ok >= 8, b.stats
    assert b.stats.failed == 0
    assert any(a.plan_source.startswith("model:") for a in w.agents.values())
    assert sum(a.decisions for a in w.agents.values()) >= 8
    # config persisted for next launch
    saved = json.loads((tmp_path / "brains.json").read_text())
    assert saved["assign"]["A"] == "fake"
    await mind.close()


async def test_dead_model_falls_back_to_instinct(tmp_path):
    mind = Mind(tmp_path / "brains.json")
    mind.upsert({"id": "dead", "base_url": f"http://127.0.0.1:{_free_port()}/v1", "timeout": 1})
    w = World("A", "A", 22, "direct", 96, 6)
    mind.assign(w, "dead")
    for _ in range(200):
        w.step(mind.hook)
        await asyncio.sleep(0.003)
    # nobody froze: everyone is doing something even though the model never answered
    assert all(a.plan or a.activity != "idle" for a in w.agents.values())
    assert mind.brains["dead"].stats.failed > 0
    await mind.close()


async def test_probe_finds_the_real_base_url(fake_llm):
    from chits.brain.llm import probe_endpoint

    root = fake_llm[: -len("/v1")]
    for typed in (fake_llm, root, root.replace("http://", ""), fake_llm + "/chat/completions"):
        r = await probe_endpoint(typed)
        assert r["ok"], (typed, r)
        assert r["base_url"] == fake_llm and r["models"]
        assert 1 <= r["suggested"]["max_concurrency"] <= 16
    dead = await probe_endpoint("http://127.0.0.1:9/v1", timeout=1.0)
    assert not dead["ok"] and dead["error"]


async def test_first_run_autodetect_and_game_modes(fake_llm, tmp_path, monkeypatch):
    from chits.runtime import Runtime

    port = fake_llm.rsplit(":", 1)[1].split("/")[0]
    monkeypatch.setenv("CHITS_SCAN_PORTS", port)
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    rt = Runtime(tmp_path)
    assert rt.mode == "versus" and sorted(rt.worlds) == ["A", "B"]
    added = await rt.autodetect()
    # one model server found: a single world driven by it
    assert len(added) == 1 and rt.mode == "single" and list(rt.worlds) == ["A"]
    bid = added[0]["id"]
    assert all(a.brain == bid for a in rt.worlds["A"].agents.values())
    # model vs model on the exact same island: same seed, same chits, same rules; only the brain differs
    rt.mind.upsert({"id": "other", "base_url": fake_llm, "model": "fake-chit-7b"})
    rt.reset(seed=77, mode="versus", brains={"A": bid, "B": "other"})
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    assert wa.culture == wb.culture == "direct" and wa.flags == wb.flags
    assert wa.tiles == wb.tiles and [a.name for a in wa.agents.values()] == [b.name for b in wb.agents.values()]
    assert {a.brain for a in wa.agents.values()} == {bid} and {a.brain for a in wb.agents.values()} == {"other"}
    rt.reset(mode="culture")
    assert rt.worlds["B"].culture == "stigmergy"
    # a second start is not a first run: the user's choices are left alone
    rt2 = Runtime(tmp_path)
    assert rt2.mode == "culture" and await rt2.autodetect() == []
    await rt.mind.close()
    await rt2.mind.close()


def test_a_settled_but_stuck_world_is_nudged_to_experiment():
    from chits.brain import prompt as P

    w = World("A", "A", 11, "direct", 96, 4)
    a = next(iter(w.agents.values()))
    a.home, a.hunger = "s1", 90.0
    w.tick = 60  # morning of day 1: nothing stale yet
    assert "good time to experiment" not in P.scene(w, a)
    w.first["design:campfire"] = {"tick": 60, "by": a.id, "name": a.name}
    w.tick = 60 + 6 * 240 + 30  # six days later, still daytime
    assert "for 6 days" in P.scene(w, a) and "good time to experiment" in P.scene(w, a)
    a.hunger = 20.0  # hungry chits are told to eat, not to tinker
    assert "good time to experiment" not in P.scene(w, a)


def test_reflection_is_weekly_on_each_chits_own_day():
    from chits.brain.mind import REFLECT_EVERY_DAYS, reflection_due

    w = World("A", "A", 5, "direct", 64, 12)
    weekdays = set()
    for a in w.agents.values():
        days = []
        for day in range(21):
            for hour in range(24):
                if reflection_due(a, day, hour):
                    a.last_reflect_day = day
                    days.append(day)
        assert len(days) == 3 and days[1] - days[0] == days[2] - days[1] == REFLECT_EVERY_DAYS, days
        weekdays.add(days[0] % REFLECT_EVERY_DAYS)
    assert len(weekdays) > 2  # spread over the week, not everyone on the same day
    # a reflection put off by a busy brain still happens later that week, and only once
    a = next(iter(w.agents.values()))
    a.last_reflect_day = -1
    first = next(d for d in range(7) if reflection_due(a, d, 23))
    assert reflection_due(a, first + 1, 3)
    a.last_reflect_day = first + 1
    assert not any(reflection_due(a, d, h) for d in range(first + 2, first + 7) for h in range(24))


def test_a_dead_chiefs_laws_lapse():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 6)
    chief, other, reader = list(w.agents.values())[:3]
    w.leader = chief.id
    w.tick = 100
    assert w.decree(chief, "Secure seeds for every plot before building")
    w.tick = 100 + 30 * 240
    assert "Secure seeds" in P.scene(w, reader)  # the chief still leads: the law holds
    w.leader = other.id
    assert "Secure seeds" not in P.scene(w, reader)  # a month on, under a new chief, it has lapsed
    w.tick = 100 + 3 * 240
    assert "Secure seeds" in P.scene(w, reader)  # a recent decree outlives its chief for a while




def test_untried_pairs_include_doubles_and_skip_what_failed():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.familiar = {"stone", "wood", "fiber"}
    a.failed_experiments = ["stone + wood at the fire", "plant fiber + wood"]
    seen = set()
    for day in range(60):
        w.tick = day * 240
        got = P.untried_pairs(w, a)
        assert len(got) == 3 and "stone + wood" not in got and "wood + stone" not in got
        assert not any(set(g.split(" + ")) == {"plant fiber", "wood"} for g in got)
        seen |= set(got)
    assert {"stone + stone", "plant fiber + plant fiber", "wood + wood"} <= seen  # doubles come up too
    a.failed_experiments.append("2 stone")
    assert all("stone + stone" not in P.untried_pairs(w, a) for w.tick in range(0, 9600, 240))
    assert "never tried" in P.scene(w, a)


def test_untried_combinations_reach_kilns_and_three_part_tools():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.familiar = {"stone", "wood", "fiber", "clay", "cord", "sharp_stone"}
    a.knows.update({"recipe:cord": {}, "recipe:sharp_stone": {}})
    a.failed_experiments = ["stone + wood"]
    spot = w.find_site("kiln", a.x, a.y)
    w.complete_structure(w.place_site("kiln", spot[0], spot[1], a), a)
    assert w.nearest_station(a.x, a.y, "kiln", 20)
    seen = set()
    for day in range(80):
        w.tick = day * 240
        seen |= set(P.untried_pairs(w, a))
    assert "clay at the kiln" in seen  # a clay pot is one clay fired in a kiln
    assert any(len(s.split(" + ")) == 3 and ("cord" in s or "sharp stone" in s) for s in seen)  # a stone axe has 3


def test_parser_keeps_trade_bags_and_item_counts():
    import json as _json

    def steps(*st):
        return parse_plan(_json.dumps({"goal": "g", "plan": list(st)}))["steps"]

    s = steps({"do": "trade", "to": "Bo", "give": {"stone": 3}, "get": {"seeds": 1}})[0]
    assert s["give"] == {"stone": 3} and s["get"] == {"seeds": 1}
    s = steps({"do": "trade", "to": "Bo", "give": {"item": "wood", "qty": 2}, "get": "berries"})[0]
    assert s["give"] == {"wood": 2} and s["get"] == "berries"
    s = steps({"do": "give", "to": "Bo", "what": {"seeds": 2}})[0]
    assert s["what"] == "seeds" and s["qty"] == 2
    s = steps({"do": "store", "what": {"item": "wood", "qty": 4}})[0]
    assert s["what"] == "wood" and s["qty"] == 4
    s = steps({"do": "take", "what": "3 seeds"})[0]
    assert s["what"] == "seeds" and s["qty"] == 3


def test_a_parsed_model_trade_goes_through():
    import json as _json
    from chits.sim import actions as ACT

    w = World("A", "A", 5, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    b.x, b.y = a.x + 1, a.y
    a.inventory.clear(); b.inventory.clear()
    a.add("stone", 3); b.add("seeds", 2)
    step = parse_plan(_json.dumps({"goal": "g", "plan": [{"do": "trade", "to": b.name, "give": {"stone": 3}, "get": {"seeds": 1}}]}))["steps"][0]
    for _ in range(40):
        r = ACT.advance(w, a, step)
        if r != ACT.RUNNING:
            break
    assert r == ACT.DONE, r
    assert a.inventory.get("seeds") == 1 and b.inventory.get("stone") == 3


def test_instinct_tries_two_of_the_same_thing():
    """Cord is 2 plant fiber: drawn at random, doubles were 3 bags in 299 and seed 2 never found cord."""
    import random
    from chits.brain.instinct import Instinct

    w = World("A", "A", 2, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    ins = Instinct()
    doubles = total = 0
    for i in range(400):
        a.failed_experiments = []
        p = ins._experiment(w, a, random.Random(i))
        exp = next((s for s in (p or {}).get("steps", []) if s.get("do") == "experiment"), None)
        if exp:
            bag = list(exp.get("with") or [])
            total += 1
            doubles += len(bag) == 2 and bag[0] == bag[1]
    assert total > 100 and doubles / total > 0.14, (doubles, total)  # was 8.5% here, 19% now


def test_the_prompt_shows_the_villages_food_at_a_glance():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("stockpile", a.x + 3, a.y, 5)
    pile = w.place_site("stockpile", xy[0], xy[1], a)
    w.complete_structure(pile, a)
    pile.storage.update({"seeds": 241})
    for i, (planted, growth) in enumerate(((True, 1.0), (True, 0.5), (False, 0.0), (False, 0.0))):
        xy = w.find_site("farm", a.x - 4, a.y + i * 3, 6)
        f = w.place_site("farm", xy[0], xy[1], a)
        w.complete_structure(f, a)
        f.planted, f.growth = planted, growth
    line = P.food_around(w, a)
    assert line == "no food stored; 241 seeds stored; farms: 1 ripe (harvest them), 1 growing, 2 empty (plant 2 seeds in each).", line
    assert "Food around here: no food stored" in P.scene(w, a)


def test_instinct_answers_and_shares_what_was_asked_for():
    w = World("A", "A", 5, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    ins = Instinct()
    a.hunger = a.energy = a.warmth = 90.0
    a.inventory.clear(); a.add("wood", 6)
    a.spoken_to = {"id": b.id, "name": b.name, "text": "Could you spare some wood?", "tick": w.tick}
    steps = ins._answer(w, a, "gather stone")
    assert steps[0]["do"] == "say" and steps[0]["to"] == b.name
    assert steps[1] == {"do": "give", "to": b.name, "what": "wood", "qty": 2}
    a.spoken_to["text"] = "Nice weather."
    steps = ins._answer(w, a, "gather stone")
    assert len(steps) == 1 and "gather stone" in steps[0]["text"]
    w.tick += 500  # too long ago
    assert ins._answer(w, a, "x") == []


def test_an_older_save_keeps_its_unfinished_sites():
    from chits.sim.agent import TICKS_PER_DAY

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    xy = w.find_site("hut", a.x, a.y)
    site = w.place_site("hut", xy[0], xy[1], a)
    site.builders[a.id] = 4
    w.tick += TICKS_PER_DAY * 11
    d = w.to_dict()
    for s in d["structures"]:
        s.pop("last_work", None)  # a save from before sites remembered their last work
    w2 = World.from_dict(d)
    w2.step(lambda world, ag: None)
    assert site.id in w2.structures


def test_base_item_names_beat_local_names():
    w = World("B", "B", 5, "direct", 64, 1)
    w.culture_names["recipe:sharp_stone"] = "Stone"  # a discoverer named it after a base item
    w.culture_names["recipe:brick"] = "pottery"
    assert w.norm_item("stone") == "stone" and w.norm_item("pottery") == "brick"


def test_weekly_reflections_keep_their_own_hour():
    from chits.brain.mind import REFLECT_EVERY_DAYS, reflection_due

    w = World("A", "A", 5, "direct", 64, 12)
    for a in w.agents.values():
        hours = []
        for day in range(28):
            for hour in range(24):
                if reflection_due(a, day, hour):
                    a.last_reflect_day = day
                    hours.append(hour)
        assert len(hours) == 4 and len(set(hours)) == 1 and hours[0] >= 8, hours


def test_answers_match_whole_words():
    w = World("A", "A", 5, "direct", 64, 2)
    a, b = list(w.agents.values())[:2]
    a.inventory.clear(); a.add("ore", 3); a.add("stone", 3)
    a.spoken_to = {"id": b.id, "name": b.name, "text": "help me build some more huts before winter?", "tick": w.tick}
    assert [s["do"] for s in Instinct()._answer(w, a, "x")] == ["say"]  # "ore" is not in "more"
    a.spoken_to["text"] = "Can you spare stones?"
    assert Instinct()._answer(w, a, "x")[1]["what"] == "stone"


def test_a_colon_where_the_comma_belongs_is_repaired():
    txt = ('{"thought":"It\'s cold, so I\'ll gather.","objective":"survive before winter":"goal":"gather wood",'
           '"plan":[{"do":"gather","what":"wood","qty":5},{"do":"rest"}]}')
    p = parse_plan(txt)
    assert p["goal"] == "gather wood" and p["objective"] == "survive before winter" and len(p["steps"]) == 2
    ok = '{"thought":"a: b","goal":"x:y","plan":[{"do":"say","to":"all","text":"time: now"}]}'
    assert parse_plan(ok)["steps"][0]["text"] == "time: now"  # colons inside strings are left alone


def test_chits_know_what_their_neighbours_tried_without_luck():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 3)
    a, b, c = list(w.agents.values())[:3]
    b.x, b.y = a.x + 2, a.y
    c.x, c.y = a.x + 3, a.y
    a.familiar = {"stone", "wood", "fiber"}
    b.failed_experiments = ["2 wood at the fire", "stone + wood"]
    c.failed_experiments = ["2 wood at the fire"]
    assert w.village_failed(a)["2 wood at the fire"] == 2
    scene = P.scene(w, a)
    assert "Others around here already tried these, with no luck: 2 wood at the fire; stone + wood." in scene
    for day in range(40):
        w.tick = day * 240
        got = P.untried_pairs(w, a)
        assert "wood + wood" not in got and "stone + wood" not in got and "wood + stone" not in got


def test_instinct_follows_up_a_near_miss():
    import random

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.familiar = {"wood", "cord", "sharp_stone", "stone", "fiber"}
    a.inventory.clear()
    a.add("cord", 1); a.add("wood", 1); a.add("sharp_stone", 1)
    a.remember(w.tick, "Tried cord + wood: nothing useful happened. The pieces seemed to want something more.", 2, "experiment")
    bags = set()
    for i in range(40):
        p = Instinct()._near_miss(w, a, random.Random(i))
        exp = next((s for s in (p or {}).get("steps", []) if s.get("do") == "experiment"), None)
        if exp:
            bags.add(tuple(sorted(exp["with"])))
    assert bags and all(len(b) == 3 and "cord" in b and "wood" in b for b in bags)
    assert ("cord", "sharp_stone", "wood") in bags  # a stone axe, a near miss away


def test_instinct_takes_a_hinted_mix_to_the_furnace():
    import random

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("furnace", a.x + 3, a.y, 6)
    w.complete_structure(w.place_site("furnace", xy[0], xy[1], a), a)
    a.inventory.clear(); a.add("charcoal", 1); a.add("ore", 1)
    a.remember(w.tick, "Tried charcoal + copper ore: nothing useful happened. Only a truly roaring fire could change this.",
               2, "experiment")
    p = Instinct()._near_miss(w, a, random.Random(1))
    exp = next(s for s in p["steps"] if s.get("do") == "experiment")
    assert sorted(exp["with"]) == ["charcoal", "ore"] and exp.get("at") == "furnace"


def test_the_never_tried_hint_includes_a_toolmakers_idea():
    from chits.brain import prompt as P

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.familiar = {"wood", "stone", "cord", "seeds", "grain", "berries"}
    a.failed_experiments = ["2 wood at the fire"]
    days_with_tool_idea = 0
    for day in range(10):
        w.tick = day * 240
        got = P.untried_pairs(w, a)
        days_with_tool_idea += any(set(g.split(" + ")) == {"cord", "stone", "wood"} for g in got)
    assert days_with_tool_idea >= 8  # a handle, a hard head and a binding: every day until it's tried


def test_instinct_skips_gathering_what_isnt_nearby_for_a_day():
    from chits.sim.actions import advance

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    from chits.sim import terrain as T
    clay = T.RES_INDEX["clay"]
    for i, k in enumerate(w.res_kind):  # no clay anywhere
        if k == clay:
            w.res_amt[i] = 0
    assert "no clay anywhere" in advance(w, a, {"do": "gather", "what": "clay", "qty": 3})
    assert a.reflex_rest.get("scarce:clay", 0) > w.tick
    ins = Instinct()
    for t in range(60):
        w.tick += 7
        a.plan = []
        p = ins.plan(w, a)
        assert not any(s.get("do") == "gather" and s.get("what") == "clay" for s in p["steps"])


def test_the_copper_chain_is_reachable_from_the_stockpile():
    import random

    w = World("A", "A", 5, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    w.structures.clear(); w.occupied.clear()
    xy = w.find_site("furnace", a.x + 3, a.y, 6)
    w.complete_structure(w.place_site("furnace", xy[0], xy[1], a), a)
    xy = w.find_site("stockpile", a.x - 3, a.y, 6)
    pile = w.place_site("stockpile", xy[0], xy[1], a)
    w.complete_structure(pile, a)
    pile.storage.update({"ore": 5, "charcoal": 5})
    a.inventory.clear()
    ins = Instinct()
    ins._world = w
    bags = [ins._heat_idea(w, a, random.Random(i)) for i in range(20)]
    assert all(b and "charcoal" in b and "ore" in b for b in bags)
    plan = ins._exp_plan(a, ["charcoal", "ore"], "furnace", "t")
    assert [s["do"] for s in plan["steps"]] == ["take", "take", "experiment"]  # from the store, no pick needed
    from chits.brain import prompt as P
    a.failed_experiments = ["2 wood"]
    assert any(s in ("charcoal + copper ore at the furnace", "copper ore + charcoal at the furnace")
               for s in P.untried_pairs(w, a))


def test_children_grow_up_with_some_of_their_parents_recipes():
    w = World("A", "A", 5, "direct", 64, 3)
    a, b = list(w.agents.values())[:2]
    for k in ("recipe:cord", "recipe:charcoal", "recipe:brick", "recipe:pot", "recipe:spear", "recipe:basket"):
        a.learn(k, "discovered", w.tick)
    spot = w.find_site("hut", a.x, a.y)
    hut = w.place_site("hut", spot[0], spot[1], a)
    w.complete_structure(hut, a)
    child = w._make_child(a, b, hut)
    got = [k for k in child.knows if k.startswith("recipe:")]
    assert 0 < len(got) < 6 and all(child.knows[k]["status"] == "told" for k in got)


def test_choose_mode_adopts_the_plan_the_model_picked():
    import asyncio
    from chits.brain.mind import Mind

    w = World("A", "A", 5, "direct", 64, 3)
    for _ in range(300):
        w.step(lambda world, ag: None)
    a = next(iter(w.agents.values()))
    m = Mind(None)
    m.upsert({"id": "x", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "choose"})
    m.assign(w, "x")
    brain = m.brains["x"]
    seen = {}

    async def fake_chat(messages, **kw):
        msgs = messages() if callable(messages) else messages
        seen["kw"], seen["msgs"] = kw, msgs
        return {"text": "B", "latency_ms": 5.0, "tokens_in": 900, "tokens_out": 1,
                "top_logprobs": {"B": -0.1, "A": -2.5, " C": -3.0}}

    brain.chat = fake_chat

    async def go():
        m._ask(w, a, brain)
        await asyncio.gather(*list(m._tasks))

    asyncio.run(go())
    assert seen["kw"]["max_tokens"] == 1 and seen["kw"]["extra"]["logprobs"] is True
    assert "YOUR OPTIONS:" in seen["msgs"][1]["content"] and "B) " in seen["msgs"][1]["content"]
    rows = [l for l in seen["msgs"][1]["content"].splitlines() if l[:3] in ("A) ", "B) ", "C) ", "D) ", "E) ", "F) ", "G) ")]
    assert len(rows) >= 2 and a.pending_plan and a.pending_plan["steps"]
    assert rows[1].startswith("B) " + a.pending_plan["goal"])  # the plan behind the letter it chose
    assert m.log[-1]["chose"].startswith("B of") and m.log[-1]["confidence"] == 0.9


def _cascade_run(first_logprobs):
    import asyncio
    import json as _json
    from chits.brain.mind import Mind

    w = World("A", "A", 5, "direct", 64, 3)
    for _ in range(300):
        w.step(lambda world, ag: None)
    a = next(iter(w.agents.values()))
    m = Mind(None)
    m.upsert({"id": "x", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "cascade", "escalate_below": 0.5})
    m.assign(w, "x")
    brain = m.brains["x"]
    calls = []

    async def fake_chat(messages, **kw):
        msgs = messages() if callable(messages) else messages
        calls.append((kw, msgs))
        if kw.get("max_tokens") == 1:
            return {"text": "A", "latency_ms": 5.0, "tokens_in": 500, "tokens_out": 1, "top_logprobs": first_logprobs(msgs)}
        plan = {"thought": "I will try something new.", "goal": "my own idea",
                "plan": [{"do": "gather", "what": "stone", "qty": 2}, {"do": "experiment", "with": ["stone", "stone"]}]}
        return {"text": _json.dumps(plan), "latency_ms": 50.0, "tokens_in": 2000, "tokens_out": 60, "top_logprobs": {}}

    brain.chat = fake_chat

    async def go():
        m._ask(w, a, brain)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))

    asyncio.run(go())
    asyncio.run(m.close())
    return a, calls


def test_cascade_keeps_confident_choices_to_one_token():
    a, calls = _cascade_run(lambda msgs: {"A": -0.05, "B": -3.0})
    assert len(calls) == 1 and calls[0][0]["max_tokens"] == 1
    assert "my own idea" in calls[0][1][1]["content"]  # always on offer
    assert a.last_choice["chose"] == "A" and not a.last_choice["escalated"]
    assert a.pending_plan and a.pending_plan["steps"]


def test_cascade_escalates_its_own_idea_to_a_written_plan():
    def own(msgs):
        last = [l for l in msgs[1]["content"].splitlines() if l.endswith("my own idea")][0][0]
        return {last: -0.1, "A": -2.5}
    a, calls = _cascade_run(own)
    assert len(calls) == 2 and calls[1][0].get("max_tokens") is None  # the second call writes a whole plan
    assert a.last_choice["escalated"] and a.last_choice["why"] == "its own idea"
    assert a.pending_plan["goal"] == "my own idea"


def test_cascade_keeps_to_its_escalation_budget():
    import asyncio
    from collections import deque
    from chits.brain.mind import Mind

    w = World("A", "A", 5, "direct", 64, 3)
    for _ in range(300):
        w.step(lambda world, ag: None)
    a = next(iter(w.agents.values()))
    m = Mind(None)
    m.upsert({"id": "x", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "cascade", "escalate_share": 0.3})
    m.assign(w, "x")
    brain = m.brains["x"]
    brain.recent_escalations = deque([True] * 10 + [False] * 10, maxlen=40)  # 50% already: over budget
    calls = []

    async def fake_chat(messages, **kw):
        msgs = messages() if callable(messages) else messages
        calls.append(kw)
        own = [l for l in msgs[1]["content"].splitlines() if l.endswith("my own idea")][0][0]
        return {"text": own, "latency_ms": 5.0, "tokens_in": 500, "tokens_out": 1, "top_logprobs": {own: -0.1, "B": -2.0}}

    brain.chat = fake_chat

    async def go():
        m._ask(w, a, brain)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))

    asyncio.run(go())
    assert len(calls) == 1 and not a.last_choice["escalated"]
    assert "busy" in a.last_choice["why"] and a.pending_plan["goal"] == a.last_choice["options"][1]["goal"]  # its next best
    asyncio.run(m.close())
