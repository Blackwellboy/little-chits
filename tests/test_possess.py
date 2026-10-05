"""Possess: an observer controls one chit per world and gives it age-gate orders (a click or a line of text).

Pure unit tests where possible: the slot selector, the order planner and the free-text mapper need no model server.
The HTTP contract (possess/order, experiment refusal, 400/404/409) is checked with FastAPI's TestClient, like the
other API tests.
"""

import os

from chits.brain.llm import BrainConfig, LLMBrain
from chits.brain.mind import Mind, _select_ai_chits
from chits.brain import orders
from chits.sim import projects
from chits.sim.actions import VERBS
from chits.sim.world import World

FAKE_ROAD = {
    "age": "Iron Age",
    "steps": [
        {"kind": "design", "key": "forge", "name": "forge", "done": False, "needs": ""},
        {"kind": "recipe", "key": "iron", "name": "iron", "done": False, "needs": ""},
    ],
    "text": "Iron Age: forge ✗ · iron ✗",
}


def _brain(cap):
    return LLMBrain(BrainConfig(id="x", base_url="http://x/v1", max_ai_chits=cap))


def _world(n=4):
    w = World("A", "A", 11, "direct", 96, n)
    for a in w.agents.values():
        a.brain = "x"
    return w, list(w.agents.values())


# ---------------------------------------------------------------------------------------------- slots
def test_possessed_chit_always_gets_a_slot_and_never_exceeds_cap(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(4)
    agents[0].job = "scholar"  # the possessed chit, deliberately the lowest priority
    agents[1].job = "gatherer"
    agents[2].job = "crafter"
    agents[3].job = "scholar"
    selected = _select_ai_chits(w, _brain(2), agents, {"A": agents[0].id})
    assert agents[0].id in selected  # forced in despite its score
    assert len(selected) <= 2  # and the cap still holds


def test_release_frees_the_possessed_slot(monkeypatch):
    monkeypatch.setattr(projects, "road", lambda world: FAKE_ROAD)
    w, agents = _world(3)
    agents[0].job = "gatherer"
    agents[1].job = "crafter"
    agents[2].job = "scholar"
    m = Mind(None)
    m.possessed = {"A": agents[2].id}
    brain = _brain(2)
    assert m._ai_eligible(w, agents[2], brain)  # the possessed scholar wins a slot
    slot_ids = m._ai_slots[(w.id, brain.id)]["ids"]
    assert agents[2].id in slot_ids and len(slot_ids) == 2
    m.possessed = {}
    m.invalidate_slots("A")
    assert not m._ai_eligible(w, agents[2], brain)  # released: back to scoring


# ---------------------------------------------------------------------------------------------- orders
def test_every_order_gives_real_steps_or_a_clear_error():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.knows["recipe:copper"] = {"how": "discovered", "tick": 0, "status": "worked", "worked_tick": 0}
    a.knows["recipe:iron"] = {"how": "discovered", "tick": 0, "status": "worked", "worked_tick": 0}
    for action in ("mine", "smelt", "forge", "build", "teach", "haul"):
        try:
            plan = orders.order_plan(w, a, action)
        except ValueError:
            continue  # impossible here is fine, as long as it says so
        orders.apply_order(w, a, action, plan)
        assert a.plan_source == "player"
        for s in plan["steps"]:
            assert s["do"] in VERBS
        for s in a.plan:
            assert s["_origin"] == "player"


def test_mine_orders_a_gather_then_a_store():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    plan = orders.order_plan(w, a, "mine")
    assert plan["steps"][0]["do"] == "gather"
    assert plan["steps"][0]["what"] in ("ore", "iron_ore", "stone", "clay", "sand", "wood", "fiber")


def test_teach_orders_a_teach_step():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.knows["recipe:copper"] = {"how": "discovered", "tick": 0, "status": "worked", "worked_tick": 0}
    plan = orders.order_plan(w, a, "teach")
    assert plan["steps"][0]["do"] == "teach"
    assert plan["steps"][0]["to"] in {o.name for o in w.agents.values()}


def test_an_impossible_teach_raises_a_friendly_error():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    other = next(o for o in w.agents.values() if o.id != a.id)
    # give the other chit everything this one knows, plus something more: nothing left to teach it
    a.knows["recipe:copper"] = {"how": "discovered", "tick": 0, "status": "worked", "worked_tick": 0}
    other.knows["recipe:copper"] = {"how": "discovered", "tick": 0, "status": "worked", "worked_tick": 0}
    other.knows["recipe:iron"] = {"how": "discovered", "tick": 0, "status": "worked", "worked_tick": 0}
    try:
        orders.order_plan(w, a, "teach", other.name)
    except ValueError as e:
        assert "already knows" in str(e) or "nothing" in str(e)
    else:
        raise AssertionError("teaching a chit that knows everything should fail")


def test_cancel_clears_the_plan_and_pending_plan():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.plan = [{"do": "build", "what": "forge", "_origin": "player"}]
    a.pending_plan = {"steps": [{"do": "craft", "what": "steel"}], "goal": "make steel"}
    a.objective = "get to the next age"
    orders.apply_order(w, a, "cancel", orders.order_plan(w, a, "cancel"))
    assert a.pending_plan is None
    assert a.objective == ""
    assert all(s.get("do") in orders._ROUTINE for s in a.plan)  # no side-quest steps remain


def test_parse_order_maps_samples_deterministically():
    assert orders.parse_order("mine iron") == ("mine", "iron_ore")
    assert orders.parse_order("dig clay") == ("mine", "clay")
    assert orders.parse_order("smelt copper") == ("smelt", "copper")
    assert orders.parse_order("melt ore") == ("smelt", "copper")
    assert orders.parse_order("make steel") == ("forge", "steel")
    assert orders.parse_order("forge gear") == ("forge", "gear")
    assert orders.parse_order("build the forge") == ("build", "forge")
    assert orders.parse_order("haul") == ("haul", None)
    assert orders.parse_order("carry") == ("haul", None)
    assert orders.parse_order("store") == ("haul", None)
    assert orders.parse_order("stop") == ("cancel", None)
    assert orders.parse_order("cancel") == ("cancel", None)


def test_parse_order_rejects_unknown_text():
    try:
        orders.parse_order("flibbertigibbet")
    except ValueError as e:
        assert "try mine/smelt/forge/build/teach/haul/cancel" in str(e)
    else:
        raise AssertionError("unknown text should raise")


# ---------------------------------------------------------------------------------------------- mind.hook
def test_mind_hook_leaves_an_active_player_plan_alone():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    m = Mind(None)
    m.possessed = {"A": a.id}
    a.plan = [{"do": "gather", "what": "stone", "qty": 3, "_origin": "player"}]
    a.plan_source = "player"
    a.goal = "mine stone"
    m.hook(w, a)
    assert a.plan[0]["_origin"] == "player"
    assert a.plan_source == "player"
    assert a.goal == "mine stone"
    assert a.pending_plan is None


# ---------------------------------------------------------------------------------------------- HTTP contract
def _client(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_MODE", "versus")
    from fastapi.testclient import TestClient

    from chits.app import app

    return TestClient(app)


def _rt():
    from chits.app import R

    return R()


def test_possess_order_and_release_via_the_api(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = _rt()
        wid, aid = "A", next(iter(r.worlds["A"].agents))
        assert c.post(f"/api/worlds/{wid}/agents/{aid}/possess").json() == {"ok": True, "possessed": aid}
        assert c.get(f"/api/worlds/{wid}/possess").json() == {"possessed": aid, "orders": list(orders.ORDERS)}
        got = c.post(f"/api/worlds/{wid}/agents/{aid}/order", json={"action": "mine", "target": "iron_ore"})
        assert got.status_code == 200
        body = got.json()
        assert body["action"] == "mine" and body["steps"]
        assert all("_" not in k for s in body["steps"] for k in s)
        assert body["steps"][0]["do"] in VERBS
        assert r.worlds[wid].agents[aid].plan_source == "player"
        # ordering another chit is refused
        other = next(o for o in r.worlds[wid].agents if o != aid)
        assert c.post(f"/api/worlds/{wid}/agents/{other}/order", json={"action": "mine"}).status_code == 409
        # bad text is a 400
        assert c.post(f"/api/worlds/{wid}/agents/{aid}/order", json={"text": "flibbertigibbet"}).status_code == 400
        # release clears it
        assert c.post(f"/api/worlds/{wid}/possess/release").json() == {"ok": True}
        assert c.get(f"/api/worlds/{wid}/possess").json()["possessed"] is None


def test_an_experiment_refuses_possess_and_order(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/api/reset", json={"mode": "versus", "contract": "experiment"})
        r = _rt()
        assert r.contract == "experiment"
        wid, aid = "A", next(iter(r.worlds["A"].agents))
        assert c.post(f"/api/worlds/{wid}/agents/{aid}/possess").status_code == 409
        assert c.post(f"/api/worlds/{wid}/agents/{aid}/order", json={"action": "mine"}).status_code == 409
        assert r.possessed == {}


def test_a_mine_target_by_plain_name_maps_to_its_item():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    plan = orders.order_plan(w, a, "mine", "iron")
    gathers = [s for s in plan["steps"] if s["do"] == "gather" and s.get("what") == "iron_ore"]
    assert gathers, plan["steps"]


def test_cancel_drops_the_walk_to_a_side_quest_but_keeps_eating():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.plan = [{"do": "go", "to": "10,10"}, {"do": "eat", "what": "berries"}, {"do": "explore"}]
    orders.apply_order(w, a, "cancel", orders.order_plan(w, a, "cancel"))
    assert [s["do"] for s in a.plan] == ["eat"]
    assert a.plan_source == "player"


def test_the_runtime_lets_go_of_a_dead_possessed_chit(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    from chits.runtime import Runtime

    r = Runtime(tmp_path)
    wid, w = next(iter(r.worlds.items()))
    aid = next(iter(w.agents))
    r.possess(wid, aid)
    assert r.possessed_id(wid) == aid
    w.agents.pop(aid)
    assert r.possessed_id(wid) is None and wid not in r.possessed
