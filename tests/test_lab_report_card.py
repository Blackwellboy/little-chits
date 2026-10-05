"""What the Lab records for the model programme's report card (docs/research/model-programme.md): preventable deaths,
judged as they happen; and a declared mode for models whose makers ask for their own sampling."""

import json
import sys
from pathlib import Path

import pytest

from chits.lab import autopsy
from chits.sim.world import World

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "harness"))


def _starve(with_food: bool):
    w = World("A", "A", 3, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    pile = w.place_site("stockpile", *w.find_site("stockpile", a.x + 4, a.y, 10), a)
    w.complete_structure(pile, a)
    if with_food:
        pile.storage["berries"] = 5
    return w, a


@pytest.mark.parametrize("with_food", [True, False])
def test_a_starvation_is_judged_as_the_harness_probe_judges_it(with_food):
    """The Lab's rule is the harness's (tools/harness/probe.py), at the moment of death."""
    from probe import Probe

    w, a = _starve(with_food)
    found = autopsy.attach(w)
    p = Probe(w)
    with p:
        w.kill(a, "starvation")  # (it says so itself: a death event with its cause)
    assert [s["preventable"] for s in found] == [with_food]
    assert [s["preventable"] for s in p.starved] == [with_food]
    assert autopsy.count(w) == int(with_food)


def test_lab_results_count_preventable_deaths(tmp_path):
    from chits.lab import run
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "card", "arms": [{"name": "a"}, {"name": "b"}], "seeds": [3],
                                     "days": 1, "size": 64, "population": 4})
    run.run(spec, tmp_path / "out")
    for p in (tmp_path / "out" / "runs").glob("*/result.json"):
        f = json.loads(p.read_text())["final"]
        assert f["preventable"] == 0 and f["preventable"] <= f["starved"]
    from chits.lab import extract

    assert extract.row(World("A", "A", 3, "direct", 64, 2))["preventable"] is None  # (not watched: not 0)


def test_native_sampling_is_declared_and_only_sampling_may_differ():
    from chits.lab.spec import ExperimentSpec, SpecError

    url = "http://127.0.0.1:9/v1"
    a = {"id": "a", "base_url": url, "model": "ministral", "temperature": 0.05, "max_tokens": 120}
    b = {"id": "b", "base_url": url, "model": "granite", "temperature": 1.0, "extra_body": {"top_p": 0.95},
         "max_tokens": 120}
    proto = {"name": "native", "allow_models": True, "seeds": [1], "days": 1, "size": 64, "population": 3,
             "arms": [{"name": "m", "brain": "a"}, {"name": "g", "brain": "b"}], "brains": {"a": a, "b": b}}
    with pytest.raises(SpecError, match="temperature"):
        ExperimentSpec.from_dict(proto)
    spec = ExperimentSpec.from_dict(dict(proto, sampling="native"))
    assert spec.fingerprint() != ExperimentSpec.from_dict(dict(proto, brains={"a": a, "b": dict(a, id="b")})).fingerprint()
    with pytest.raises(SpecError, match="max_tokens"):  # (only sampling: tokens, timeouts and the rest still match)
        ExperimentSpec.from_dict(dict(proto, sampling="native", brains={"a": a, "b": dict(b, max_tokens=600)}))
    with pytest.raises(SpecError):
        ExperimentSpec.from_dict(dict(proto, sampling="whatever"))
    # an older protocol keeps its fingerprint
    root = Path(__file__).resolve().parents[1]
    assert ExperimentSpec.from_dict(json.loads((root / "docs/protocols/jevk5-vs-gemma.json").read_text())).fingerprint()         == "6fc60a4faaa15742"


def test_food_across_the_water_does_not_make_a_starvation_preventable(monkeypatch):
    w, a = _starve(True)
    found = autopsy.attach(w)
    monkeypatch.setattr(w, "same_land", lambda x, y: False)  # (the store is on another shore)
    w.kill(a, "starvation")
    assert [s["preventable"] for s in found] == [False]


def test_an_unmeasured_metric_is_left_out_of_the_report_never_read_as_zero(tmp_path):
    """Codex on #151: a run recorded before `preventable` existed was averaged in as 0."""
    from chits.lab import report, run
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "card", "arms": [{"name": "a"}, {"name": "b"}], "seeds": [3, 4],
                                     "days": 1, "size": 64, "population": 4})
    run.run(spec, tmp_path / "out")
    for p in (tmp_path / "out" / "runs").glob("*/result.json"):  # (as if every run were from before the field)
        r = json.loads(p.read_text())
        r["final"].pop("preventable")
        p.write_text(json.dumps(r))
    text = report.write_pack(tmp_path / "out").read_text()
    row = next(l for l in text.splitlines() if l.startswith("| preventable"))
    assert "0.00" not in row, row  # (nothing measured: no zero mean)


def test_native_sampling_varies_samplers_only():
    from chits.lab.spec import ExperimentSpec, SpecError

    url = "http://127.0.0.1:9/v1"
    a = {"id": "a", "base_url": url, "model": "m1", "temperature": 0.05, "max_tokens": 120,
         "extra_body": {"top_k": 20, "seed": 1}}
    proto = {"name": "native", "allow_models": True, "seeds": [1], "days": 1, "size": 64, "population": 3,
             "sampling": "native", "arms": [{"name": "x", "brain": "a"}, {"name": "y", "brain": "b"}]}
    ok = dict(a, id="b", model="m2", temperature=1.0, extra_body={"top_k": 64, "top_p": 0.95, "seed": 1})
    ExperimentSpec.from_dict(dict(proto, brains={"a": a, "b": ok}))
    sneaky = dict(ok, extra_body={"top_k": 64, "seed": 7})  # (a seed isn't a sampler)
    with pytest.raises(SpecError, match="seed"):
        ExperimentSpec.from_dict(dict(proto, brains={"a": a, "b": sneaky}))


@pytest.mark.parametrize("native", [False, True])
def test_reflection_samples_at_the_brains_own_temperature_under_native_sampling(native):
    import asyncio

    from chits.brain.mind import Mind

    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for i in range(8):
        a.remember(w.tick, f"memory {i}", 3, "note")
    m = Mind(None)
    b = m.upsert({"id": "m", "base_url": "http://127.0.0.1:9/v1", "temperature": 0.05})
    m.native_sampling = native
    seen = {}

    async def chat(msgs, **kw):
        seen.update(kw)
        return {"text": '{"lessons": [], "ambition": "to build"}', "latency_ms": 1.0}

    b.chat = chat
    asyncio.run(m._reflect(w, a, b))
    assert seen["temperature"] == (0.05 if native else 0.6)


def test_a_native_planner_varies_samplers_only_too():
    """Codex on #151 (issue #152): a planner's extra_body was exempt whole under native sampling."""
    from chits.lab.spec import ExperimentSpec, SpecError

    url = "http://127.0.0.1:9/v1"
    jev = {"id": "jev", "base_url": url, "model": "j", "prompt_style": "cascade", "escalate_to": "plan",
           "max_tokens": 120, "extra_body": {"top_k": 20}}
    plan = {"id": "plan", "base_url": url, "model": "p", "max_tokens": 120, "temperature": 1.0,
            "extra_body": {"top_k": 64, "top_p": 0.95}}
    proto = {"name": "n", "allow_models": True, "seeds": [1], "days": 1, "size": 64, "population": 3,
             "sampling": "native", "arms": [{"name": "x", "brain": "jev"}, {"name": "base"}],
             "brains": {"jev": jev, "plan": plan}}
    ExperimentSpec.from_dict(proto)
    bad = dict(proto, brains={"jev": jev, "plan": dict(plan, extra_body={"top_k": 64, "seed": 9})})
    with pytest.raises(SpecError, match="beyond samplers"):
        ExperimentSpec.from_dict(bad)
