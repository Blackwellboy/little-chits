"""The scorecard: which model is building the better civilisation, from what the game already records."""

import asyncio
from collections import deque

from chits import diag
from chits.runtime import Runtime


def test_the_scorecard_compares_the_worlds_over_the_same_stretch(tmp_path):
    rt = Runtime(tmp_path)
    rt.mind.decisions = deque(maxlen=8)  # (the real one keeps 5000: the count must not stop at the window)
    ids = list(rt.worlds)
    assert len(ids) >= 2, "a versus game has two worlds"
    a, b = (rt.worlds[i] for i in ids[:2])
    # a game resumed at tick 500: decisions are counted from then, and so are the discoveries they're weighed against
    for w in (a, b):
        w.tick = 500
        rt._attach(w)
    for w, adopted, found in ((a, 10, 3), (b, 20, 2)):
        for i in range(found):
            w.first[f"recipe:thing{i}"] = {"tick": w.tick + 1, "by": "", "name": ""}
        w.first["recipe:old"] = {"tick": 400, "by": "", "name": ""}  # before this session: not counted per decision
        for i in range(adopted):
            rec = {"world": w.id, "outcome": "pending", "choice": {"escalated": i % 5 == 0}}
            rt.mind.decisions.append(rec)
            rt.mind._resolve(rec, "adopted", w.tick)
        chief = {"world": w.id, "style": "chief-project", "outcome": "pending", "choice": {"requested": "A"}}
        rt.mind.decisions.append(chief)
        rt.mind._resolve(chief, "adopted", w.tick)  # the chief's project choice is not a plan decision
    sc = diag.scorecard(rt)
    rows = {r["world"]: r for r in sc["rows"]}
    assert rows[a.id]["discoveries_this_session"] == 3 and rows[a.id]["decisions"] == 10
    assert rows[a.id]["discoveries_per_100_decisions"] == 30.0 and rows[b.id]["discoveries_per_100_decisions"] == 10.0
    assert rows[b.id]["escalation_pct"] == 14.3  # of b's last 7 plan choices kept (i = 13..19), 15 was escalated
    assert sc["lead"]["discoveries_per_100_decisions"] == a.id
    assert "since the game last started" in sc["note"]
    rt.store.db.close()
    asyncio.run(rt.mind.close())
