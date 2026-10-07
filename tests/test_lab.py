"""The Experiment Lab (research plan R1): protocols, blind labels, resumable runs, matched interventions, statistics."""

import json
import socket
import threading
import time

import pytest

from chits.lab import assign, report, run, stats
from chits.lab.spec import ExperimentSpec, SpecError



def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def lab_fake_llm():
    import uvicorn
    import fake_llm as F

    F.STATE["latency"] = 0.005
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


def _proto(**kw):
    d = {"name": "speech", "arms": [{"name": "talking", "culture": "direct"}, {"name": "silent", "culture": "stigmergy"}],
         "seeds": [3, 4], "days": 2, "size": 64, "population": 6,
         "events": {"a home": {"metric": "homes", "at_least": 1}}}
    d.update(kw)
    return d


def test_a_protocol_is_checked_before_anything_runs():
    ExperimentSpec.from_dict(_proto())
    for bad in ({"arms": [{"name": "x"}]}, {"arms": [{"name": "x"}, {"name": "x"}]}, {"seeds": [1, 1]},
                {"arms": [{"name": "x", "culture": "telepathy"}, {"name": "y"}]},
                {"interventions": [{"day": 9, "kind": "drought"}]}, {"interventions": [{"day": 1, "kind": "plague"}]},
                {"arms": [{"name": "x", "brain": "rtx5090"}, {"name": "y"}]}, {"colour": "blue"}):
        with pytest.raises(SpecError):
            ExperimentSpec.from_dict(_proto(**bad))
    ok = ExperimentSpec.from_dict(_proto(
        arms=[{"name": "x", "brain": "rtx5090"}, {"name": "y"}],
        allow_models=True,
        brains={"rtx5090": {"id": "rtx5090", "base_url": "http://127.0.0.1:9/v1", "model": "dummy"}},
    ))
    with pytest.raises(SpecError, match="CHITS_LAB_ALLOW_MODELS"):  # ...and even then the runner wants the owner's go-ahead
        run.run(ok, "/nonexistent/never-written")


def test_model_arms_are_sealed_strict_and_run_with_explicit_owner_gate(monkeypatch, tmp_path, lab_fake_llm):
    brain = {"id": "fake", "label": "Fake", "base_url": lab_fake_llm, "model": "fake",
             "max_concurrency": 4, "temperature": 0.7, "max_tokens": 120}
    proto = _proto(arms=[{"name": "model", "brain": "fake"}, {"name": "baseline"}], allow_models=True,
                   brains={"fake": brain}, seeds=[7], days=1, population=3)
    spec = ExperimentSpec.from_dict(proto)
    with pytest.raises(SpecError, match="CHITS_LAB_ALLOW_MODELS"):
        run.run(spec, tmp_path / "blocked")
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    res = run.run(spec, tmp_path / "run", jobs=1)
    assert res["ran"] == 2
    rows = run.results(tmp_path / "run")
    model = next(x for x in rows if x.get("compute"))
    assert model["compute"]["requests"] > 0 and model["compute"]["tokens"] > 0
    man = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert man["protocol"]["brains"]["fake"]["base_url"] == lab_fake_llm
    assert man["fingerprint"] == spec.fingerprint()


def test_model_brain_config_is_part_of_protocol_and_never_embeds_a_literal_secret(lab_fake_llm):
    base = _proto(arms=[{"name": "model", "brain": "fake"}, {"name": "baseline"}], allow_models=True,
                  brains={"fake": {"id": "fake", "base_url": lab_fake_llm}})
    a = ExperimentSpec.from_dict(base)
    changed = dict(base)
    changed["brains"] = {"fake": {"id": "fake", "base_url": lab_fake_llm, "temperature": 0.1}}
    b = ExperimentSpec.from_dict(changed)
    assert a.fingerprint() != b.fingerprint()
    secret = dict(base)
    secret["brains"] = {"fake": {"id": "fake", "base_url": lab_fake_llm, "api_key": "literal-secret"}}
    with pytest.raises(SpecError, match="environment variable"):
        ExperimentSpec.from_dict(secret)


def test_blind_labels_are_stable_rotate_through_every_slot_and_the_seal_catches_tampering(tmp_path):
    spec = ExperimentSpec.from_dict(_proto(arms=[{"name": n} for n in ("p", "q", "r")], seeds=[1, 2, 3]))
    m = assign.labels(spec)
    assert sorted(m) == ["A", "B", "C"] and sorted(m.values()) == ["p", "q", "r"] and assign.labels(spec) == m
    orders = [assign.run_order(spec, i) for i in range(3)]
    assert all(sorted(o) == ["A", "B", "C"] for o in orders)
    assert {o[0] for o in orders} == {"A", "B", "C"}  # every label runs first once
    run.start(spec, tmp_path, "abc123")
    assert assign.unblind(tmp_path) == m
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert "p" not in json.dumps(man["runs"]) and man["fingerprint"] == spec.fingerprint()
    sealed = tmp_path / "sealed" / "assignment.json"
    swapped = dict(m)
    swapped["A"], swapped["B"] = m["B"], m["A"]
    sealed.write_text(json.dumps(swapped))
    with pytest.raises(ValueError):
        assign.unblind(tmp_path)


def test_statistics_on_known_answers():
    assert stats.describe([1, 2, 3, 4])["median"] == 2.5
    lo, hi = stats.bootstrap_ci([5, 5, 5, 5])
    assert lo == hi == 5
    lo, hi = stats.bootstrap_ci(list(range(100)), seed=3)
    assert lo < 49.5 < hi and stats.bootstrap_ci(list(range(100)), seed=3) == (lo, hi)  # seeded: reproducible
    assert stats.cliffs_delta([1, 2, 3], [4, 5, 6]) == 1.0 and stats.cliffs_delta([4, 5], [1, 2]) == -1.0
    mw = stats.mann_whitney([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert mw["u"] == 0 and mw["p"] < 0.02
    assert stats.mann_whitney([1, 2, 3], [1, 2, 3])["p"] > 0.9
    p = stats.paired({1: 10, 2: 10, 3: 10}, {1: 12, 2: 11, 3: 10, 4: 99})
    assert p["n"] == 3 and p["mean_diff"] == 1 and (p["b_higher"], p["a_higher"], p["ties"]) == (2, 0, 1)
    daily = [{"day": 1, "x": 0}, {"day": 2, "x": 3}, {"day": 3, "x": 5}]
    assert stats.first_day(daily, "x", 3) == 2 and stats.first_day(daily, "x", 9) is None
    assert stats.km_median([2, 4, None, None], 10) == 4.0  # half got there by day 4
    assert stats.km_median([2, None, None], 10) is None  # fewer than half


def test_paired_statistics_on_known_answers():
    # Exact Wilcoxon signed-rank. Six positive diffs: W+ = 21, the top of the distribution, p = 2/64.
    w = stats.wilcoxon_signed([1, 2, 3, 4, 5, 6])
    assert (w["n"], w["w_plus"]) == (6, 21) and abs(w["p"] - 2 / 64) < 1e-12
    assert abs(w["min_p"] - 2 / 64) < 1e-12  # with n pairs the smallest exact two-sided p is 2/2**n
    # All-negative: the same p from the lower tail (W+ = 0), the one-sided-tail trap.
    w2 = stats.wilcoxon_signed([-1, -2, -3, -4, -5, -6])
    assert w2["w_plus"] == 0 and w2["p"] == w["p"]
    # Zeros are dropped (they carry no sign), so n counts non-zero pairs, not seeds.
    wz = stats.wilcoxon_signed([1, 2, 3, 4, 5, 6, 0, 0])
    assert wz["n"] == 6 and wz["p"] == w["p"]
    # Ties get average ranks; fractional ranks (halves) must not break the exact distribution.
    wt = stats.wilcoxon_signed([1, 1, 2, 2, 3, 3])  # ranks 1.5,1.5,3.5,3.5,5.5,5.5, all positive: W+ = 21
    assert wt["w_plus"] == 21.0 and abs(wt["p"] - 2 / 64) < 1e-12
    # Direct proof the fractional ranks are honoured, not floored: 1,1,2 ranks 1.5,1.5,3, so W+ = 6, not 5.
    wf = stats.wilcoxon_signed([1, 1, 2])
    assert wf["w_plus"] == 6.0 and abs(wf["p"] - 0.25) < 1e-12  # (floored ranks would give W+ = 5)
    # A weaker signal: a larger p than the all-one-sign case.
    wm = stats.wilcoxon_signed([1, -2, 3, -4, 5, -6, 7, 8])
    assert wm["p"] > wt["p"]
    # Above 20 pairs: the normal approximation, still a probability.
    wb = stats.wilcoxon_signed([1, -1] * 11 + [2, 2])
    assert wb["n"] == 24 and 0 < wb["p"] <= 1
    # Sign test: 6 positives against 1 negative, two-sided exact: 2 * 8/128 = 0.125.
    s = stats.sign_test([1, 1, 1, 1, 1, 1, -1])
    assert (s["pos"], s["neg"], s["n"]) == (6, 1, 7) and abs(s["p"] - 0.125) < 1e-12
    assert stats.sign_test([1, -1, 0])["n"] == 2 and abs(stats.sign_test([1, -1, 0])["p"] - 1.0) < 1e-12
    # The frozen JevK5-vs-Gemma study reproduces its published paired p-values (issue #159).
    import csv
    from pathlib import Path
    frozen = Path(__file__).resolve().parents[1] / "docs/research/jevk5-vs-gemma/runs-blind.csv"
    rows = list(csv.DictReader(frozen.read_text().splitlines()))

    def diffs(metric):
        vals = {}
        for r in rows:
            vals.setdefault(r["seed"], {})[r["arm"]] = float(r[metric])
        return [vals[seed]["B"] - vals[seed]["A"] for seed in sorted(vals, key=int)
                if "A" in vals[seed] and "B" in vals[seed]]

    # (the published vectors, in the report's own order: 1, 2, 3, 42, 7, 99 — the test is order-free)
    assert sorted(diffs("population")) == [-12, -6, -5, -3, -2, -1]
    assert sorted(map(abs, diffs("era"))) == [0, 0, 1, 1, 1, 1]
    assert sorted(diffs("discoveries")) == [-10, -9, -9, -8, 2, 5]
    assert abs(stats.wilcoxon_signed(diffs("discoveries"))["p"] - 0.15625) < 1e-9
    assert abs(stats.wilcoxon_signed(diffs("era"))["p"] - 1.0) < 1e-9
    assert abs(stats.wilcoxon_signed(diffs("population"))["p"] - 0.03125) < 1e-9


def test_an_experiment_runs_resumes_applies_matched_interventions_and_reports_blind(tmp_path):
    spec = ExperimentSpec.from_dict(_proto(interventions=[{"day": 2, "kind": "drought"},
                                                          {"day": 2, "kind": "ore_shortage", "params": {"radius": 30}}]))
    res = run.run(spec, tmp_path, commit="abc123")
    assert res["ran"] == 4 == res["total"]
    rs = run.results(tmp_path)
    assert len(rs) == 4 and all(len(r["daily"]) == 2 for r in rs)
    assert all([iv["kind"] for iv in r["interventions"]] == ["drought", "ore_shortage"] for r in rs)  # the same in every arm
    assert run.run(spec, tmp_path)["ran"] == 0  # resume: nothing left to do
    done = tmp_path / "runs" / f"4_{rs[0]['label']}" / "result.json"
    stamp = done.stat().st_mtime_ns
    arm = next(a for a in spec.arms if a.name == assign.labels(spec)[rs[0]["label"]])
    run.run_one(spec.to_dict(), str(tmp_path), 4, rs[0]["label"], arm.__dict__)  # (two workers on one run)
    assert done.stat().st_mtime_ns == stamp  # a finished run is never run again
    (tmp_path / "runs" / f"3_{rs[0]['label']}" / "result.json").unlink()
    assert run.run(spec, tmp_path)["ran"] == 1  # a lost run is redone, the rest kept
    changed = ExperimentSpec.from_dict(_proto(days=3))
    with pytest.raises(SpecError):
        run.run(changed, tmp_path)  # another protocol can't be resumed into this directory
    blind = report.write_pack(tmp_path).read_text()
    assert "silent" not in blind
    assert "talking" not in blind
    assert "| metric | A | B |" in blind and "B vs A" in blind
    assert "a home" in blind and "Runs finished: 4 of 4" in blind
    open_ = report.write_pack(tmp_path, unblind=True).read_text()
    assert "silent" in open_ and "talking" in open_
    assert (tmp_path / "runs-blind.csv").read_text().count("\n") == 5
    assert "silent" not in (tmp_path / "runs-blind.csv").read_text()


def test_the_command_line_runs_a_json_protocol_and_analyses_it(tmp_path, capsys):
    from chits.lab.__main__ import main

    proto = tmp_path / "p.json"
    proto.write_text(json.dumps(_proto(seeds=[5])))
    assert main(["run", str(proto), "--out", str(tmp_path / "o")]) == 0
    assert main(["resume", str(tmp_path / "o")]) == 0
    assert main(["analyze", str(tmp_path / "o")]) == 0
    assert "# speech" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_proto(seeds=[])))
    assert main(["run", str(bad), "--out", str(tmp_path / "x")]) == 2



def test_model_arms_require_identical_comparison_settings(lab_fake_llm):
    shared = {"max_concurrency": 4, "timeout": 30.0, "temperature": 0.7, "max_tokens": 120,
              "json_mode": True, "disable_thinking": True, "extra_body": {"top_p": 0.95, "top_k": 40, "min_p": 0.05},
              "prompt_style": "full", "escalate_below": 0.5, "escalate_share": 0.3, "focus": True}
    brains = {
        "a": {"id": "a", "label": "A", "base_url": lab_fake_llm, "model": "model-a", **shared},
        "b": {"id": "b", "label": "B", "base_url": lab_fake_llm + "/other", "model": "model-b", **shared},
    }
    ExperimentSpec.from_dict(_proto(
        arms=[{"name": "A", "brain": "a"}, {"name": "B", "brain": "b"}],
        allow_models=True, brains=brains,
    ))

    for field_name, value in (("temperature", 0.1), ("max_concurrency", 2), ("timeout", 5.0),
                              ("prompt_style", "cascade"), ("escalate_below", 0.2),
                              ("extra_body", {"top_p": 0.8})):
        changed = json.loads(json.dumps(brains))
        changed["b"][field_name] = value
        with pytest.raises(SpecError, match="identical comparison settings"):
            ExperimentSpec.from_dict(_proto(
                arms=[{"name": "A", "brain": "a"}, {"name": "B", "brain": "b"}],
                allow_models=True, brains=changed,
            ))


def test_lab_manifest_pins_prompt_version(tmp_path):
    from chits.brain import prompt as P

    spec = ExperimentSpec.from_dict(_proto(seeds=[9]))
    run.start(spec, tmp_path, commit="deadbeef")
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["commit"] == "deadbeef"
    assert man["prompt_version"] == P.PROMPT_VERSION



def test_report_exports_persistent_lifetime_dataset(tmp_path):
    from chits.lab import report

    spec = ExperimentSpec.from_dict(_proto(seeds=[3], days=1, population=3))
    out = tmp_path / "life"
    run.start(spec, out, commit="abc")
    run.run(spec, out, jobs=1)
    report.write_pack(out)

    path = out / "lifetime-blind.csv"
    assert path.exists()
    rows = list(__import__("csv").DictReader(path.open()))
    assert len(rows) == 2
    assert all(r["since_tick"] == "0" and r["complete_from_start"] == "True" for r in rows)
    assert all(int(r["through_tick"]) > 0 for r in rows)
    assert any(k not in {"seed", "arm", "since_tick", "through_tick", "complete_from_start"} for k in rows[0])
