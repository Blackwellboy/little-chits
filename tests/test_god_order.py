"""God-mode Order overlay (SOK-284): dispatch one job to Auto or a picked chit, never overwriting critical work.

The backend reuses the possess order planner (``chits.brain.orders``): same verbs, same friendly errors, but instead
of one possessed chit there is an Auto picker and a per-world queue, and every attempt lands in the decisions trail
(``style == "god-order"``).
"""

import os

from chits.runtime import Runtime


def _rt(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_MODE", "single")
    return Runtime(tmp_path)


def _client(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_MODE", "single")
    from fastapi.testclient import TestClient

    from chits.app import app

    return TestClient(app)


def _busy(w):
    for a in w.agents.values():
        a.plan = [{"do": "gather", "what": "stone", "qty": 3}]
        a.plan_source = "player"
        a.goal = "mine stone"


# ---------------------------------------------------------------------------------------------- auto / pick / queue
def test_auto_assigns_when_a_free_capable_chit_exists(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    rsp = r.god_order("A", action="mine")
    assert rsp["outcome"] == "assigned"
    assert rsp["agent_id"] in w.agents
    assert rsp["goal"].startswith("mine")
    assert w.agents[rsp["agent_id"]].plan_source == "player"


def test_auto_queues_when_all_capable_chits_are_busy(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    _busy(w)
    rsp = r.god_order("A", action="mine")
    assert rsp["outcome"] == "queued"
    assert rsp["message"].startswith("queued for")
    assert len(r.god_queues["A"]) == 1
    # nothing was overwritten
    assert all(a.plan and a.plan[0]["do"] == "gather" for a in w.agents.values())


def test_pick_assigns_a_free_chit(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    aid = next(iter(w.agents))
    rsp = r.god_order("A", action="mine", agent_id=aid)
    assert rsp["outcome"] == "assigned"
    assert rsp["agent_id"] == aid
    assert rsp["agent_name"] == w.agents[aid].name


def test_pick_queues_a_busy_chit_without_overwriting(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    aid = next(iter(w.agents))
    a = w.agents[aid]
    a.plan = [{"do": "gather", "what": "stone", "qty": 3}]
    a.plan_source = "player"
    a.goal = "mine stone"
    rsp = r.god_order("A", action="mine", agent_id=aid)
    assert rsp["outcome"] == "queued"
    assert rsp["message"] == f"queued for {a.name}"
    assert w.agents[aid].plan[0]["do"] == "gather"  # critical work left alone


def test_pick_refuses_an_incapable_chit_with_a_friendly_error(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    aid = next(iter(w.agents))
    try:
        r.god_order("A", action="smelt", agent_id=aid)  # a fresh chit knows no ore recipe
    except ValueError as e:
        assert "smelt" in str(e).lower() or "recipe" in str(e).lower()
    else:
        raise AssertionError("smelting without a recipe should refuse")
    assert any(x.get("style") == "god-order" and x["outcome"] == "refused"
               for x in r.store.decisions("A", limit=10))


def test_text_order_is_parsed_like_possess(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    rsp = r.god_order("A", text="mine iron")
    assert rsp["action"] == "mine"
    assert rsp["outcome"] == "assigned"
    assert r.worlds["A"].agents[rsp["agent_id"]].goal.startswith("mine iron")


def test_cancel_auto_finds_a_side_quest_to_drop(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    aid = next(iter(w.agents))
    a = w.agents[aid]
    a.plan = [{"do": "explore"}, {"do": "eat", "what": "berries"}]
    a.goal = "wander"
    rsp = r.god_order("A", action="cancel")
    assert rsp["outcome"] == "assigned"
    assert all(s.get("do") in ("eat", "sleep", "rest", "shelter", "store", "drop", "refuel") for s in a.plan)


# ---------------------------------------------------------------------------------------------- decision trail
def test_decision_trail_gets_a_god_order_record(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    r.god_order("A", action="mine")
    recs = r.store.decisions("A", limit=10)
    rec = next(x for x in recs if x.get("style") == "god-order")
    assert rec["outcome"] == "assigned"
    assert rec["brain"] == "god" and rec["model"] == "god"
    assert rec["action"] == "mine"
    assert rec["select"] == "auto"
    assert rec["agent"] in r.worlds["A"].agents


def test_a_refused_attempt_is_logged_too(tmp_path, monkeypatch):
    r = _rt(tmp_path, monkeypatch)
    w = r.worlds["A"]
    aid = next(iter(w.agents))
    try:
        r.god_order("A", action="smelt", agent_id=aid)
    except ValueError:
        pass
    recs = r.store.decisions("A", limit=10)
    assert any(x.get("style") == "god-order" and x["outcome"] == "refused" for x in recs)


# ---------------------------------------------------------------------------------------------- HTTP contract
def test_god_order_via_the_api(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        got = c.post("/api/worlds/A/god/order", json={"action": "mine"})
        assert got.status_code == 200
        body = got.json()
        assert body["ok"] is True and body["outcome"] == "assigned"
        assert body["agent_id"] and body["goal"]
        # unknown chit -> 404
        assert c.post("/api/worlds/A/god/order", json={"action": "mine", "agent_id": "nope"}).status_code == 404
        # unknown world -> 404
        assert c.post("/api/worlds/Z/god/order", json={"action": "mine"}).status_code == 404
        # bad text -> 400
        assert c.post("/api/worlds/A/god/order", json={"text": "flibbertigibbet"}).status_code == 400


def test_an_experiment_refuses_god_order(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/api/reset", json={"mode": "single", "contract": "experiment"})
        assert c.post("/api/worlds/A/god/order", json={"action": "mine"}).status_code == 409


def test_possess_order_path_still_works(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        from chits.app import R

        r = R()
        wid, aid = "A", next(iter(r.worlds["A"].agents))
        assert c.post(f"/api/worlds/{wid}/agents/{aid}/possess").json() == {"ok": True, "possessed": aid}
        assert c.post(f"/api/worlds/{wid}/agents/{aid}/order", json={"action": "mine"}).status_code == 200
        assert c.post(f"/api/worlds/{wid}/possess/release").json() == {"ok": True}
