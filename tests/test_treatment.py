"""TreatmentPack (research plan item 46): what an arm's founders are told at the start, linted so it can't touch
anything else, and carried by the lab without unblinding its report."""

import copy
import json

import pytest

from chits.lab import run
from chits.lab import treatment as T
from chits.lab.__main__ import main as lab_main
from chits.lab.spec import ExperimentSpec, SpecError
from chits.sim.world import World


def _pack(**kw):
    p = {"id": "keepers", "version": "1", "title": "Fire keepers", "scope_note": "a synthetic test pack",
         "sources": [{"id": "s1", "citation": "Made up for a test", "edition": "1st", "licence": "CC0-1.0"}],
         "claims": [{"id": "c1", "text": "A fire kept in stone lasts the night.", "category": "practice", "sources": ["s1"]},
                    {"id": "c2", "text": "Elders should be fed first.", "category": "norm", "sources": ["s1"]}],
         "practices": [{"knowledge": "recipe:sharp_stone", "sources": ["s1"]},
                       {"knowledge": "design:campfire", "sources": ["s1"]}],
         "founders": {"share": 0.5}, "reviewer_notes": "none"}
    p.update(kw)
    return p


def _errors(pack):
    return [f"{x['where']}: {x['problem']}" for x in T.lint(pack) if x["level"] == "error"]


def test_a_good_pack_lints_clean_and_reports_what_it_covers():
    assert _errors(_pack()) == []
    c = T.coverage(_pack())
    assert c["claims"] == 2 and c["by_category"] == {"practice": 1, "norm": 1} and c["practices"] == 2
    assert c["sources"] == c["sources_cited"] == 1 and c["founder_share"] == 0.5
    assert c["est_tokens_per_founder"] == round((36 + 27) * T.TOKENS_PER_CHAR) and len(c["fingerprint"]) == 16


@pytest.mark.parametrize("change,expect", [
    ({"inventory": {"iron": 9}}, "only changes what founders know"),
    ({"physics": {"gravity": 0}}, "only changes what founders know"),
    ({"title": ""}, "title: missing"),
    ({"sources": []}, "sources: missing"),
    ({"sources": [{"id": "s1", "citation": "x", "edition": "1"}]}, "no licence"),
    ({"sources": [{"id": "s1", "licence": "CC0", "edition": "1"}]}, "no citation"),
    ({"sources": [{"id": "s1", "citation": "x", "licence": "CC0"}, {"id": "s1", "citation": "y", "licence": "CC0"}]},
     "used twice"),
    ({"claims": [{"id": "c1", "text": "x", "category": "practice", "sources": ["nope"]}]}, "unknown source 'nope'"),
    ({"claims": [{"id": "c1", "text": "x", "category": "practice", "sources": []}]}, "cites no source"),
    ({"claims": [{"id": "c1", "text": "x", "category": "rumour", "sources": ["s1"]}]}, "category 'rumour'"),
    ({"claims": [{"id": "c1", "text": "x" * 300, "category": "story", "sources": ["s1"]}]}, "300 characters"),
    ({"claims": [{"id": "c1", "text": "x", "category": "story", "sources": ["s1"]}] * 2}, "claim id 'c1' is used twice"),
    ({"practices": [{"knowledge": "recipe:warp_drive", "sources": ["s1"]}]}, "never invents physics"),
    ({"practices": [{"knowledge": "sharp_stone", "sources": ["s1"]}]}, "never invents physics"),
    ({"practices": [{"knowledge": "recipe:sharp_stone"}]}, "cites no source"),
    ({"claims": [], "practices": []}, "tells the founders nothing"),
    ({"founders": {"share": 0}}, "share is the fraction"),
    ({"founders": {"share": 1.5}}, "share is the fraction"),
    ({"founders": {"share": True}}, "share is the fraction"),
    ({"founders": {"share": 0.5, "who": "the chief"}}, "only 'share' is known"),
])
def test_the_linter_refuses(change, expect):
    errs = _errors(_pack(**change))
    assert any(expect in e for e in errs), errs


def test_warnings_do_not_refuse_a_pack():
    p = _pack(sources=[{"id": "s1", "citation": "x", "licence": "CC0"}, {"id": "s2", "citation": "y", "licence": "CC0"}])
    lv = {(x["where"], x["level"]) for x in T.lint(p)}
    assert ("sources[0] s1", "warning") in lv and ("sources s2", "warning") in lv  # no edition; cited by nothing
    T.check(p)
    with pytest.raises(T.TreatmentError):
        T.check(_pack(title=""))


def _world(seed=5):
    return World("A", "A", seed, "direct", 64, 8)


def _state(w):
    return {a.id: (a.x, a.y, dict(a.inventory), a.hunger) for a in w.agents.values()}, dict(w.flags), w.tick, \
        sorted(w.structures), list(w.res_amt)


def test_apply_tells_the_seeded_share_of_founders_and_changes_nothing_else():
    w = _world()
    before_know = {a.id: dict(a.knows) for a in w.agents.values()}
    before = copy.deepcopy(_state(w))
    log = T.apply(w, _pack(), seed=5)
    assert _state(w) == before  # knowledge only
    told = set(log["told"])
    assert len(told) == 4 and log["of"] == 8 and log["pack"] == "treatment:keepers@1"
    for a in w.agents.values():
        if a.id in told:
            k = a.knows["recipe:sharp_stone"]
            assert k["how"] == "taught" and k["status"] == "told" and k["from"] == "treatment:keepers@1"
            assert "design:campfire" in a.knows
            assert {"A fire kept in stone lasts the night.", "Elders should be fed first."} <= {m.text for m in a.memories}
        else:
            assert a.knows == before_know[a.id]
    again = T.apply(_world(), _pack(), seed=5)
    assert again["told"] == log["told"]  # the same seed tells the same chits
    assert T.apply(_world(), _pack(founders={"share": 1.0}), seed=5)["told"] == sorted(w.agents)
    with pytest.raises(T.TreatmentError):
        T.apply(_world(), _pack(inventory={"iron": 1}), seed=5)


def _proto(**kw):
    d = {"name": "told", "arms": [{"name": "told", "treatment": "keepers"}, {"name": "control"}], "seeds": [3],
         "days": 1, "size": 64, "population": 6, "treatments": {"keepers": _pack()}}
    d.update(kw)
    return d


def test_the_protocol_checks_its_packs():
    ExperimentSpec.from_dict(_proto())
    for bad in ({"treatments": {}}, {"treatments": {"other": _pack()}}, {"treatments": {"keepers": _pack(title="")}},
                {"treatments": {"keepers": _pack(id="other")}},  # (the pack's own id must match its name)
                {"treatments": {"keepers": "not a pack"}}):
        with pytest.raises(SpecError):
            ExperimentSpec.from_dict(_proto(**bad))
    a = ExperimentSpec.from_dict(_proto()).fingerprint()
    b = ExperimentSpec.from_dict(_proto(treatments={"keepers": _pack(version="2")})).fingerprint()
    assert a != b  # a changed pack is a changed protocol


def test_a_protocol_names_its_pack_by_path(tmp_path):
    (tmp_path / "packs").mkdir()
    (tmp_path / "packs" / "keepers.json").write_text(json.dumps(_pack()))
    (tmp_path / "p.json").write_text(json.dumps(_proto(treatments={"keepers": "packs/keepers.json"})))
    spec = ExperimentSpec.load(tmp_path / "p.json")
    assert spec.treatments["keepers"] == _pack()
    (tmp_path / "q.json").write_text(json.dumps(_proto(treatments={"keepers": "packs/missing.json"})))
    with pytest.raises(SpecError, match="reading a treatment pack"):
        ExperimentSpec.load(tmp_path / "q.json")


def test_the_lab_applies_the_pack_to_its_arm_only_and_keeps_the_report_blind(tmp_path):
    spec = ExperimentSpec.from_dict(_proto())
    run.run(spec, tmp_path)
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["treatments"]["keepers"]["claims"] == 2
    told = sorted(tmp_path.glob("runs/*/treatment.json"))
    assert len(told) == 1 and json.loads(told[0].read_text())["pack"] == "treatment:keepers@1"
    for rd in tmp_path.glob("runs/*"):
        assert "treatment" not in (rd / "result.json").read_text()


def test_lint_on_the_command_line(tmp_path, capsys):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_pack()))
    bad.write_text(json.dumps(_pack(inventory={"iron": 1})))
    assert lab_main(["lint", str(good)]) == 0
    assert '"claims": 2' in capsys.readouterr().out
    assert lab_main(["lint", str(bad)]) == 2
    assert "error: inventory" in capsys.readouterr().out
