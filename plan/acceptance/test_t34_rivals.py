import json


def rivals(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_PER_WORLD", "4")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import MODES, Runtime

    assert "rivals" in MODES and MODES["rivals"]["worlds"] == ["A", "B"]
    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="rivals")
    assert rt.contact
    return rt


def test_hostility_war_and_peace(tmp_path, monkeypatch):
    rt = rivals(tmp_path, monkeypatch)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    for _ in range(6):
        rt.record_incident(wa, wb, "theft")
    assert wa.relations["B"]["hostility"] >= 60 and wa.relations["B"]["state"] == "war"
    assert wb.relations["A"]["state"] == "war"
    kinds = [e.kind for e in wa.events] + [e.kind for e in wb.events]
    assert "war" in kinds
    for _ in range(6):
        rt.record_incident(wa, wb, "gift")
    assert wa.relations["B"]["state"] in ("tension", "peace")
    for _ in range(10):
        rt.record_incident(wa, wb, "trade")
    assert wa.relations["B"]["state"] == "peace" and "peace" in [e.kind for e in wa.events]
    d = json.loads(json.dumps(wa.to_dict()))
    from chits.sim.world import World

    assert World.from_dict(d).relations["B"]["state"] == "peace"
