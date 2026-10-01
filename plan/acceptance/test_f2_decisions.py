import asyncio
import json

from chits.brain import prompt as P
from chits.brain.mind import Mind
from chits.brain.parse import parse_plan
from chits.sim.world import World


def test_objective_parse_and_scene():
    p = parse_plan(json.dumps({"objective": "Somewhere warm before winter", "goal": "get wood",
                               "steps": [{"do": "gather", "what": "wood"}]}))
    assert p["objective"] == "Somewhere warm before winter"
    assert parse_plan(json.dumps({"goal": "x", "steps": [{"do": "rest"}]}))["objective"] == ""
    w = World("A", "A", 3, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.objective, a.objective_since = "Somewhere warm before winter", 0
    assert "YOUR OBJECTIVE" in P.scene(w, a) and "Somewhere warm" in P.scene(w, a)
    r0 = a.rev
    w.learned(a, "recipe:cord", "discovered")
    assert a.rev > r0


async def _drive(world, mind, ticks):
    for _ in range(ticks):
        world.step(mind.hook)
        await asyncio.sleep(0.004)


async def test_records_adoption_and_staleness(fake_llm_url):
    w = World("A", "A", 5, "direct", 64, 4)
    mind = Mind(None)
    mind.upsert({"id": "fake", "base_url": fake_llm_url, "max_concurrency": 8})
    mind.assign(w, "fake")
    seen = []
    mind.on_decision = seen.append
    await _drive(w, mind, 150)
    recs = list(mind.decisions)
    assert recs and seen
    r = recs[0]
    for k in ("request_id", "world", "agent", "brain", "model", "base_url", "tick_requested", "rev_requested",
              "prompt_version", "prompt_hash", "temperature", "max_tokens", "latency_ms", "tokens_out",
              "response_hash", "parse", "outcome"):
        assert k in r, k
    assert any(x["outcome"] == "adopted" for x in recs)
    adopted = [a for a in w.agents.values() if a.plan_source == "model:fake"]
    assert adopted and all(a.plan_id for a in adopted)
    # a plan that arrives after the chit's situation changed is dropped as stale
    target = None
    for _ in range(200):
        await _drive(w, mind, 1)
        target = next((a for a in w.agents.values() if a.pending_plan is not None), None)
        if target:
            break
    assert target is not None
    target.bump_rev()
    target.plan = []
    mind.hook(w, target)
    assert any(x["agent"] == target.id and x["outcome"] == "stale" for x in mind.decisions)
    await mind.close()
