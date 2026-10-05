"""World rules beyond religion (sim/rules.py, docs/WORLD_RULES.md): invention, library hints, protecting endangered
knowledge, the storyteller and wanderers. Each is tested in pairs: on, the path is reached; off, it is closed."""

import json

import pytest

from chits.brain import civic
from chits.brain import inventor as IV
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import actions, lore, research
from chits.sim.rules import PRESETS, RULES, RULES_VERSION, WorldRules, describe
from chits.sim.world import World


def world(rules, n=2, seed=3, brain="m"):
    w = World("A", "A", seed, "direct", 64, n, rules=rules)
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = o.health = o.mood = 95.0
        o.inventory.clear()
        o.plan = []
        o.brain = brain
    w.tick = 240 * 2 + 120
    return w, next(iter(w.agents.values()))


ON = WorldRules()


def off(rule):
    return WorldRules(**{rule: False})


# -------------------------------------------------------------------------------------------- invention

@pytest.mark.parametrize("rules", [ON, off("invention")])
def test_invention(rules):
    w, a = world(rules)
    a.inventory.update({"fiber": 2, "wood": 1})
    assert (IV.option(w, a) is not None) is rules.invention
    assert any(any(s.get("do") == "invent" for s in o["steps"]) for o in Instinct().options(w, a)) is rules.invention
    assert ('{"do":"invent"' in P.system_prompt(w, a)) is rules.invention
    a.plan = [{"do": "invent", "with": ["fiber", "wood"], "name": "Net", "purpose": "to catch fish"}]
    for _ in range(300):
        w.step()
        if not a.plan:
            break
    assert bool(w.inventions) is rules.invention
    if not rules.invention:
        assert a.last_result.endswith(": nobody in this world invents new things (they can still experiment)")


def test_experimenting_stays_when_invention_is_off():
    w, a = world(off("invention"))
    assert '{"do":"experiment"' in P.system_prompt(w, a) and w.rules.allows_verb("experiment")


# ------------------------------------------------------------------------------------------ library hints

@pytest.mark.parametrize("rules", [ON, off("library_hints")])
def test_library_hints(rules):
    w, a = world(rules)
    research.add_insight(w, a, 3.0)  # (a small study's worth: on, it builds towards the village's next idea)
    assert (w.civic.get("insight", 0.0) > 0) is rules.library_hints
    if not rules.library_hints:
        assert research.add_insight(w, a, 10_000.0) is None and not w.civic.get("hints")
        assert w.civic.get("insight", 0.0) == 0.0  # (no insight piles up towards a hint either)
        assert not research.scene_lines(w, a)


# ---------------------------------------------------------------------------------- endangered knowledge

def _old_keeper(rules):
    w, a = world(rules, n=4, seed=5, brain="instinct")
    for o in w.agents.values():
        o.x, o.y = a.x + (o is not a), a.y
    a.learn("recipe:cord", "discovered", w.tick)
    w.first["recipe:cord"] = {"tick": 0, "by": a.id, "name": a.name}
    w.tick = a.born + int(lore.OLD * a.lifespan) + 1
    return w, a


@pytest.mark.parametrize("rules", [ON, off("lore_rescue")])
def test_protecting_endangered_knowledge(rules):
    w, a = _old_keeper(rules)
    import random

    assert (lore.scene_line(w, a) is not None) is rules.lore_rescue
    assert bool(civic.lore_options(Instinct(), w, a, random.Random(1))) is rules.lore_rescue
    # what happens to it is still recorded either way: it is the world's history, not a nudge
    lore.daily(w)
    assert any(e.kind == "last_keeper" for e in w.events)
    w.kill(a, "old age")
    assert any(e.kind == "forgotten" for e in w.events)


# ------------------------------------------------------------------------------ the storyteller, wanderers

@pytest.mark.parametrize("rule", ["storyteller", "wanderers"])
@pytest.mark.parametrize("on", [True, False])
def test_play_mode_storyteller_and_wanderers(tmp_path, monkeypatch, rule, on):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import Runtime
    from chits.sim import storyteller
    from chits.sim.world import World as W

    calls = []
    monkeypatch.setattr(storyteller, "daily", lambda w: calls.append(("storyteller", w.day)))
    monkeypatch.setattr(W, "welcome_wanderer", lambda self: calls.append(("wanderers", self.day)))
    rt = Runtime(tmp_path)
    rt.reset(seed=5, chits=4, size=64, mode="single", rules={rule: on})
    rt.step_worlds(240 * 6)
    assert any(c[0] == rule for c in calls) is on


# --------------------------------------------------------------------------------------- record, presets

def test_a_version_1_record_comes_forward_with_the_new_rules_at_their_defaults():
    v1 = {"version": 1, "religion": False}
    assert WorldRules.from_dict(v1) == WorldRules(religion=False)
    assert RULES_VERSION == 2 and WorldRules().to_dict() == {"version": 2, **{k: True for k in RULES}}


def test_every_rule_and_preset_is_described_and_valid():
    d = describe()
    for k, spec in d["rules"].items():
        assert spec["label"] and spec["off"] and spec["default"] is True, k
    assert set(d["presets"]) == {"standard", "model_led", "research_clean", "sandbox"}
    for name, p in PRESETS.items():
        WorldRules.from_dict(p["rules"])  # (valid)
        assert p["label"] and p["about"] and isinstance(p["model_led"], bool), name
    clean = WorldRules.from_dict(PRESETS["research_clean"]["rules"])
    assert not (clean.religion or clean.library_hints or clean.lore_rescue or clean.storyteller or clean.wanderers)
    assert clean.invention and PRESETS["research_clean"]["model_led"]  # (inventing is a chit's own act: it stays)


@pytest.mark.parametrize("rules", [ON, off("invention")])
def test_no_prompt_mentions_inventing_when_invention_is_off(rules):
    """Codex on #143: the compact prompt and the stale-village nudge still offered inventing."""
    w, a = world(rules)
    texts = [P.compact_system_prompt(w, a), P.system_prompt(w, a), json.dumps(P.messages(w, a, "compact")),
             json.dumps(P.messages(w, a, "full"))]
    assert any("invent" in x.lower() for x in texts) is rules.invention


@pytest.mark.parametrize("rules", [ON, off("library_hints")])
def test_study_says_what_it_gives_when_hints_are_off(rules):
    """Codex on #143: with hints off, study still promised an idea, in the guide and in its own result."""
    w, a = world(rules)
    guide = P.system_prompt(w, a)
    assert ("gives the village's scholars an idea" in guide) is rules.library_hints
    s = {}
    research.add_insight(w, a, 1.0)
    from chits.sim.actions import DONE

    lib = w.place_site("library", *w.find_site("library", a.x + 2, a.y, 10), a)
    w.complete_structure(lib, a)
    from chits.sim.world import Tablet

    tb = Tablet(id="t1", knowledge="recipe:cord", author=a.id, author_name=a.name, tick=w.tick, x=lib.x, y=lib.y,
                in_structure=lib.id)
    w.tablets[tb.id] = tb
    lib.shelf.append(tb.id)
    a.x, a.y = lib.x, lib.y
    res = None
    for _ in range(200):
        res = research.do_study(w, a, {"do": "study"}, s)
        if res != "running":
            break
    assert res == DONE
    assert ("no idea comes of study here" in s["note"]) is (not rules.library_hints)


@pytest.mark.parametrize("rules", [ON, off("invention")])
def test_a_stale_village_is_nudged_to_invent_only_where_inventing_exists(monkeypatch, rules):
    w, a = world(rules)
    monkeypatch.setattr(P, "stale_days", lambda world: 99)
    home = w.place_site("hut", *w.find_site("hut", a.x + 2, a.y, 10), a)
    w.complete_structure(home, a)
    a.home, a.hunger = home.id, 90.0
    w.tick = 240 * 3 + 120  # (midday)
    text = P.scene(w, a)
    assert "good time to experiment" in text
    assert ("invent something" in text) is rules.invention
