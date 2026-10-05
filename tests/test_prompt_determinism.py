"""A prompt is the same text in every process: nothing in it may follow string hashing (set order). The Lab seeds each
request from the exact prompt, so a prompt that changed with PYTHONHASHSEED changed the run. And a reply cut off
mid-JSON, which the parser closes, is counted as repaired."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from chits.brain import parse as PR
from chits.brain.llm import BrainStats
from chits.brain.mind import Mind
from chits.sim.world import World

SERVER = Path(__file__).resolve().parents[1] / "server"

# Builds every prompt for one chit whose neighbours share many failed experiments, tried once each (all tied), and
# who has met several faiths with the same number of followers (all tied).
SCRIPT = r"""
import json
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim.world import World

w = World("A", "A", 5, "direct", 64, 4)
a, *others = list(w.agents.values())
for o in others:
    o.x, o.y = a.x, a.y
tried = [f"{x} + {y}" for x in ("stone", "wood", "clay", "sand", "plant fiber") for y in ("seeds", "berries", "cord")]
for i, o in enumerate(others):
    o.failed_experiments = tried[i::len(others)] + tried[:3]
w.beliefs = {f"b{i}": {"id": f"b{i}", "name": f"The Way {i}", "tenet": f"Tenet number {i} holds.", "founder": others[0].id,
                       "founder_name": others[0].name, "followers": [others[0].id]} for i in range(8)}
a.met_beliefs = sorted(w.beliefs)
opts = Instinct().options(w, a)
out = {"full": P.messages(w, a), "compact": P.messages(w, a, style="compact"),
       "choice": P.choice_messages(w, a, opts, own_idea=True), "reflection": P.reflection_messages(w, a)}
print(json.dumps(out))
"""


def _prompts(hashseed: str) -> dict:
    env = dict(os.environ, PYTHONHASHSEED=hashseed, PYTHONPATH=str(SERVER))
    r = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, cwd=SERVER, env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_same_prompts_under_two_string_hash_seeds():
    one, two = _prompts("1"), _prompts("2")
    assert "Others around here already tried these" in one["full"][1]["content"]  # (the tied lines are in it)
    assert "The Way" in one["reflection"][1]["content"]
    for kind in one:
        assert one[kind] == two[kind], kind


def test_a_truncated_reply_is_counted_as_repaired():
    whole = '{"thought": "x", "goal": "g", "plan": [{"do": "gather", "what": "wood", "qty": 6}, {"do": "store"}]}'
    cut = whole[:70]  # ran out of tokens inside the first step
    assert PR.parse_plan(whole)["repaired"] is False
    p = PR.parse_plan(cut)
    assert p["repaired"] is True and p["steps"] == [{"do": "gather", "what": "wood"}]  # (the qty was cut off)
    fenced = PR.parse_plan("```json\n" + cut)  # (cut inside a code fence too)
    assert fenced["repaired"] is True


def test_a_whole_object_repeated_and_cut_off_is_not_repaired():
    """A reply with a whole object, then the same object again cut off before its last brace: closing the second
    gives the first one's text exactly. The whole first object is what parsed, so nothing was repaired."""
    whole = '{"thought": "x", "goal": "g", "plan": [{"do": "gather", "what": "wood", "qty": 6}]}'
    assert PR._close_truncated(whole[:-1]) == whole  # (the case: the same text both ways)
    for reply in (whole + "\n" + whole[:-1], "```json\n" + whole + "\n```\n" + whole[:-1]):
        p = PR.parse_plan(reply)
        assert p["repaired"] is False and p["steps"] == [{"do": "gather", "what": "wood", "qty": 6}], reply
    assert PR.parse_plan(whole[:-1])["repaired"] is True  # (alone, the cut-off one still counts)


def test_the_mind_counts_a_truncated_reply_as_repaired():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    cut = '{"thought": "x", "goal": "g", "plan": [{"do": "gather", "what": "wood", "qty": 6}, {"do": "sto'

    class Brain:
        id = label = "stub"
        stats = BrainStats()

        async def chat(self, msgs, **kw):
            return {"text": cut, "latency_ms": 1.0, "tokens_in": 1, "tokens_out": 1}

    b, rec = Brain(), {"outcome": "pending", "rev_requested": a.rev, "tick_requested": w.tick}
    asyncio.run(Mind(None)._think(w, a, b, [{"role": "user", "content": "?"}], rec))
    assert rec["parse"] == "repaired" and b.stats.repaired == 1
    assert a.pending_plan["steps"] == [{"do": "gather", "what": "wood", "qty": 6}]
