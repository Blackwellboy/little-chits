"""The story so far: a recap for someone who has just arrived, from the world's own record. Every line is a count or
a quote; no model is asked, and the world is not changed."""

import asyncio
import json

from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World
from chits.story.recap import lost_arts, recap


def _world(seed=5, name="A"):
    w = World(name, name, seed, "direct", 64, 6)
    w.tick = 400 * TICKS_PER_DAY
    ags = list(w.agents.values())
    w.first.update({"design:campfire": {"tick": 10, "by": ags[0].id, "name": ags[0].name},
                    "recipe:stone_axe": {"tick": 60 * TICKS_PER_DAY, "by": ags[1].id, "name": ags[1].name},
                    "recipe:copper": {"tick": 300 * TICKS_PER_DAY, "by": ags[2].id, "name": ags[2].name},
                    "recipe:iron": {"tick": 380 * TICKS_PER_DAY, "by": ags[3].id, "name": ags[3].name}})
    w.built_designs["campfire"] = w.first["design:campfire"]  # (deeds: Firekeepers needs a campfire standing)
    w.update_era()
    for a in ags:  # everyone knows what the world has made, but iron (the tests take things away from here)
        for k in ("design:campfire", "recipe:stone_axe", "recipe:copper"):
            a.knows.setdefault(k, {"how": "taught", "tick": 0})
    return w, ags


def test_the_story_so_far_is_told_from_the_record():
    w, ags = _world()
    keno = ags[3]
    w.kill(keno, "starvation")  # the only one who knew how to make iron
    other = ags[4]  # more firsts than Keno, none of them an age's
    w.first["recipe:cord"] = {"tick": 50, "by": other.id, "name": other.name}
    w.first["design:stockpile"] = {"tick": 60, "by": other.id, "name": other.name}
    w.kill(other, "old age")
    for a in w.agents.values():
        a.knows.pop("recipe:iron", None)
    w.leader = ags[0].id
    w.decree(ags[0], "No skill is buried with its keeper.")
    rival, _ = _world(9, "B")
    rival.first["recipe:iron"]["tick"] = 320 * TICKS_PER_DAY
    r = recap(w, {"law": 12, "storm": 7, "drought": 2, "wolf": 30}, rival)
    text = "\n".join(r["lines"])
    remembered_lines = [line for line in r["lines"] if line.startswith("Remembered:")]
    assert remembered_lines[0].startswith(f"Remembered: {keno.name},")  # who began the Iron Age, before more firsts
    assert r["title"] == "A: the story so far" and r["day"] == 401
    for bit in ("Day 401. 4 chits", "2 have died", "Firekeepers (day 1)", "Iron Age (day 381)",
                "Next is the Machine Age, when someone first makes a steam engine.",
                "Once known, now forgotten: iron,", f"Remembered: {keno.name}, who was the first to make iron; died of starvation",
                "12 laws decreed; the latest, by Chief", "No skill is buried with its keeper.",
                "7 storms, 2 droughts and 30 wolf attacks", "B reached the Iron Age first, by 60 days.", f"Now: Chief {ags[0].name} leads"):
        assert bit in text, bit


def test_lost_arts_lead_with_the_road_through_the_ages():
    from chits.sim.items import base_value

    w, ags = _world()
    w.first["recipe:pot"] = {"tick": 5, "by": ags[0].id, "name": ags[0].name}  # the Potters' own art: cheap
    w.first["recipe:wheel"] = {"tick": 6, "by": ags[0].id, "name": ags[0].name}  # worth more, but no age's mark
    assert base_value("wheel") > base_value("pot")
    for a in w.agents.values():
        a.knows["recipe:iron"] = {"how": "taught", "tick": 0}
        a.knows.pop("recipe:pot", None)
        a.knows.pop("recipe:wheel", None)
    assert lost_arts(w) == ["clay pot", "wheel"]  # the age's own art first, however much a thing is worth


def test_the_recap_only_reads_and_counts_only_its_own_timeline(tmp_path):
    from chits.runtime import Runtime

    w, ags = _world()
    before = json.dumps(w.to_dict(), sort_keys=True, default=str)
    recap(w, {}, None)
    assert json.dumps(w.to_dict(), sort_keys=True, default=str) == before
    rt = Runtime(tmp_path)
    x = next(iter(rt.worlds.values()))
    rows = [(x.id, 10 ** 6 + i, 5, "storm", 4, None, "A storm", "{}", x.uuid, x.epoch) for i in range(3)]
    rows += [(x.id, 10 ** 6 + 9, 5, "storm", 4, None, "an old game's storm", "{}", "old", "another-epoch"),
             ("Z", 10 ** 6 + 8, 5, "storm", 4, None, "another world's", "{}", "z", "z")]
    rt.store.db.executemany("INSERT INTO events (world_id, seq, tick, kind, importance, actor, text, data, world_uuid, epoch) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    got = rt.store.count_kinds(x.id, ("storm", "law"), epoch=x.timeline())
    assert got == {"storm": 3}  # this world, this timeline, the kinds asked for
    assert rt.store.count_kinds("nope", ("storm",)) == {}
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_wolves_driven_off_are_not_attacks_and_a_long_life_is_worth_remembering(tmp_path):
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    x = next(iter(rt.worlds.values()))
    rows = [(x.id, 2 * 10 ** 6, 5, "wolf", 3, None, "A wolf attacked", "{}", x.uuid, x.epoch),
            (x.id, 2 * 10 ** 6 + 1, 5, "wolf", 2, None, "The lookout drove it off", '{"driven_off": true}', x.uuid, x.epoch)]
    rt.store.db.executemany("INSERT INTO events (world_id, seq, tick, kind, importance, actor, text, data, world_uuid, epoch) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    assert rt.store.count_kinds(x.id, ("wolf",), epoch=x.timeline(), unless="driven_off") == {"wolf": 1}
    rt.store.db.close()
    asyncio.run(rt.mind.close())
    w, ags = _world()
    elder = ags[5]
    elder.born = w.tick - 80 * TICKS_PER_DAY
    w.kill(elder, "old age")
    lines = [l for l in recap(w, {}, None)["lines"] if l.startswith(f"Remembered: {elder.name}")]
    assert lines and "who lived to 80 days" in lines[0] and "taught 0" not in lines[0]
