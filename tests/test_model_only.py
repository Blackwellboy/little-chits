"""Model-only diagnostic mode: a run where nothing from instinct covers for the model. No instinct menu (the prompt is
forced to the full style), no instinct fallback or filler, and no body reflexes (sim/actions.py): a chit acts only on
its model's plans. What a reflex would have done is counted instead, by kind, to show where the model fails to look
after its chits. Diagnostic only, and off by default everywhere."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from chits import diag
from chits.brain.mind import Mind
from chits.sim import actions
from chits.sim.world import World

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "harness"))
import mindrun  # noqa: E402
from test_lab import lab_fake_llm  # noqa: E402,F401  (the Lab's fake model server, a fixture)

INSTINCT_SOURCES = ("reflex", "filler", "instinct", "fallback", "routine", "duty", "shed")


def _chit(world_seed=2):
    w = World("A", "A", world_seed, "direct", 64, 4)
    return w, next(iter(w.agents.values()))


# ---------------------------------------------------------------------------------------------- off by default
def test_model_only_is_off_by_default_everywhere():
    from chits.lab.spec import ExperimentSpec

    assert actions.REFLEXES is True
    w, _ = _chit()
    assert actions.reflexes_on(w)
    assert Mind(None).model_only is False
    proto = {"name": "x", "arms": [{"name": "a"}, {"name": "b"}], "seeds": [1], "days": 1, "size": 64, "population": 4}
    spec = ExperimentSpec.from_dict(proto)
    assert spec.model_only is False
    # an old protocol keeps its fingerprint: the new option counts only when it is used
    assert spec.fingerprint() == ExperimentSpec.from_dict(dict(proto, model_only=False)).fingerprint()
    assert spec.fingerprint() != ExperimentSpec.from_dict(dict(proto, model_only=True)).fingerprint()
    src = (ROOT / "tools" / "harness" / "run.py").read_text()
    assert '"--model-only", action="store_true"' in src


# ---------------------------------------------------------------------------------------------- reflexes
def test_with_reflexes_off_the_body_does_nothing_but_the_reflex_is_counted():
    w, a = _chit()
    a.plan, a.hunger, a.inventory = [], 5.0, {}
    actions.reflexes(w, a)
    assert a.plan and a.plan[0].get("_reflex")  # (on, as in every mode before: a starving chit goes for food)
    assert not diag.reflex_would_summary(w)["ticks"]
    w, a = _chit()
    w.model_only = True
    assert not actions.reflexes_on(w)
    a.plan, a.hunger, a.inventory = [], 5.0, {}
    rev, emote = a.rev, a.emote
    for _ in range(3):
        actions.reflexes(w, a)
        assert a.plan == []  # nothing put in front of the model's plan
    assert a.rev == rev and a.emote == emote  # no interruption, no face pulled
    rw = diag.reflex_would_summary(w)
    assert rw["onsets_by_kind"] == {"food": 1}  # one need, held for three ticks
    assert sum(rw["ticks"].values()) == 3
    a.hunger, a.energy = 90.0, 3.0  # fed, now exhausted: a new need starts
    actions.reflexes(w, a)
    rw = diag.reflex_would_summary(w)
    assert rw["onsets_by_kind"] == {"food": 1, "sleep": 1} and rw["onsets"]["sleep"] == 1


def test_reflexes_off_leave_a_model_step_untouched():
    w, a = _chit()
    w.model_only = True
    step = {"do": "gather", "what": "wood", "qty": 2, "_origin": "model_generated"}
    a.plan, a.hunger, a.inventory = [step], 5.0, {}
    before = json.dumps(step, sort_keys=True)
    actions.reflexes(w, a)
    assert a.plan == [step] and json.dumps(a.plan[0], sort_keys=True) == before
    assert diag.reflex_would_summary(w)["onsets_by_kind"] == {"food": 1}
    # a step under way keeps lookups in its state (_s); the reflexes looked food up for the hunger margin, on a copy
    step = {"do": "gather", "what": "wood", "qty": 2, "_origin": "model_generated", "_s": {}}
    a.plan, a.hunger = [step], 30.0
    actions.reflexes(w, a)
    assert a.plan == [step] and step["_s"] == {}


def test_the_module_switch_turns_reflexes_off_too(monkeypatch):
    w, a = _chit()
    monkeypatch.setattr(actions, "REFLEXES", False)
    a.plan, a.hunger = [], 5.0
    actions.reflexes(w, a)
    assert a.plan == [] and diag.reflex_would_summary(w)["onsets_by_kind"]


# ---------------------------------------------------------------------------------------------- the mind
def test_a_model_only_mind_never_hands_a_chit_an_instinct_plan():
    w, a = _chit()
    mind = Mind(None)
    mind.model_only = True
    b = mind.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "cascade"})
    mind.assign(w, "m")
    b.healthy = lambda: False  # the model is down: in play, instinct would fall back
    a.plan = []
    mind.hook(w, a)
    assert a.plan == [] and a.plan_source == "waiting"
    assert w.model_only is True  # the mind carries the switch to the body


def test_a_model_only_mind_adopts_the_model_plan_as_written(monkeypatch):
    from chits.brain import mind as M

    added = []

    def tools_first(world, a, steps):  # instinct's "a pick before the ore", watched
        added.append(1)
        return [{"do": "craft", "what": "pick"}] + steps

    monkeypatch.setattr(M, "tools_first", tools_first)
    for model_only, want in ((True, ["gather"]), (False, ["craft", "gather"])):
        w, a = _chit()
        mind = Mind(None)
        mind.model_only = model_only
        mind.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1"})
        mind.assign(w, "m")
        a.plan, a.pending_plan = [], {"steps": [{"do": "gather", "what": "ore", "qty": 2}], "goal": "ore"}
        mind.hook(w, a)
        assert [s["do"] for s in a.plan] == want
    assert added == [1]  # only the play mind asked instinct to add to the model's plan


# ---------------------------------------------------------------------------------------------- a whole run
@pytest.mark.parametrize("bad_rate", [0.0, 0.15])
def test_a_model_only_run_has_no_menu_no_fallback_and_no_reflex_steps(bad_rate):
    w, p, mp, low, r = mindrun.run_world(3, 1, size=64, chits=6, style="cascade", bad_rate=bad_rate, model_only=True)
    assert r["model_only"] is True
    src = r["steps_by_source"]
    assert not any(src.get(k) for k in INSTINCT_SOURCES), src
    assert src.get("model_generated", 0) > 0 and not src.get("model_selected")
    # (a vote is still a letter: the ballot's options are the village's, not instinct's plans)
    assert not any(k in r["decisions"] for k in ("style:choose", "style:cascade", "style:cascade-full"))
    assert r["decisions"].get("style:full", 0) > 0
    assert set(r["plans"]) <= {"model"}, r["plans"]
    rw = r["reflex_would"]
    assert sum(rw["onsets_by_kind"].values()) > 0 and rw["ticks"]


def test_without_model_only_the_same_run_still_has_reflexes_and_the_menu():
    _, _, _, _, r = mindrun.run_world(3, 1, size=64, chits=6, style="cascade", bad_rate=0.0)
    assert r["model_only"] is False
    assert r["steps_by_source"].get("reflex", 0) > 0 and r["decisions"].get("style:choose", 0) > 0
    assert not r["reflex_would"]["ticks"]  # reflexes on: nothing left undone to count


def test_run_py_model_only_needs_a_mind_and_records_itself():
    cmd = [sys.executable, str(ROOT / "tools" / "harness" / "run.py"), "4", "--days", "1", "--size", "64", "--chits",
           "6", "--mind", "scripted", "--model-only"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    row = json.loads(r.stdout.strip().splitlines()[-1])
    assert row["mind"]["model_only"] is True and row["mind"]["style"] == "full"
    assert "reflex" not in row["mind"]["steps_by_source"]
    assert row["mind"]["reflex_would"]["onsets_by_kind"]
    bare = subprocess.run(cmd[:-3] + ["--model-only"], capture_output=True, text=True, timeout=120)
    assert bare.returncode != 0 and "--mind" in bare.stderr


# ---------------------------------------------------------------------------------------------- the Lab
def test_a_lab_protocol_can_ask_for_model_only_and_the_manifest_says_so(tmp_path):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "diag", "arms": [{"name": "a"}, {"name": "b", "culture": "stigmergy"}],
                                     "seeds": [3], "days": 1, "size": 64, "population": 4, "model_only": True})
    run.run(spec, tmp_path / "out")
    man = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert man["model_only"] is True and man["protocol"]["model_only"] is True
    assert "diagnostic" in man["model_only_note"]
    for r in run.results(tmp_path / "out"):
        assert r["model_only"]["reflexes"] is False
        assert sum(r["model_only"]["reflex_would"]["onsets_by_kind"].values()) > 0
    plain = ExperimentSpec.from_dict({"name": "x", "arms": [{"name": "a"}, {"name": "b"}], "seeds": [3], "days": 1,
                                      "size": 64, "population": 4})
    run.run(plain, tmp_path / "plain")
    man = json.loads((tmp_path / "plain" / "manifest.json").read_text())
    assert man["model_only"] is False
    assert all("model_only" not in r for r in run.results(tmp_path / "plain"))


def test_a_lab_model_arm_under_model_only_takes_every_step_from_its_model(monkeypatch, tmp_path, lab_fake_llm):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec

    brain = {"id": "fake", "label": "Fake", "base_url": lab_fake_llm, "model": "fake", "max_concurrency": 4,
             "max_tokens": 120, "prompt_style": "cascade"}
    proto = {"name": "diag", "arms": [{"name": "model", "brain": "fake"}, {"name": "baseline"}], "allow_models": True,
             "brains": {"fake": brain}, "seeds": [7], "days": 1, "size": 64, "population": 3, "model_only": True}
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    run.run(ExperimentSpec.from_dict(proto), tmp_path / "run", jobs=1)
    model = next(x for x in run.results(tmp_path / "run") if x.get("compute"))
    assert model["compute"]["requests"] > 0
    assert model["final"]["model_step_share"] == 1.0  # no reflex, no instinct step: the model's plans only
    assert model["model_only"]["reflexes"] is False
    calls = [json.loads(line) for line in (tmp_path / "run" / "runs").glob("7_*/tape.jsonl").__next__().open()]
    assert calls and not any("YOUR OPTIONS" in json.dumps(c) for c in calls)  # never instinct's menu


# ---------------------------------------------------------------------------------------------- the live game
def test_the_game_offers_model_only_as_a_play_toggle_off_by_default(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import app

    with TestClient(app) as c:
        assert c.get("/api/brains").json()["model_only"] is False
        r = c.post("/api/model-only", json={"on": True})
        assert r.status_code == 200 and r.json()["model_only"] is True
        assert c.get("/api/brains").json()["model_only"] is True
        warns = c.get("/api/diagnostics").json()["warnings"]
        assert any("MODEL-ONLY" in w and "diagnostic" in w for w in warns)
        assert c.post("/api/model-only", json={"on": False}).json()["model_only"] is False
        assert not any("MODEL-ONLY" in w for w in c.get("/api/diagnostics").json()["warnings"])
        cfg = (tmp_path / "brains.json")
        assert not cfg.exists() or "model_only" not in cfg.read_text()  # never saved: a restart turns it off


def test_an_experiment_run_never_runs_model_only(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.app import R, app

    with TestClient(app) as c:
        assert c.post("/api/model-only", json={"on": True}).status_code == 200
        assert c.post("/api/reset", json={"contract": "experiment"}).status_code == 200
        assert R().mind.model_only is False  # an experiment starts with it off ...
        assert c.post("/api/model-only", json={"on": True}).status_code == 409  # ... and can't turn it on


def test_switching_model_only_on_mid_game_drops_instinct_plans_and_stales_menu_requests():
    """Codex P2 on #118: turned on mid-game, the flag alone let a running instinct plan finish and a choose request
    already in flight come back and be adopted. Neither may act after the switch."""
    from chits.runtime import Runtime

    w, a = _chit()
    b_ = next(x for x in w.agents.values() if x is not a)
    mind = Mind(None)
    mind.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "choose"})
    mind.assign(w, "m")
    # a: running an instinct plan, with a reflex in front of it
    a.plan = [{"do": "eat", "_reflex": True}, {"do": "gather", "what": "wood", "_origin": "instinct"}]
    # b: a menu choice is in flight (asked before the switch, answered after it)
    b_.plan = [{"do": "gather", "what": "stone", "_origin": "model_generated", "_decision_id": "r0"}]
    rec = {"request_id": "r1", "style": "choose", "parse": "choice", "rev_requested": b_.rev, "tick_requested": w.tick,
           "world": w.id, "agent": b_.id}
    b_.__dict__["_decision"] = rec
    b_.thinking = True
    rt = Runtime.__new__(Runtime)
    rt.mind, rt.worlds, rt.forks = mind, {w.id: w}, {}
    rt.set_model_only(True)
    assert a.plan == []  # no instinct or reflex step survives the switch
    assert b_.plan == [{"do": "gather", "what": "stone", "_origin": "model_generated", "_decision_id": "r0"}]  # its own
    d = diag.of(w)
    assert d.model_only_since == w.tick and d.model_only_dropped == 2
    # the choice comes back: it is stale, never adopted, even if it was only sent after the switch
    rec["rev_requested"] = b_.rev
    b_.thinking, b_.plan = False, []
    b_.pending_plan = {"steps": [{"do": "gather", "what": "clay"}], "goal": "clay"}
    mind.hook(w, b_)
    assert not any(s.get("what") == "clay" for s in b_.plan) and rec.get("outcome") == "stale"
    assert all(str(s.get("_origin")).startswith("model") for s in b_.plan)  # and no instinct plan in its place
    rt.set_model_only(False)
    assert diag.of(w).model_only_since is None


def _game(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)


def test_every_world_put_in_place_under_model_only_is_sanitized_and_a_new_game_turns_it_off(tmp_path, monkeypatch):
    """Codex P2 on #118: a save point restored while model-only was on came back with its saved instinct, filler and
    reflex steps (model_only isn't saved, and the mind only restored the flag). Every way a world is put in place
    runs the same sanitizing: a restore (rewinds and loaded save files go through it too) and a fork."""
    from fastapi.testclient import TestClient

    _game(tmp_path, monkeypatch)
    from chits.app import R, app

    instinct = [{"do": "eat", "_reflex": True}, {"do": "gather", "what": "wood", "_origin": "instinct"},
                {"do": "rest", "_filler": True, "_origin": "filler"}]
    with TestClient(app) as c:
        r = R()
        for w in r.worlds.values():
            for a in w.agents.values():
                a.plan = [dict(s) for s in instinct]
        sid = r.save_point("before")["id"]
        assert c.post("/api/model-only", json={"on": True}).status_code == 200
        assert r.restore_point(sid)
        for w in r.worlds.values():
            assert w.model_only is True
            assert all(a.plan == [] for a in w.agents.values()), "saved instinct steps came back"
            assert diag.of(w).model_only_since == w.tick and diag.of(w).model_only_dropped == 3 * len(w.agents)
        wid = next(iter(r.worlds))
        next(iter(r.worlds[wid].agents.values())).plan = [dict(s) for s in instinct]  # (as if left by a stale tick)
        f = r.fork(wid)
        fw = r.forks[f["id"]]["world"]
        assert fw.model_only is True and all(a.plan == [] for a in fw.agents.values())
        # a new game is a new match: the diagnostic doesn't carry over into it unnoticed (as an experiment, it's off)
        assert c.post("/api/reset", json={"seed": 7, "chits": 4, "size": 64}).status_code == 200
        assert r.mind.model_only is False and not any(getattr(w, "model_only", False) for w in r.worlds.values())
        assert c.get("/api/brains").json()["model_only"] is False


def test_a_chit_that_becomes_model_driven_under_model_only_drops_its_instinct_plan():
    """Codex P2 on #118: model-only on while a world ran on instinct, then a model assigned to it. Mind.assign kept
    the chits' instinct plans, and nothing cleaned them (the switch was already on). Whenever a chit becomes
    model-driven under model-only (assigned a model, or arriving where a model drives it) it is cleaned."""
    from chits.runtime import Runtime

    w, a = _chit()
    others = [x for x in w.agents.values() if x is not a]
    mind = Mind(None)
    mind.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1"})
    rt = Runtime.__new__(Runtime)
    rt.mind, rt.worlds, rt.forks = mind, {w.id: w}, {}
    rt.set_model_only(True)  # the world is still on instinct: its chits plan on instinct, as is theirs to do
    instinct = [{"do": "gather", "what": "wood", "_origin": "instinct"}, {"do": "rest", "_filler": True}]
    for x in w.agents.values():
        x.plan = [dict(s) for s in instinct]
    rev = a.rev
    mind.assign(w, "m", [a.id])  # one chit gets the model, through the API's path
    assert a.plan == [] and a.rev > rev
    assert all(len(x.plan) == 2 for x in others)  # still on instinct: their plans are their own mind's
    assert diag.of(w).model_only_dropped == 2
    # a chit made model-driven any other way (a voyager taking its new home's brain) is cleaned before it acts
    b_ = others[0]
    b_.brain = "m"
    mind.hook(w, b_)
    assert not any(s.get("_origin") == "instinct" or s.get("_filler") for s in b_.plan)
    assert diag.of(w).model_only_dropped == 4
    a.plan = [{"do": "gather", "what": "stone", "_origin": "model_generated"}]
    mind.hook(w, a)  # already cleaned under this brain: its own plan stands
    assert a.plan[0]["what"] == "stone"


def test_one_uninterrupted_need_is_one_onset_even_when_its_first_verb_changes():
    """Codex P2 on #118: onsets were counted on verb changes, so one food need that went from gather or explore to
    eat counted twice. An onset is a kind starting to fire."""
    w, a = _chit()
    for verb in ("gather", "gather", "explore", "eat", "eat"):
        diag.reflex_would(w, a, verb)
    diag.reflex_would(w, a, None)  # fed
    diag.reflex_would(w, a, "eat")  # hungry again: a second need
    diag.reflex_would(w, a, "sleep")  # food need over, a sleep need starts
    rw = diag.reflex_would_summary(w)
    assert rw["onsets_by_kind"] == {"food": 2, "sleep": 1}
    assert rw["onsets"] == {"eat": 1, "gather": 1, "sleep": 1}  # by the verb each need began with
    assert rw["ticks"] == {"eat": 3, "explore": 1, "gather": 2, "sleep": 1}
