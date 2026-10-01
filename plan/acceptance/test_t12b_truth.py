from chits.story import chronicle as C

NAMES = {"a1": "Mara", "a2": "Tovi", "a3": "Bix"}
WORLD = {"id": "A", "name": "World A", "label": "Direct culture", "culture": "direct", "brain": "x"}


def ev(seq, kind, actor, text, imp=3, **data):
    return {"seq": seq, "tick": 300, "kind": kind, "text": text, "importance": imp, "actor": actor, "x": 1.0,
            "y": 1.0, "data": data}


EVENTS = [ev(1, "helped", "a1", "Mara brought 3 wood to Tovi's hut", 2),
          ev(2, "built", "a2", "Tovi finished a hut", 2, builders=["a2", "a1"], first=False)]


def facts():
    return C.daily_facts(WORLD, 2, EVENTS, {"population": 3}, NAMES)


def test_embellishment_is_flagged():
    known = set(NAMES.values())
    bad = "Mara courageously rallied the frightened village and saved everyone, the best builder on the island."
    probs = C.validate_narration(bad, facts(), known)
    text = " ".join(probs)
    for fam in ("emotion", "leadership", "causation", "superlative"):
        assert f"unsupported {fam}" in text, (fam, probs)


def test_facts_carry_kinds():
    assert [e.get("kind") for e in facts()["events"]] == ["helped", "built"]


def test_plain_retelling_passes():
    ok = "Mara carried wood to Tovi's hut (#1), and Tovi finished it that afternoon (#2)."
    assert C.validate_narration(ok, facts(), set(NAMES.values())) == []
