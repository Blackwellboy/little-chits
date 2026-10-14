"""The sea-raiders' age: a sail and a longship, rune charms and runestones, and the holmgang of rune, sail and axe
(rock, paper, scissors) that settles grudges and raids alike. Nobody is hurt in any of it."""

import random

from chits.brain import prompt as P
from chits.brain import voyages as VOY
from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import holmgang as HG
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS, RECIPES, match_recipe, normalize_design, normalize_item
from test_buildings import put, run_step, village
from test_trade_voyage import _close, _do, _put, _rivals, _village


def _pair():
    w, (a, b) = village()
    b.x, b.y = a.x + 1, a.y
    return w, a, b


def test_the_sail_the_charm_and_the_ideas_they_open():
    assert match_recipe({"cloth": 3}, "workshop").key == "sail"
    assert match_recipe({"stone": 1, "sharp_stone": 1}, None) is None  # a charm is given at a runestone, not made
    assert ("recipe", "sail") in DESIGNS["longship"].prereqs and DESIGNS["longship"].material_map["sail"] == 1
    assert DESIGNS["runestone"].prereqs == (("design", "longship"),)  # the raiders' age, after the sail
    assert normalize_design("dragon ship") == "longship" and normalize_design("rune stone") == "runestone"
    assert normalize_item("charm") == "rune_charm" and normalize_item("sails") == "sail"
    assert actions.normalize_verb("duel") == "holmgang" and actions.normalize_verb("plunder") == "pillage"
    assert actions.normalize_verb("rock_paper_scissors") == "holmgang"
    assert "sail" in RECIPES and "rune_charm" not in RECIPES


def test_rune_binds_axe_axe_cuts_sail_sail_outruns_rune():
    assert HG.BEATS == {"rune": "axe", "axe": "sail", "sail": "rune"}
    assert [HG.norm_throw(x) for x in ("Rock", "paper", "scissors", "RUNE", "wind", "spoon")] == \
        ["axe", "sail", "axe", "rune", "sail", None]
    w, a, b = _pair()
    mood = a.mood, b.mood
    res = HG.play(w, a, b, ["rune"], ["axe"])
    assert res["winner"] is a and res["score"] == {a.id: 2, b.id: 0} and len(res["rounds"]) == 2
    assert a.stats["throw_rune"] == 2 and b.stats["throw_axe"] == 2 and a.stats["holm_won"] == 1
    assert b.mood == max(0.0, mood[1] - HG.PRIDE) and a.health == 90.0 and b.health == 90.0  # pride, not blood
    assert any("threw axe, axe" in m.text for m in a.memories)
    assert HG.tale(res, a, b) == f"{a.name}'s rune binds the axe"
    # a tie is thrown again; never settled, the one challenged holds its ground
    res = HG.play(w, a, b, ["sail"], ["sail"])
    assert res["winner"] is b and len(res["rounds"]) == HG.MAX_ROUNDS


def test_a_rune_charm_turns_one_lost_round_and_a_runestone_wards_ties():
    w, a, b = _pair()
    a.inventory["rune_charm"] = 1
    res = HG.play(w, a, b, ["sail", "rune", "rune"], ["axe"])  # sail loses to axe: the charm flares
    assert res["rounds"][0]["charm"] == a.id and "rune_charm" not in a.inventory
    assert res["winner"] is a
    # without the charm the same throws lose the first round, and still win the next two
    w, a, b = _pair()
    res = HG.play(w, a, b, ["sail", "rune", "rune"], ["axe"])
    assert res["rounds"][0]["win"] == b.id and res["winner"] is a

    w, a, b = _pair()
    assert not HG.warded(w, a)
    put(w, "runestone", b, (b.x, b.y))
    w.tick += 1  # (the buildings at work are looked up once a tick)
    assert HG.warded(w, a) and HG.warded(w, b)
    res = HG.play(w, a, b, ["axe"], ["axe"])  # both warded: ties are thrown again as usual
    assert res["winner"] is b and len(res["rounds"]) == HG.MAX_ROUNDS
    b.origin = "B"  # a stranger is never warded by this island's runes
    res = HG.play(w, a, b, ["axe"], ["axe"])
    assert res["winner"] is a and all(r["ward"] for r in res["rounds"])
    assert HG.tale(res, a, b) == "the runestone's ward turned the tie for " + a.name


def test_praying_at_a_runestone_gives_one_of_its_island_a_rune_charm():
    w, a, b = _pair()
    rs = put(w, "runestone", b, (b.x, b.y))
    assert run_step(w, a, {"do": "pray", "target": rs.id}) == actions.DONE and a.inventory["rune_charm"] == 1
    assert run_step(w, a, {"do": "pray", "at": "runestone"}) == actions.DONE and a.inventory["rune_charm"] == 1  # one at a time
    b.origin = "B"
    assert run_step(w, b, {"do": "pray", "target": rs.id}) == actions.DONE and not b.inventory.get("rune_charm")
    assert "no shrine" in run_step(w, a, {"do": "pray"})  # a plain prayer still looks for a shrine


def test_without_named_throws_a_chit_plays_its_habit():
    w, a, b = _pair()
    a.stats.update({"holm_last": HG.THROWS.index("axe") + 1, "holm_last_won": 1})

    class Habitual:  # always follows the habit, and changes up when it lost
        def random(self):
            return 0.0

        def choice(self, seq):
            return seq[0]

    assert HG._habit_throw(a, Habitual()) == "axe"  # won with axe: axe again
    a.stats["holm_last_won"] = 0
    assert HG._habit_throw(a, Habitual()) == "rune"  # lost with axe: to what beats what beat it


def test_a_holmgang_settles_a_grudge_and_hurts_nobody():
    w, a, b = _pair()
    a.like(b.id, -40)
    b.like(a.id, -60)
    res = run_step(w, a, {"do": "duel", "to": b.name, "throws": "rune axe sail"})
    assert res == actions.DONE
    assert a.affinity[b.id] == 0.0 and b.affinity[a.id] == 0.0
    assert a.health == b.health == 90.0
    [ev] = [e for e in w.events if e.kind == "holmgang"]
    assert "rune, sail and axe" in ev.text and ev.data["winner"] in (a.id, b.id)


def test_pillage_is_only_for_raiders_from_over_the_sea():
    w, a, b = _pair()
    pile = put(w, "stockpile", b, (b.x, b.y))
    pile.storage["wood"] = 10
    assert "my own people's stores" in actions.advance(w, a, {"do": "pillage"})


def test_a_longship_raid_holmgang_plunder_and_home_with_the_ship(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    a, hut, pile = _village(wa)
    for w in (wa, wb):
        w.relation("B" if w is wa else "A")["state"] = "war"
    ship = _put(wa, a, "longship", (a.x, a.y))
    [(_, plan)] = VOY.options(wa, a, random.Random(1))
    assert plan["steps"] == [{"do": "sail", "target": ship.id, "intent": "raid"}]
    assert _do(wa, a, plan["steps"][0]) == actions.DONE
    [voyage] = wa.outbox
    assert voyage["arrive_tick"] - wa.tick == BLD.voyage_ticks(wa) // 2  # twice a boat's speed
    assert VOY.raid_plan(wa, next(iter(wa.agents.values()))) is None  # one raider at a time
    wa.tick = voyage["arrive_tick"]
    rt._deliver_boats()

    raider = next(x for x in wb.agents.values() if x.origin == "A")
    host = next(x for x in wb.agents.values() if not x.origin and not x.is_child(wb.tick))
    for o in wb.agents.values():
        if o is not raider and o is not host:
            o.x, o.y = 2, 2  # (out of the way: only the host stands at the stores)
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"stone": 20, "copper": 3, "wood": 5})
    raider.x, raider.y = host.x, host.y + 1
    hp = host.health
    monkeypatch.setattr(HG, "_habit_throw", lambda x, rng: "sail")  # the host always opens with sail...
    [(_, plan)] = VOY.options(wb, raider, random.Random(1))
    assert plan["steps"] == [{"do": "pillage"}]
    # ...and the raider, who has watched it, plays what beats it
    assert _do(wb, raider, {"do": "pillage", "throws": ["axe"]}) == actions.DONE
    [ev] = [e for e in wb.events if e.kind == "pillage"]
    assert ev.data["won"] and ev.data["defender"] == host.id and f"{raider.name}'s axe cuts the sail" in ev.text
    assert raider.inventory.get("copper") == 3  # the best goods first
    assert sum(raider.inventory.get(k, 0) for k in ("copper", "stone", "wood")) == actions.LONGSHIP_LOOT  # a longship's load
    assert raider.stats["stole_abroad"] == actions.LONGSHIP_LOOT and host.health == hp
    assert "time to sail home" in actions.advance(wb, raider, {"do": "pillage"})  # one raid a trip
    [(_, plan)] = VOY.options(wb, raider, random.Random(1))
    assert plan["steps"] == [{"do": "sail", "intent": "home"}]
    assert _do(wb, raider, plan["steps"][0]) == actions.DONE
    [back] = wb.outbox
    wb.tick = back["arrive_tick"]
    rt._deliver_boats()
    home = wa.agents[a.id]
    assert home.origin == "" and home.home == hut.id and home.inventory.get("copper") == 3
    assert any(s.design == "longship" for s in wa.structures.values())  # the ship came home too
    assert any(e.kind == "raid" and "longship laden with plunder" in e.text for e in wa.events)
    assert wa.relations["B"]["raids"] == 1
    _close(rt)


def test_a_raider_who_loses_the_holmgang_leaves_empty_handed(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wb = rt.worlds["B"]
    host = next(x for x in wb.agents.values() if not x.origin and not x.is_child(wb.tick))
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"stone": 20})
    raider = next(x for x in wb.agents.values() if x is not host)
    raider.origin, raider.voyage_intent = "A", "raid"
    for o in wb.agents.values():
        if o is not raider and o is not host:
            o.x, o.y = 2, 2
    raider.x, raider.y = host.x, host.y + 1
    hp = raider.health
    monkeypatch.setattr(HG, "_habit_throw", lambda x, rng: "rune")  # rune binds the raider's axe
    res = _do(wb, raider, {"do": "pillage", "throws": ["axe"]})
    assert "beat me in the holmgang" in res and not raider.inventory.get("stone") and stores.storage["stone"] == 20
    assert raider.health == hp and host.stats["raids_repelled"] == 1
    [ev] = [e for e in wb.events if e.kind == "pillage"]
    assert not ev.data["won"] and "left empty-handed" in ev.text
    _close(rt)


def test_an_unguarded_store_is_plundered_without_a_holmgang(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wb = rt.worlds["B"]
    host = next(x for x in wb.agents.values() if not x.origin)
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"stone": 20, "copper": 2})
    raider = next(x for x in wb.agents.values() if x is not host)
    raider.origin, raider.voyage_intent = "A", "raid"
    for o in wb.agents.values():
        if o is not raider:
            o.x, o.y = 2, 2
    raider.x, raider.y = stores.x, stores.y - 1
    assert _do(wb, raider, {"do": "pillage"}) == actions.DONE
    assert raider.inventory == {"copper": 2, "stone": actions.LOOT - 2} and stores.storage["stone"] == 20 - (actions.LOOT - 2)
    [ev] = [e for e in wb.events if e.kind == "pillage"]
    assert ev.data["won"] and not ev.data["defender"]
    _close(rt)


def test_at_war_a_village_with_a_boat_builds_a_longship(tmp_path, monkeypatch):
    rt = _rivals(tmp_path, monkeypatch)
    wa = rt.worlds["A"]
    a, hut, pile = _village(wa)
    a.learn("design:longship", "insight", wa.tick)
    a.inventory.update({"wood": 16, "cord": 6, "sail": 1})
    assert VOY.longship_plan(wa, a) is None  # at peace: no longship
    wa.relation("B")["state"] = "war"
    wa._nolongship.clear()
    plan = VOY.longship_plan(wa, a)
    assert plan["steps"][-1]["what"] == "longship"
    _close(rt)


def test_a_models_throws_survive_the_parser_and_nothing_else_does():
    from chits.brain.parse import parse_plan

    p = parse_plan('{"thought":"Bjorn opens with axe","goal":"win","plan":[{"do":"duel","to":"Bjorn",'
                   '"throws":["Rune","paper","fireball",{"x":1},"axe"]},{"do":"plunder","throw":"sail rune"}]}')
    assert p["steps"][0] == {"do": "holmgang", "to": "Bjorn", "throws": ["rune", "sail", "axe"]}
    assert p["steps"][1] == {"do": "pillage", "throws": ["sail", "rune"]}


def test_the_viking_verbs_are_offered_only_while_the_islands_can_meet():
    w, a, b = _pair()
    assert "pillage" not in P.verb_guide(w) and "holmgang" not in P.compact_system_prompt(w, a)
    w.contact = True
    assert "pillage" in P.verb_guide(w) and "holmgang" in P.compact_system_prompt(w, a)
    b.stats.update({"throw_axe": 3, "throw_rune": 1})  # what b threw against others: a never saw it
    assert "in holmgangs" not in P.scene(w, a)
    HG.play(w, a, b, ["rune"], ["axe"])
    assert "in holmgangs with you threw axe 2 times of 2" in P.scene(w, a)
    for leak in ("rune charm", "runestone", "longship"):  # nothing undiscovered is named
        assert leak not in P.verb_guide(w), leak
