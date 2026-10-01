from chits.story.moments import Moment, find_moments, top_moments

NAMES = {"a1": "Pip", "a2": "Mo", "a3": "Bix", "a4": "Tam", "a5": "Lu"}


def ev(seq, tick, kind, actor=None, **data):
    return {"seq": seq, "tick": tick, "kind": kind, "text": f"{kind} text {seq}", "importance": 3, "actor": actor,
            "x": float(seq), "y": 2.0, "data": data}


def test_first_and_local_name():
    ms = find_moments([ev(1, 10, "discovery", "a1", knowledge="recipe:stone_axe"),
                       ev(2, 20, "discovery", "a2", knowledge="recipe:cord", local_name="Twisty")], NAMES)
    by = {m.seqs[0]: m for m in ms}
    assert by[1].kind == "first" and by[1].score == 90
    assert by[2].score == 95 and by[2].actors == ["a2"]


def test_teaching_chain():
    evs = [
        ev(1, 100, "learned", "a2", how="taught", knowledge="recipe:stone_axe", source="a1"),
        ev(2, 300, "learned", "a3", how="taught", knowledge="recipe:stone_axe", source="a2"),
        ev(3, 500, "learned", "a4", how="taught", knowledge="recipe:stone_axe", source="a3"),
        ev(4, 510, "learned", "a5", how="taught", knowledge="recipe:cord", source="a1"),
    ]
    chains = [m for m in find_moments(evs, NAMES) if m.kind == "teaching_chain"]
    assert len(chains) == 1
    c = chains[0]
    assert c.actors == ["a1", "a2", "a3", "a4"] and c.seqs == [1, 2, 3]
    assert c.score == 75
    assert "Pip taught Mo, who taught Bix" in c.text and "stone axe" in c.text
    assert c.tick == 500 and c.x == 3.0


def test_chain_breaks_on_gap():
    evs = [
        ev(1, 100, "learned", "a2", how="taught", knowledge="recipe:brick", source="a1"),
        ev(2, 700, "learned", "a3", how="taught", knowledge="recipe:brick", source="a2"),
    ]
    assert not [m for m in find_moments(evs, NAMES) if m.kind == "teaching_chain"]


def test_other_kinds_and_sorting():
    evs = [
        ev(1, 5, "discovery", "a1", knowledge="recipe:brick"),
        ev(2, 50, "death", "a1", cause="starvation"),
        ev(3, 60, "death", "a3", cause="old age"),
        ev(4, 70, "built", "a2", builders=["a1", "a2", "a3", "a4"], first=True),
        ev(5, 80, "birth", "a5", generation=2),
        ev(6, 90, "legacy", "a4"),
        ev(7, 95, "storm"),
        ev(8, 96, "settlement", "a2", name="Mossbrook"),
        ev(9, 97, "ambition", "a3", ambition="Build a monument"),
        ev(10, 98, "speech", "a3"),
    ]
    ms = find_moments(evs, NAMES)
    kinds = {m.kind: m for m in ms}
    assert kinds["lost_pioneer"].score == 85 and kinds["lost_pioneer"].actors == ["a1"]
    assert not any(m.kind == "lost_pioneer" and m.actors == ["a3"] for m in ms)
    assert kinds["built_together"].score == 75
    assert kinds["birth"].score == 60 and kinds["legacy"].score == 80
    assert kinds["storm"].score == 65 and kinds["settlement"].score == 75 and kinds["ambition"].score == 45
    assert all(isinstance(m, Moment) and m.seqs for m in ms)
    scores = [(m.score, m.tick) for m in ms]
    assert scores == sorted(scores, reverse=True)
    assert all(m.kind != "speech" for m in ms)
    top = top_moments(evs, NAMES, since_tick=60, limit=3)
    assert len(top) == 3 and all(m.tick >= 60 for m in top)
