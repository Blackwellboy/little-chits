"""Regression checks for the independent progression audit; no live model or saved world."""
import asyncio
import json
import random

import pytest

from chits.brain.parse import parse_plan, ParseError
from chits.brain.instinct import Instinct, _supply_steps
from chits.brain.mind import Mind
from chits.brain import prompt
from chits.sim import actions
from chits.sim.world import World


def setup(n=2):
    w = World("A", "A", 1, "direct", 64, n)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = a.energy = a.warmth = 100
    return w, a


def building(w, a, design):
    x, y = w.find_site(design, a.x, a.y)
    st = w.place_site(design, x, y, a)
    w.complete_structure(st, a)
    return st


@pytest.mark.parametrize("bag,expected", [
    ({"ore": 2, "charcoal": 2}, ["ore", "ore", "charcoal", "charcoal"]),
    ({"stone": 2}, ["stone", "stone"]),
    ({"item": "stone", "qty": 2}, ["stone", "stone"]),
])
def test_ingredient_maps_preserve_exact_inputs(bag, expected):
    p = parse_plan(json.dumps({"plan": [{"do": "experiment", "ingredients": bag, "at": "furnace"}]}))
    assert actions._experiment_bag(p["steps"][0]) == expected
    assert p["steps"][0]["at"] == "furnace"


@pytest.mark.parametrize("bag", [{"ore": 0}, {"ore": -1}, {"ore": 1.5}, {"ore": 7}, {"ore": "lots"}])
def test_ambiguous_ingredient_maps_are_rejected(bag):
    with pytest.raises(ParseError):
        parse_plan(json.dumps({"plan": [{"do": "experiment", "with": bag}]}))


def test_craft_fetches_split_inputs_and_restock_for_next_batch():
    w, a = setup()
    one, two = building(w, a, "stockpile"), building(w, a, "stockpile")
    one.storage = {"stone": 1}
    two.storage = {"stone": 3}
    a.learn("recipe:sharp_stone", "taught", w.tick)
    a.plan = [{"do": "craft", "what": "sharp_stone", "qty": 2}]
    for _ in range(300):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    assert a.inventory.get("sharp_stone") == 2, a.last_result
    assert not one.storage and not two.storage


def test_take_fulfils_quantity_across_piles():
    w, a = setup()
    one, two = building(w, a, "stockpile"), building(w, a, "stockpile")
    one.storage = {"stone": 1}
    two.storage = {"stone": 2}
    a.plan = [{"do": "take", "what": "stone", "qty": 3}]
    for _ in range(200):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    assert a.inventory.get("stone") == 3, a.last_result
    assert not one.storage and not two.storage


def test_supply_ledger_reserves_final_inputs_and_accounts_for_yield():
    w, a = setup()
    a.inventory.update(wood=2, clay=1, sand=1)
    for k in ("charcoal", "brick"):
        a.learn("recipe:" + k, "taught", w.tick)
    steps = _supply_steps(a, {"wood": 2, "charcoal": 2, "brick": 2})
    assert steps == [
        {"do": "gather", "what": "wood", "qty": 1},
        {"do": "craft", "what": "charcoal", "qty": 1},
        {"do": "craft", "what": "brick", "qty": 1},
    ]
    assert a.inventory == {"wood": 2, "clay": 1, "sand": 1}
    assert _supply_steps(a, {"engine": 1}) is None
    assert _supply_steps(a, {"wool": 1}) is None


def test_shelter_proposals_do_not_change_home():
    w, a = setup(5)
    st = building(w, a, "hut")
    st.founder = "another"
    for agent in w.agents.values():
        agent.home = st.id
    a.born = -10000
    before = a.home
    for seed in range(40):
        Instinct()._shelter(w, a, random.Random(seed))
        assert a.home == before


def test_a_crowded_out_chit_moves_into_the_home_it_builds():
    w, a = setup(5)
    family = building(w, a, "hut")
    family.founder = "another"
    for agent in w.agents.values():
        agent.home = family.id
    a.born = -10000
    x, y = w.find_site("hut", a.x + 6, a.y)
    new = w.place_site("hut", x, y, a)
    new.builders[a.id] = 30.0
    w.complete_structure(new, a)
    assert a.home == new.id
    # the founder of an uncrowded home stays put
    b = next(o for o in w.agents.values() if o is not a)
    b.born = -10000
    mine = building(w, b, "hut")
    b.home = mine.id
    mine.founder = b.id
    x, y = w.find_site("hut", b.x - 6, b.y)
    other = w.place_site("hut", x, y, b)
    other.builders[b.id] = 30.0
    w.complete_structure(other, b)
    assert b.home == mine.id


def test_unknown_brain_in_strict_mode_waits_without_instinct():
    w, a = setup()
    m = Mind(None)
    m.strict = True
    a.brain = "missing-model"
    a.plan = []
    m.hook(w, a)
    assert not a.plan
    assert a.brain == "missing-model"
    asyncio.run(m.close())


def test_choice_describes_terminal_step_and_station():
    w, a = setup()
    steps = [{"do": "gather", "what": "wood"}] * 5 + [{"do": "experiment", "with": ["ore", "charcoal"], "at": "furnace"}]
    text = prompt.choice_messages(w, a, [{"goal": "test", "steps": steps}])[1]["content"]
    assert "experiment ore + charcoal furnace" in text


def test_epoch_collisions_preserve_both_futures_and_active_restore(tmp_path):
    from chits.store import Store
    w, a = setup()
    store = Store(tmp_path / "world.sqlite")
    old = w.to_dict()
    w.tick = 100
    first = w.emit("note", "abandoned future", 3)
    store.save_world(w.to_dict(), events=[first])
    store.save_keyframe("A", 100, {"future": "old"}, w.uuid, w.epoch)
    old_epoch = w.epoch
    restored = World.from_dict(old)
    restored.fork_epoch("test restore")
    restored.seq = first.seq - 1
    second = restored.emit("note", "selected future", 3)
    assert second.seq == first.seq
    store.save_world(restored.to_dict(), events=[second])
    store.save_keyframe("A", 100, {"future": "new"}, restored.uuid, restored.epoch)
    assert store.events("A", epoch=old_epoch)[0]["text"] == "abandoned future"
    assert store.events("A", epoch=restored.epoch)[0]["text"] == "selected future"
    store.db.close()
    store = Store(tmp_path / "world.sqlite")
    assert store.load_world("A")["epoch"] == restored.epoch
    assert store.load_world("A")["tick"] == old["tick"]
    assert store.keyframes("A", epoch=old_epoch) == [{"future": "old"}]
    assert store.keyframes("A", epoch=restored.epoch) == [{"future": "new"}]
    store.db.close()


def test_action_outcomes_keep_only_the_last_week(tmp_path):
    from chits.store import Store, OUTCOME_TICKS
    store = Store(tmp_path / "world.sqlite")
    w, _ = setup()
    row = lambda t: {"tick": t, "plan_id": f"p{t}", "outcome": "executed"}
    store.save_world(w.to_dict(), outcomes=[row(0), row(10)])
    w.tick = OUTCOME_TICKS + 5
    store.save_world(w.to_dict(), outcomes=[row(w.tick)])
    assert [r["tick"] for r in store.action_outcomes("A")] == [OUTCOME_TICKS + 5, 10]
    store.db.close()


def test_checkpoint_rolls_back_state_events_and_active_pointer(tmp_path, monkeypatch):
    from chits.store import Store
    store = Store(tmp_path / "world.sqlite")
    w, _ = setup()
    store.save_world(w.to_dict())
    w.tick = 20
    ev = w.emit("note", "must not be committed", 3)
    original = store._insert_events
    def crash(identity, events):
        original(identity, events)
        raise RuntimeError("simulated interrupted checkpoint")
    monkeypatch.setattr(store, "_insert_events", crash)
    with pytest.raises(RuntimeError):
        store.save_world(w.to_dict(), events=[ev])
    assert store.load_world("A")["tick"] == 0
    assert not store.events("A")
    store.db.close()


def test_legacy_database_migration_preserves_snapshot_and_events(tmp_path):
    import sqlite3
    import gzip
    from chits.store import Store, SCHEMA
    path = tmp_path / "legacy.sqlite"
    w, _ = setup()
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO snapshots(world_id,tick,data) VALUES (?,?,?)", ("A", 0, gzip.compress(json.dumps(w.to_dict()).encode())))
    db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", ("A", 1, 0, "note", 3, None, "legacy evidence", "{}"))
    db.commit()
    db.close()
    store = Store(path)
    assert store.load_world("A")["uuid"] == w.uuid
    assert store.events("A")[0]["text"] == "legacy evidence"
    assert store.get_meta("schema_version") == "3"
    store.db.close()


def test_action_provenance_survives_checkpoint(tmp_path):
    from chits.runtime import Runtime
    rt = Runtime(tmp_path)
    w = rt.worlds["A"]
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["stone"] = 2
    a.learn("recipe:sharp_stone", "taught", w.tick)
    a.plan_id = "plan-test"
    a.plan = [{"do": "craft", "what": "sharp_stone", "_origin": "model_generated", "_decision_id": "request-test"}]
    for _ in range(50):
        actions.run(w, a)
        w.tick += 1
        if not a.plan:
            break
    rt.save_all()
    rows = rt.store.action_outcomes("A", "plan-test")
    assert len(rows) == 1 and rows[0]["decision_id"] == "request-test"
    assert rows[0]["source"] == "model_generated" and rows[0]["outcome"] == "executed"
    assert a.inventory["sharp_stone"] == 1
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_roads_and_known_unworked_recipes_remain_visible():
    from chits.diag import opportunities, capability_use
    w, a = setup()
    w.roads.add(a.y * w.w + a.x)
    a.learn("recipe:iron", "taught", w.tick)
    w.first["recipe:iron"] = {"tick": 0}
    assert "design:road" not in opportunities(w)
    assert capability_use(w)["recipe:iron"] == {"known_by": 1, "worked_by": 0, "held_units": 0, "stored_units": 0}


def test_invalid_choice_is_not_a_successful_option_a():
    w, a = setup()
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "choose"})
    m.assign(w, "test")
    brain = m.brains["test"]
    async def reply(messages, **kw):
        messages()
        return {"text": "?", "latency_ms": 1, "top_logprobs": {}}
    brain.chat = reply
    async def run():
        m._ask(w, a, brain)
        await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())
    assert not a.pending_plan
    assert brain.stats.parse_failed == 1
    assert m.decisions[-1]["outcome"] == "failed"


def test_cascade_records_both_requests_and_correct_full_prompt():
    import hashlib
    w, a = setup()
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1", "prompt_style": "cascade"})
    m.assign(w, "test")
    brain = m.brains["test"]
    prompts = []
    async def reply(messages, **kw):
        msgs = messages() if callable(messages) else messages
        prompts.append(msgs)
        if kw.get("max_tokens") == 1:
            own = next(line[0] for line in msgs[1]["content"].splitlines() if line.endswith("my own idea"))
            return {"text": own, "latency_ms": 5, "tokens_in": 100, "tokens_out": 1, "top_logprobs": {own: -0.1}}
        return {"text": '{"plan":[{"do":"rest"}]}', "latency_ms": 40, "tokens_in": 800, "tokens_out": 20}
    brain.chat = reply
    async def run():
        m._ask(w, a, brain)
        while m._tasks:
            await asyncio.gather(*list(m._tasks))
        await m.close()
    asyncio.run(run())
    rec = m.decisions[-1]
    assert rec["style"] == "cascade-full" and rec["max_tokens"] == brain.cfg.max_tokens
    assert rec["prompt_hash"] == hashlib.sha256(json.dumps(prompts[1], sort_keys=True).encode()).hexdigest()[:16]
    assert rec["choice"]["tokens_out"] == 1 and rec["tokens_out"] == 20
    assert rec["choice"]["escalated"] is True


@pytest.mark.asyncio
async def test_cancelled_queued_request_does_not_leak_queue_count():
    from chits.brain.llm import LLMBrain, BrainConfig
    brain = LLMBrain(BrainConfig(id="test", base_url="http://127.0.0.1:9/v1", max_concurrency=1))
    await brain.sem.acquire()
    task = asyncio.create_task(brain.chat([]))
    await asyncio.sleep(0)
    assert brain.stats.queued == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert brain.stats.queued == 0
    brain.sem.release()
    await brain.close()


@pytest.mark.parametrize("ingredients", [[{"item": "wood", "qty": 4}], ["4 wood"], {"wood": 4}])
def test_four_units_are_not_silently_clamped_to_three(ingredients):
    p = parse_plan(json.dumps({"plan": [{"do": "experiment", "with": ingredients}]}))
    assert actions._experiment_bag(p["steps"][0]) == ["wood"] * 4


def test_unknown_experiment_station_is_not_silently_ignored():
    w, a = setup()
    a.inventory["stone"] = 2
    result = actions._do_experiment(w, a, {"do": "experiment", "with": ["stone", "stone"], "at": "volcano"}, {})
    assert "not a known kind of station" in result
    assert a.inventory["stone"] == 2


def test_progression_report_reads_checkpoint_without_writing(tmp_path):
    from chits.store import Store
    from chits.tools.progression_report import report
    w, a = setup()
    a.learn("recipe:iron", "taught", 0)
    pile = building(w, a, "stockpile")
    pile.storage["iron"] = 2
    path = tmp_path / "audit.sqlite"
    store = Store(path)
    store.save_world(w.to_dict())
    store.db.close()
    before = path.read_bytes()
    result = report(path)
    assert result["capabilities"]["recipe:iron"]["stored_units"] == 2
    assert result["capabilities"]["recipe:iron"]["worked_by"] == 0
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_logprobs_unsupported_server_is_negotiated_once():
    import httpx
    from chits.brain.llm import LLMBrain, BrainConfig
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if "logprobs" in body:
            return httpx.Response(400, text="unsupported parameter: logprobs")
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}], "usage": {"completion_tokens": 1}})
    brain = LLMBrain(BrainConfig(id="test", model="fake", base_url="http://fake/v1"))
    brain._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    for _ in range(2):
        result = await brain.chat([], max_tokens=1, json_reply=False, extra={"logprobs": True, "top_logprobs": 10})
        assert result["text"] == "A" and result["queue_ms"] >= 0
    assert len(seen) == 3 and sum("logprobs" in b for b in seen) == 1
    await brain.close()


def test_corrupt_saved_blob_is_quarantined_in_play(tmp_path):
    from chits.runtime import Runtime
    rt = Runtime(tmp_path)
    rt.save_all()
    rt.store.db.execute("UPDATE snapshots SET data=? WHERE world_id='A'", (b"broken gzip",))
    rt.store.db.commit()
    rt.store.db.close()
    asyncio.run(rt.mind.close())
    recovered = Runtime(tmp_path)
    assert recovered.store.db.execute("SELECT count(*) FROM quarantine WHERE world_id='A'").fetchone()[0] > 0
    assert any(e.kind == "notice" for e in recovered.worlds["A"].events)
    recovered.store.db.close()
    asyncio.run(recovered.mind.close())


def test_a_timeline_reads_its_ancestors_up_to_each_fork():
    from chits.store import Store
    import tempfile, pathlib
    w, _ = setup()
    store = Store(pathlib.Path(tempfile.mkdtemp()) / "t.sqlite")
    e0 = w.epoch
    w.tick = 40
    kept = w.emit("note", "kept from the first timeline", 3)
    store.append_events(w, [kept])
    w.tick = 60
    store.append_events(w, [w.emit("note", "an abandoned future", 3)])
    # restored to a checkpoint taken at tick 50 (its event counter comes back with it): what happened at 60 in the
    # old timeline never happened in this one
    w.tick, w.seq = 50, kept.seq
    e1 = w.fork_epoch("restored")
    w.tick = 70
    store.append_events(w, [w.emit("note", "the new future", 3)])
    assert w.timeline() == [(e1, None), (e0, (kept.seq, 50))]
    texts = [e["text"] for e in store.events("A", epoch=w.timeline(), limit=50)]
    assert "kept from the first timeline" in texts and "the new future" in texts
    assert "an abandoned future" not in texts
    # one epoch by id is still that epoch alone (F3)
    assert all(e["text"] != "kept from the first timeline" for e in store.events("A", epoch=e1, limit=50))
    w.tick = 90
    seq = w.seq
    e2 = w.fork_epoch("again")
    assert w.timeline() == [(e2, None), (e1, (seq, 90)), (e0, (kept.seq, 50))]
    # a fork recorded before seq was kept falls back to its tick
    for e in w.epochs:
        e.pop("from_seq", None)
    texts = [e["text"] for e in store.events("A", epoch=w.timeline(), limit=50)]
    assert "kept from the first timeline" in texts and "an abandoned future" not in texts
    store.db.close()


def test_history_survives_a_restart_after_a_crash(tmp_path):
    from chits.runtime import Runtime
    rt = Runtime(tmp_path)
    w = rt.worlds["A"]
    w.tick = 100
    w.emit("note", "before the last checkpoint", 3)
    rt.save_all()
    w.tick = 130
    rt.store.append_events(w, [w.emit("note", "after it, then the power went out", 3)])
    rt.store.db.close()
    asyncio.run(rt.mind.close())
    back = Runtime(tmp_path)
    w2 = back.worlds["A"]
    assert w2.tick == 100 and w2.epoch != w.epoch  # resumed from the checkpoint on a new timeline
    texts = [e["text"] for e in back.store.events("A", epoch=w2.timeline(), limit=500)]
    assert "before the last checkpoint" in texts and "after it, then the power went out" not in texts
    back.store.db.close()
    asyncio.run(back.mind.close())


def test_the_chronicle_api_keeps_the_days_before_a_crash(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from chits.runtime import Runtime
    rt = Runtime(tmp_path)
    w = rt.worlds["A"]
    w.tick = 100
    w.emit("note", "before the last checkpoint", 3)
    rt.save_all()
    w.tick = 130
    rt.store.append_events(w, [w.emit("note", "after it, then the power went out", 3)])
    rt.store.db.close()
    asyncio.run(rt.mind.close())
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    monkeypatch.setenv("CHITS_SPEED", "0")
    from chits import app as APP
    with TestClient(APP.app) as c:
        texts = [e["text"] for e in c.get("/api/worlds/A/events", params={"limit": 500}).json()]
    # told once: the snapshot's own events are not copied into the new timeline
    assert texts.count("before the last checkpoint") == 1 and "after it, then the power went out" not in texts
