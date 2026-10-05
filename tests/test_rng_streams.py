"""Streams per system, per chit and per tick (world.RNG_STREAMS): one change moves only its own draws."""

import json

import pytest

from chits.brain import builder as BI
from chits.brain import civic
from chits.brain.instinct import Instinct
from chits.sim import world as W
from chits.sim.world import World


@pytest.fixture
def streams(monkeypatch):
    def set_(on):
        monkeypatch.setattr(W, "RNG_STREAMS", on)
    return set_


def _first_draws(on, monkeypatch, extra_builder_draw):
    """Plan once for every chit, recording the first number the experiment and the village's projects draw."""
    monkeypatch.setattr(W, "RNG_STREAMS", on)
    w = World("A", "A", 42, "direct", 64, 6)
    for _ in range(3):
        w.step()
    seen = []
    exp, ext, opts = Instinct._experiment, civic.extend, BI.building_options

    def rec_exp(self, world, a, rng):
        seen.append(("exp", a.id, rng.random()))
        return exp(self, world, a, rng)

    def rec_ext(ins, world, a, rng, o):
        seen.append(("civic", a.id, rng.random()))
        return ext(ins, world, a, rng, o)

    def more(world, a, rng):
        if extra_builder_draw:
            rng.random()  # the builder rolls once more: a change to the builder alone
        out = opts(world, a, rng)
        seen.append(("built", a.id, [o["goal"] for _, o in out]))
        return out

    monkeypatch.setattr(Instinct, "_experiment", rec_exp)
    monkeypatch.setattr(civic, "extend", rec_ext)
    monkeypatch.setattr(BI, "building_options", more)
    ins = Instinct()
    for a in list(w.agents.values()):
        a.job = ""  # (a guard can stop before the options)
        p = ins._progress(w, a, w.stream("instinct:_progress:0", a.id) if on else __import__("random").Random(a.id))
        seen.append(("pick", a.id, p and p["goal"]))
    monkeypatch.undo()
    return [x for x in seen if x[0] == "civic"], [x for x in seen if x[0] != "civic"]


def test_an_extra_draw_by_the_builder_leaves_the_rest_of_a_plan_alone(monkeypatch):
    civ_a, rest_a = _first_draws(True, monkeypatch, False)
    civ_b, rest_b = _first_draws(True, monkeypatch, True)
    assert civ_a and any(x[0] == "exp" for x in rest_a)
    # the builder offered the same either way, so the final pick, the experiment and the projects match too
    assert (civ_a, rest_a) == (civ_b, rest_b)
    # off, the plan shares one stream: the same extra draw moves the projects' (the test can tell)
    civ_c, _ = _first_draws(False, monkeypatch, False)
    civ_d, _ = _first_draws(False, monkeypatch, True)
    assert civ_c != civ_d


def test_each_chit_and_each_tick_has_its_own_stream(streams):
    streams(True)
    a, b = World("A", "A", 7, "direct", 64, 0), World("A", "A", 7, "direct", 64, 0)
    for _ in range(5):
        a.rng_for("agents", "c1").random()  # one chit's extra luck in one world only
    assert a.rng_for("agents", "c2").random() == b.rng_for("agents", "c2").random()
    assert b.rng_for("agents", "c1").random() != b.rng_for("agents", "c3").random()  # (not the same stream twice)
    first = b.rng_for("agents", "c4").random()
    assert a.rng_for("weather").random() == b.rng_for("weather").random()
    a.step()
    b.step()
    assert a.rng_for("agents", "c1").random() == b.rng_for("agents", "c1").random()  # (the next tick is clean)
    assert b.rng_for("agents", "c4").random() != first  # (a new tick, new numbers)
    assert a.rng_for("births", "c1") is a.rng_for("births", "c1")
    assert a.rng_for("births", "c1") is not a.rng_for("births", "c2")


def test_the_switch_brings_back_the_running_streams(streams):
    """Off, every draw is the old one (tests/identity_runner.py turns it off); on, the draws are new ones."""
    streams(False)
    old = World("A", "A", 7, "direct", 64, 0)
    want = [old.rng_for("agents").random() for _ in range(3)]
    old2 = World("A", "A", 7, "direct", 64, 0)
    assert [old2.rng_for("agents", "c1").random() for _ in range(3)] == want  # (the key means nothing off)
    streams(True)
    new = World("A", "A", 7, "direct", 64, 0)
    assert [new.rng_for("agents").random() for _ in range(3)] != want
    assert [new.rng_for("agents", "c1").random() for _ in range(3)] != want


def test_a_save_between_draws_restores_this_ticks_streams(streams):
    streams(True)
    w = World("A", "A", 11, "direct", 64, 3)
    for _ in range(2):
        w.step()
    w.rng_for("agents", "few").random()
    for _ in range(400):  # past one table of 624 words: saved whole
        w.rng_for("agents", "many").random()
    w.rng_for("misc", "gauss").gauss(0, 1)  # (one normal kept back for the next call)
    snap = json.loads(json.dumps(w.to_dict()))
    kinds = {n + ":" + str(k): len(st) for n, k, st in snap["rng_tick"]["streams"]}
    assert kinds["agents:few"] == 2 and kinds["agents:many"] == 3
    x = World.from_dict(snap)
    for name, key in (("agents", "few"), ("agents", "many"), ("agents", "fresh"), ("weather", None)):
        assert x.rng_for(name, key).random() == w.rng_for(name, key).random(), (name, key)
    assert x.rng_for("misc", "gauss").gauss(0, 1) == w.rng_for("misc", "gauss").gauss(0, 1)
    x.step()
    w.step()
    assert x.rng_for("agents", "few").random() == w.rng_for("agents", "few").random()


def test_saves_without_tick_streams_still_load(streams):
    streams(True)
    w = World("A", "A", 11, "direct", 64, 3)
    w.step()
    w.rng_for("agents", "c").random()
    snap = json.loads(json.dumps(w.to_dict()))
    snap.pop("rng_tick")
    x = World.from_dict(snap)
    assert x.rng_for("agents", "c").random() == World.from_dict(snap).rng_for("agents", "c").random()
    streams(False)
    assert "rng_tick" not in World("A", "A", 11, "direct", 64, 3).to_dict()  # (off: the old save shape)


def test_each_part_of_a_plan_draws_from_its_own_stream(monkeypatch):
    """Survival rolling one more number leaves what the chores and progress draw as they were (streams on)."""
    def draws(on, extra):
        monkeypatch.setattr(W, "RNG_STREAMS", on)
        w = World("A", "A", 5, "direct", 64, 4)
        w.step()
        seen = []
        prog = Instinct._progress

        def survive(self, world, a, rng):
            if extra:
                rng.random()
            return rng.random() and None  # (and offers nothing, so every plan gets as far as progress)

        def progress(self, world, a, rng):
            seen.append((a.id, rng.random()))
            return prog(self, world, a, rng)

        monkeypatch.setattr(Instinct, "_survive", survive)
        monkeypatch.setattr(Instinct, "_progress", progress)
        for part in ("_declutter", "_shelter", "_maintain", "_communal"):  # each rolls once and offers nothing
            monkeypatch.setattr(Instinct, part, lambda self, world, a, rng: rng.random() and None)
        ins = Instinct()
        for a in w.agents.values():
            ins.plan(w, a)
        monkeypatch.undo()
        return seen

    assert draws(True, False) and draws(True, False) == draws(True, True)
    assert draws(False, False) != draws(False, True)  # (off: one stream for the whole plan, as it was)


def test_each_animal_moves_by_its_own_luck(streams):
    """One animal fewer leaves where every other animal wanders (streams on); off, one stream moves them all, so the
    first one's rolls missing shifts every later one's."""
    from chits.sim import animals as AN

    def moved(on, extra):
        streams(on)
        w = World("A", "A", 13, "direct", 96, 0)
        w.step()
        first = next(iter(w.animals))  # (the first to move)
        if extra:
            w.animals.pop(first)
        AN.move(w)
        return {k: (a["x"], a["y"]) for k, a in w.animals.items() if k != first}

    assert len(moved(True, False)) >= 4
    assert moved(True, False) == moved(True, True)
    assert moved(False, False) != moved(False, True)  # (the test can tell)


# ---------------------------------------------------------------- the scheme a save carries (rng_scheme)

def _carry_on(w, ticks=240):
    for _ in range(ticks):
        w.step()
    return json.dumps(w.to_dict(), sort_keys=True, default=str)


def test_a_save_says_which_scheme_made_it(streams):
    streams(True)
    on = World("A", "A", 11, "direct", 64, 3)
    assert on.to_dict()["rng_scheme"] == 3 == W.RNG_STREAMED
    streams(False)
    off = World("A", "A", 11, "direct", 64, 3)
    snap = off.to_dict()
    assert snap["rng_scheme"] == 2 and "rng_tick" not in snap  # (streams off: the save is the old one exactly)


@pytest.mark.parametrize("made_on,loaded_on", [(False, True), (True, False)])
def test_a_loaded_world_goes_on_with_the_scheme_it_was_saved_with(streams, made_on, loaded_on):
    """A scheme-2 save loaded with streams on keeps its running streams, and a scheme-3 save loaded with them off
    keeps its streams per tick: either way it carries on exactly as the world it was taken from. (Refusing a
    scheme-3 save while streams are off would only stop tools such as the identity runner opening it; switching it
    to the other scheme is the silent change of history this guards against.)"""
    streams(made_on)
    w = World("A", "A", 11, "direct", 64, 6)
    for _ in range(300):
        w.step()
    snap = json.loads(json.dumps(w.to_dict()))
    streams(loaded_on)
    back = World.from_dict(snap)
    assert back.rng_scheme == (3 if made_on else 2) and back.to_dict()["rng_scheme"] == snap["rng_scheme"]
    assert _carry_on(back) == _carry_on(w)


def test_saves_from_older_schemes_still_load_and_unknown_ones_are_refused(streams):
    streams(True)
    snap = json.loads(json.dumps(World("A", "A", 11, "direct", 64, 3).to_dict()))
    for old in (1, 2):
        assert World.from_dict({**snap, "rng_scheme": old}).rng_scheme == 2
    with pytest.raises(ValueError, match="unsupported RNG scheme"):
        World.from_dict({**snap, "rng_scheme": 4})


def test_a_lab_directory_is_not_resumed_under_another_scheme(streams, tmp_path):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec, SpecError

    spec = ExperimentSpec.from_dict({"name": "scheme", "arms": [{"name": "a"}, {"name": "b", "culture": "stigmergy"}],
                                     "seeds": [1], "days": 1, "size": 64, "population": 4})
    streams(True)
    run.start(spec, tmp_path, "abc")
    assert json.loads((tmp_path / "manifest.json").read_text())["rng_scheme"] == 3
    run.start(spec, tmp_path, "abc")  # (the same scheme resumes)
    streams(False)
    with pytest.raises(SpecError, match="random-number scheme 3"):
        run.start(spec, tmp_path, "abc")
