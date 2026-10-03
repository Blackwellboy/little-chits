"""🐢 "Why is nothing happening?": the diagnostics report as a few plain sentences per world (diag.why_slow)."""

import asyncio

from chits import diag
from chits.runtime import Runtime


def _world(**over):
    wd = {"name": "Ember", "brain": "instinct", "day": 12, "population": 90, "plans": {}, "model_share_pct": 0.0,
          "waiting_on_model_pct": 0.0, "steps_ok": 0, "steps_failed": 0, "step_success_pct": 0.0, "top_failures": [],
          "stuck": [], "loops": {}, "days_since_last_discovery": 0.5, "opportunities": {}}
    wd.update(over)
    return wd


def _report(wd, **over):
    r = {"paused": False, "pacing_to_brain": False, "durability": {"save_errors": {}, "invalid_reason": ""},
         "brains": {}, "worlds": {"A": wd}}
    r.update(over)
    return r


def _texts(r, wid="A"):
    return [x["text"] for x in diag.why_slow(r)["worlds"][wid]["reasons"]]


def test_a_shortage_names_the_building_that_would_end_it_and_who_could_build_it():
    wd = _world(top_failures=[["gather: there is no sand anywhere nearby — maybe explore", 35]],
                opportunities={"design:sand_pit": {"known_by": 60, "affordable_by": 58, "sites_started": 0}})
    assert _texts(_report(wd)) == ["No sand near home: 35 failed tries so far. A sand pit would fix it and 58 chits "
                                   "could build one."]
    # known, but nobody has the materials; and being built
    wd["opportunities"]["design:sand_pit"] = {"known_by": 3, "affordable_by": 0, "sites_started": 0}
    assert _texts(_report(wd))[0].endswith("A sand pit would fix it. 3 chits know how, but none has the materials.")
    wd["opportunities"]["design:sand_pit"] = {"known_by": 3, "affordable_by": 1, "sites_started": 1}
    assert _texts(_report(wd))[0].endswith("A sand pit is being built.")


def test_a_building_nobody_there_knows_is_not_named():
    wd = _world(top_failures=[["gather: there is no copper ore anywhere nearby — maybe explore", 40]],
                opportunities={"design:mine": {"known_by": 0, "affordable_by": 0, "sites_started": 0}})
    assert _texts(_report(wd)) == ["No copper ore near home: 40 failed tries so far."]


def test_a_slow_model_is_the_first_reason_and_says_how_little_it_answers():
    wd = _world(brain="m", plans={"model": 2, "filler": 98, "routine": 400, "shed": 30},
                model_share_pct=2.0, waiting_on_model_pct=55.0)
    brains = {"m": {"healthy": True, "speed": {"level": "slow", "chits": 90}}}
    t = _texts(_report(wd, brains=brains))
    assert t[0] == "The model answers only 2% of decisions: it is too slow for 90 chits."
    assert "Chits spend 55% of their time waiting for the model." in t
    assert "30 decisions were left to instinct because the model's queue was full." in t
    # a model that isn't answering at all says so instead
    brains["m"]["healthy"] = False
    assert _texts(_report(wd, brains=brains))[0] == "The model is not answering. Chits act on instinct until it does."
    # and an instinct world never blames a model
    assert not any("model" in x for x in _texts(_report(_world(plans={"instinct": 500}))))


def test_other_reasons_come_from_their_own_fields_and_the_list_is_short():
    wd = _world(steps_ok=100, steps_failed=200, step_success_pct=33.3, days_since_last_discovery=6.2,
                stuck=[{"name": "Ada", "fails_in_a_row": 7, "doing": "gathering", "last": "x"}],
                top_failures=[["craft: it needs a kiln and there is none nearby", 50], ["store: there's no stockpile nearby", 20],
                              ["gather: there is no sand nearby; you remember some at (#,#)", 12], ["eat: rare", 2]],
                opportunities={"design:kiln": {"known_by": 9, "affordable_by": 4, "sites_started": 0},
                               "design:boat": {"known_by": 9, "affordable_by": 9, "sites_started": 0},
                               "design:forge": {"known_by": 0, "affordable_by": 0, "sites_started": 0},
                               "recipe:copper": {"inputs_handled_by": 5, "tried_by": 0}})
    t = _texts(_report(wd))
    assert len(t) == diag.WHY_MAX
    assert t[0] == ("Chits keep failing to craft: 50 failed tries so far. They say: it needs a kiln and there is none "
                    "nearby.")
    assert "Only 33.3% of plan steps work." in t
    assert "No new discovery for 6 days." in t
    diag_max, diag.WHY_MAX = diag.WHY_MAX, 20  # (past the cap that keeps the panel short: everything it found)
    try:
        full = _texts(_report(wd))
    finally:
        diag.WHY_MAX = diag_max
    assert "1 chit keeps failing the same step. Ada failed 7 times in a row." in full
    assert "Nobody has started a kiln. 9 chits know how and 4 have the materials." in full
    assert not any("rare" in x for x in full), "a failure seen twice is not a reason"
    assert not any("boat" in x or "forge" in x or "copper" in x for x in full), "nothing the world can't act on or doesn't know"


def test_what_stops_every_world_is_said_once_for_the_game():
    assert diag.why_slow(_report(_world(), paused=True))["game"] == [{"kind": "paused", "text": "The game is paused."}]
    r = _report(_world(), paused=True, durability={"save_errors": {"A": "disk full"}, "invalid_reason": ""})
    assert [g["kind"] for g in diag.why_slow(r)["game"]] == ["save"]
    assert "disk full" not in str(diag.why_slow(r)), "the raw error stays in the diagnostics"
    assert diag.why_slow(_report(_world(), pacing_to_brain=True))["game"][0]["text"] == "The clock is waiting for a model to answer."
    quiet = diag.why_slow(_report(_world()))
    assert quiet["game"] == [] and quiet["worlds"]["A"] == {"name": "Ember", "day": 12, "brain": "instinct", "reasons": []}


def test_a_real_world_report_becomes_reasons(tmp_path):
    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    chits = list(w.agents.values())[:3]
    for a in chits:
        a.inventory.clear()
        a.learn("design:sand_pit", "taught", w.tick, None)
    for a in chits[:2]:
        a.inventory.update(wood=4, stone=2)  # what a sand pit takes
    for _ in range(12):
        diag.step_failed(w, chits[0], "gather", "there is no sand anywhere nearby — maybe explore", "sand")
    why = diag.why_slow(diag.report(rt))
    assert set(why["worlds"]) == set(rt.worlds)
    mine = why["worlds"][w.id]
    assert mine["name"] == w.name and mine["day"] == w.day + 1
    assert {"kind": "failure", "text": "No sand near home: 12 failed tries so far. A sand pit would fix it and 2 chits "
                                       "could build one."} in mine["reasons"]
    assert any(x["kind"] == "stuck" and chits[0].name in x["text"] for x in mine["reasons"])
    other = next(x for wid, x in why["worlds"].items() if wid != w.id)
    assert not any(x["kind"] == "failure" for x in other["reasons"]), "one world's failures are not another's"
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_the_endpoint_needs_the_token_like_the_other_private_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_TOKEN", "why-test-token")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from fastapi.testclient import TestClient
    from chits.app import app

    with TestClient(app) as c:
        assert c.get("/api/why").status_code == 401
        r = c.get("/api/why", headers={"Authorization": "Bearer why-test-token"})
        assert r.status_code == 200
        body = r.json()
        assert body["game"] == []
        assert body["worlds"] and all(isinstance(x["reasons"], list) for x in body["worlds"].values())
        h = {"Authorization": "Bearer why-test-token"}
        assert c.post("/api/control", json={"paused": True}, headers=h).status_code == 200
        assert c.get("/api/why", headers=h).json()["game"] == [{"kind": "paused", "text": "The game is paused."}]
