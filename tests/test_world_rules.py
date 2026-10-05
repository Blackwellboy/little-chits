"""World rules (sim/rules.py, docs/WORLD_RULES.md): a frozen, versioned record of what a world allows, chosen when it
is made and saved with it. The first rule is religion: off, no path may make or use a belief. Each path is tested in
pairs: on, the effect happens (so the test reaches the path); off, it doesn't."""

import json

import pytest

from chits.brain import prompt as P
from chits.brain.mind import apply_reflection
from chits.sim import actions
from chits.sim.rules import LEGACY, RULES_VERSION, WorldRules
from chits.sim.world import Tablet, World

ON, OFF = WorldRules(religion=True), WorldRules(religion=False)


def world(rules, n=6, seed=3):
    w = World("A", "A", seed, "direct", 64, n, rules=rules)
    for a in w.agents.values():
        a.x, a.y = 30, 30
        a.hunger = a.energy = a.warmth = a.health = 95.0
        a.mood = 50.0
    return w, list(w.agents.values())


def inject_belief(w, founder):
    """A belief put in place by hand: a religion-off world can't make one, so its gates are tested against one."""
    bid = "belief_t"
    w.beliefs[bid] = {"id": bid, "name": "The Test", "tenet": "Tests reveal the truth", "founder": founder.id,
                      "founder_name": founder.name, "tick": w.tick, "followers": [founder.id]}
    founder.belief = bid
    return bid


def shrine(w, a, bid=""):
    s = w.place_site("shrine", *w.find_site("shrine", a.x + 2, a.y, 8), a)
    w.complete_structure(s, a)
    s.belief = bid
    return s


def run_plan(w, a, steps, ticks=400):
    a.plan = [dict(s) for s in steps]
    for _ in range(ticks):
        if not a.plan:
            break
        actions.run(w, a)
        w.tick += 1


# ------------------------------------------------------------------------------------------------- the record

def test_the_default_is_the_legacy_set_and_round_trips():
    assert WorldRules() == LEGACY and LEGACY.religion is True and LEGACY.version == RULES_VERSION
    assert WorldRules.from_dict(None) == LEGACY  # (a world from before rules)
    assert WorldRules.from_dict(OFF.to_dict()) == OFF
    assert OFF.changed() == {"religion": False} and LEGACY.changed() == {}
    with pytest.raises(Exception):
        OFF.religion = True  # frozen: a world's rules don't change while it runs


@pytest.mark.parametrize("bad", [{"version": RULES_VERSION + 1}, {"telepathy": True}, {"religion": "no"},
                                 {"religion": 0}, {"version": True}, []])
def test_a_rule_set_is_never_guessed(bad):
    with pytest.raises(ValueError):
        WorldRules.from_dict(bad)


def test_a_world_saves_and_loads_its_rules_and_an_old_save_gets_the_legacy_set():
    w, _ = world(OFF)
    d = json.loads(json.dumps(w.to_dict()))
    assert d["rules"] == {**WorldRules().to_dict(), "religion": False} and d["rules"]["version"] == RULES_VERSION
    assert World.from_dict(d).rules == OFF
    old = dict(d)
    old.pop("rules")  # a save from before world rules
    assert World.from_dict(old).rules == LEGACY
    with pytest.raises(ValueError):
        World.from_dict(dict(d, rules={"version": RULES_VERSION + 1, "religion": False}))


def test_the_legacy_set_given_explicitly_plays_exactly_as_no_rules_at_all():
    a, b = World("A", "A", 11, "direct", 64, 8), World("A", "A", 11, "direct", 64, 8, rules=WorldRules(religion=True))
    for _ in range(2 * 240):
        a.step()
        b.step()
    from identity_runner import normal  # (without the uuid labels a world and its steps carry)

    assert json.dumps(normal(a.to_dict()), sort_keys=True, default=str) ==         json.dumps(normal(b.to_dict()), sort_keys=True, default=str)


# ----------------------------------------------------------------------------------- religion: the state paths

@pytest.mark.parametrize("rules", [ON, OFF])
def test_founding_and_converting(rules):
    w, ags = world(rules)
    bid = w.found_belief(ags[0], "The Way", "The fire remembers those who feed it")
    assert bool(bid) is rules.religion and bool(w.beliefs) is rules.religion
    if not rules.religion:
        bid = inject_belief(w, ags[0])
    assert w.convert(ags[1], bid, "they chose it") is rules.religion
    assert (ags[1].belief == bid) is rules.religion


@pytest.mark.parametrize("rules", [ON, OFF])
def test_a_child_of_two_believers(rules):
    w, ags = world(rules)
    bid = inject_belief(w, ags[0])
    ags[1].belief = bid
    w.beliefs[bid]["followers"].append(ags[1].id)
    home = w.place_site("hut", *w.find_site("hut", 30, 34, 10), ags[0])
    w.complete_structure(home, ags[0])
    child = w._make_child(ags[0], ags[1], home)
    assert (child.belief == bid) is rules.religion


@pytest.mark.parametrize("rules", [ON, OFF])
def test_prayer(rules):
    w, ags = world(rules)
    a = ags[0]
    bid = inject_belief(w, ags[1])
    shrine(w, ags[1], bid)
    mood = a.mood
    run_plan(w, a, [{"do": "pray"}])
    assert (a.belief == bid) is rules.religion and (a.mood > mood) is rules.religion
    if not rules.religion:
        assert "no religion in this world" in a.last_result


@pytest.mark.parametrize("rules", [ON, OFF])
def test_preaching(rules):
    w, ags = world(rules)
    bid = inject_belief(w, ags[0])
    run_plan(w, ags[0], [{"do": "preach"}])
    heard = any(bid in o.met_beliefs for o in ags[1:])
    assert heard is rules.religion
    assert all(not o.belief for o in ags[1:]) or rules.religion


@pytest.mark.parametrize("rules", [ON, OFF])
def test_reading_a_belief_tablet(rules):
    w, ags = world(rules)
    a = ags[1]
    bid = inject_belief(w, ags[0])
    tb = Tablet(id="tab_t", knowledge=f"belief:{bid}", author=ags[0].id, author_name=ags[0].name, tick=w.tick,
                x=a.x + 1, y=a.y)
    w.tablets[tb.id] = tb
    run_plan(w, a, [{"do": "read"}])
    assert (a.belief == bid) is rules.religion


@pytest.mark.parametrize("rules", [ON, OFF])
def test_writing_down_a_belief(rules):
    w, ags = world(rules)
    a = ags[0]
    inject_belief(w, a)
    a.inventory["clay_tablet"] = 1
    run_plan(w, a, [{"do": "write", "what": "belief"}])
    assert any(t.knowledge.startswith("belief:") for t in w.tablets.values()) is rules.religion


@pytest.mark.parametrize("rules", [ON, OFF])
def test_a_reflection_naming_a_belief(rules):
    w, ags = world(rules)
    parsed = apply_reflection(w, ags[0], json.dumps({"lessons": [], "ambition": "to build", "belief": {
        "name": "The Way", "tenet": "The fire remembers its keepers"}}))
    assert bool(ags[0].belief) is rules.religion and bool(w.beliefs) is rules.religion
    assert bool(parsed.get("belief")) is rules.religion  # (nor is the conviction kept in the record)


@pytest.mark.parametrize("rules", [ON, OFF])
def test_the_holy_book(rules):
    from chits.sim import artifacts

    w, ags = world(rules)
    mood = ags[0].mood
    artifacts.on_inspect(w, ags[0], "holy_book", {})
    assert bool(ags[0].belief) is rules.religion and (ags[0].mood > mood) is rules.religion


@pytest.mark.parametrize("rules", [ON, OFF])
def test_co_believers_and_their_shrine(rules):
    w, ags = world(rules)
    bid = inject_belief(w, ags[0])
    ags[1].belief = bid
    w.beliefs[bid]["followers"].append(ags[1].id)
    shrine(w, ags[0], bid)
    mood, liking = ags[0].mood, ags[0].affinity.get(ags[1].id, 0)
    w._belief_tick()
    assert (ags[0].mood > mood) is rules.religion
    assert (ags[0].affinity.get(ags[1].id, 0) > liking) is rules.religion


# ------------------------------------------------------------------------------ religion: the shrine and prompts

@pytest.mark.parametrize("rules", [ON, OFF])
def test_the_shrine_design_is_never_learned(rules):
    w, ags = world(rules)
    for how in ("taught", "read", "insight", "inspected"):
        a = ags[("taught", "read", "insight", "inspected").index(how)]
        assert w.learned(a, "design:shrine", how) is rules.religion
        assert a.knows_design("shrine") is rules.religion
    run_plan(w, ags[4], [{"do": "build", "what": "shrine"}])
    if not rules.religion:
        assert not any(s.design == "shrine" for s in w.structures.values())


WORDS = ("pray", "preach", "belief", "faith", "shrine", "worship")


def test_prompts_in_a_world_without_religion_say_nothing_of_it():
    w, ags = world(OFF)
    a = ags[0]
    texts = {"system": P.system_prompt(w, a), "compact": P.compact_system_prompt(w, a),
             "reflection": json.dumps(P.reflection_messages(w, a)), "full": json.dumps(P.messages(w, a, "full"))}
    for name, text in texts.items():
        low = text.lower()
        assert not [x for x in WORDS if x in low], (name, [x for x in WORDS if x in low])
    on, _ = world(ON)
    a_on = next(iter(on.agents.values()))
    assert "pray" in P.system_prompt(on, a_on) and "belief" in json.dumps(P.reflection_messages(on, a_on)).lower()


def test_a_model_step_to_pray_or_preach_fails_with_the_simulators_reason():
    w, ags = world(OFF)
    for verb in ("pray", "preach"):
        run_plan(w, ags[0], [{"do": verb}])
        assert ags[0].last_result == f"Could not {verb}: there is no religion in this world, so nobody can {verb}"


def test_a_long_instinct_run_without_religion_has_no_belief_anywhere():
    w = World("A", "A", 42, "direct", 128, 18, rules=OFF)
    for _ in range(20 * 240):
        w.step()
    assert not w.beliefs and not any(a.belief or a.met_beliefs for a in w.agents.values())
    assert not any(a.knows_design("shrine") for a in w.agents.values())
    assert not any(s.design == "shrine" for s in w.structures.values())


# -------------------------------------------------------------------------------------------- the Lab

def _proto(**kw):
    return {"name": "rules", "arms": [{"name": "a"}, {"name": "b"}], "seeds": [3], "days": 1, "size": 64,
            "population": 4, **kw}


def test_a_protocol_keeps_its_fingerprint_until_it_sets_rules(tmp_path):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec, SpecError

    plain = ExperimentSpec.from_dict(_proto())
    assert ExperimentSpec.from_dict(_proto(rules={})).fingerprint() == plain.fingerprint()
    off = ExperimentSpec.from_dict(_proto(rules={"religion": False}))
    assert off.fingerprint() != plain.fingerprint() and off.world_rules() == OFF
    run.start(off, tmp_path / "out")
    man = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert man["world_rules"] == OFF.to_dict() and man["protocol"]["rules"] == {"religion": False}
    run.start(plain, tmp_path / "plain")
    assert json.loads((tmp_path / "plain" / "manifest.json").read_text())["world_rules"] == LEGACY.to_dict()
    with pytest.raises(SpecError):
        ExperimentSpec.from_dict(_proto(rules={"religion": "maybe"}))
    pack = {"id": "shrine", "version": "1", "title": "Shrines (synthetic)", "scope_note": "A made-up pack for a test.",
            "sources": [{"id": "s", "citation": "test", "edition": "1", "licence": "CC0-1.0"}],
            "claims": [], "practices": [{"knowledge": "design:shrine", "sources": ["s"]}], "founders": {"share": 1.0}}
    with pytest.raises(SpecError, match="rule out"):
        ExperimentSpec.from_dict(_proto(rules={"religion": False}, arms=[{"name": "a", "treatment": "shrine"},
                                                                         {"name": "b"}], treatments={"shrine": pack}))


# ----------------------------------------------------------------------------------- the game and its API

def _game(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)


def test_a_new_game_is_made_with_its_rules_and_keeps_them(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    _game(tmp_path, monkeypatch)
    from chits.app import R, app

    with TestClient(app) as c:
        r = R()
        desc = c.get("/api/rules").json()
        assert desc["version"] == RULES_VERSION and "religion" in desc["rules"] and desc["rules"]["religion"]["label"]
        assert c.post("/api/reset", json={"seed": 5, "chits": 4, "size": 64, "rules": {"religion": False}}).status_code == 200
        assert all(w.rules == OFF for w in r.worlds.values()) and r.rules == OFF
        got = c.get("/api/rules").json()
        assert got["current"] == OFF.to_dict() and all(v == OFF.to_dict() for v in got["worlds"].values())
        assert all(w["rules"] == OFF.to_dict() for w in r.manifest()["worlds"].values())
        # a reset that doesn't say keeps the game's rules; a bad set is refused and changes nothing
        assert c.post("/api/reset", json={"seed": 6, "chits": 4, "size": 64}).status_code == 200
        assert all(w.rules == OFF for w in r.worlds.values())
        uuids = {w.uuid for w in r.worlds.values()}
        assert c.post("/api/reset", json={"seed": 7, "rules": {"religion": False, "dragons": True}}).status_code == 400
        assert {w.uuid for w in r.worlds.values()} == uuids
        # a save point brings back its own rules
        sid = r.save_point("off")["id"]
        assert c.post("/api/reset", json={"seed": 8, "chits": 4, "size": 64, "rules": {"religion": True}}).status_code == 200
        assert r.rules == ON
        assert r.restore_point(sid)
        assert r.rules == OFF and all(w.rules == OFF for w in r.worlds.values())


def test_a_save_file_whose_worlds_have_different_rules_is_not_one_game():
    from chits.runtime import Runtime

    a = World("A", "A", 5, "direct", 64, 4).to_dict()
    b = World("B", "B", 5, "direct", 64, 4, rules=OFF).to_dict()
    assert Runtime._match_problem({"A": a, "B": b}) == "they have different world rules"


def test_the_harness_refuses_rules_that_are_not_a_rules_object():
    """Codex on #137: --rules false (or 0, or []) ran with the legacy rules and left them out of the row."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for bad in ("false", "0", "[]", '{"religion": "no"}'):
        r = subprocess.run([sys.executable, str(root / "tools" / "harness" / "run.py"), "3", "--days", "1", "--size",
                            "64", "--chits", "4", "--rules", bad], capture_output=True, text=True)
        assert r.returncode != 0, bad
    ok = subprocess.run([sys.executable, str(root / "tools" / "harness" / "run.py"), "3", "--days", "1", "--size", "64",
                         "--chits", "4", "--rules", '{"religion": false}'], capture_output=True, text=True)
    assert ok.returncode == 0 and json.loads(ok.stdout.strip().splitlines()[-1])["rules"] == {"religion": False}
