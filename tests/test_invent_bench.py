"""The invention benchmark (F34): a fixed list of attempts a model might write, judged by both engines."""

import json

from chits.sim import invent as INV
from chits.tools import invent_bench as B


def test_the_benchmark_is_big_enough_and_covers_every_kind_of_attempt_and_purpose():
    assert len(B.CASES) >= 40
    kinds = [c[5] for c in B.CASES]
    for kind in (B.SENSIBLE, B.IMPOSSIBLE, B.VAGUE, B.WRONG_PURPOSE):
        assert kinds.count(kind) >= 5, kind
    assert {c[4] for c in B.CASES if c[3]} == {p[0] for p in INV.PURPOSES}  # a sensible attempt at every purpose
    assert len({(c[0], json.dumps(c[1], sort_keys=True), c[2]) for c in B.CASES}) == len(B.CASES)  # no attempt twice
    texts = {c[0] for c in B.CASES}
    for was_wrong_on_main in ("a pointed stick to catch fish", "a shoe to run fast", "something to heat the hut"):
        assert was_wrong_on_main in texts


def test_the_composing_engine_gets_every_verdict_right_and_the_first_engine_does_not():
    res = B.bench()
    new, old = res["new"], res["old"]
    assert new["right"] == res["cases"] == len(B.CASES), [r["text"] for r in new["rows"] if not r["right"]]
    assert old["right"] < new["right"]
    wrong = {r["text"]: r for r in old["rows"] if not r["right"]}
    # the first engine's two kinds of mistake: a sensible thing refused, and a thing the parts cannot be accepted
    assert not wrong["a pointed stick to catch fish"]["ok"] and not wrong["a fishing net, not a weapon"]["ok"]
    assert wrong["a blanket to keep warm"]["ok"] and wrong["a remedy to cure the sick"]["ok"]
    assert wrong["a cart to carry more"]["purpose"] == "speed"
    by = {(r["text"], json.dumps(r["bag"], sort_keys=True)): r for r in new["rows"]}
    heat = by[("something to heat the hut", json.dumps({"stone": 1, "wood": 1}, sort_keys=True))]
    assert not heat["ok"] and heat["purpose"] == "warmth" and "could make something for" in heat["feedback"]
    for r in new["rows"]:  # every accepted invention does something, and says which rule made it
        assert not r["ok"] or (r["rule"] in INV.RULE and INV.effect_words(r["effect"])), r["text"]


def test_the_benchmark_is_deterministic_and_leaves_the_engine_switch_as_it_was(monkeypatch, capsys):
    a, b = B.bench(), B.bench()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert INV.COMPOSE is True
    monkeypatch.setattr(INV, "COMPOSE", False)
    assert B.bench()["new"]["right"] == a["new"]["right"] and INV.COMPOSE is False
    assert B.main([]) == 0
    out = capsys.readouterr().out
    assert "| keywords (first engine) |" in out and "| composition |" in out and "What each invention" in out
    assert B.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["cases"] == len(B.CASES)
