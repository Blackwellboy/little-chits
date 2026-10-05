"""The harness's model-in-the-loop check (tools/harness/mindrun.py, scripted.py): a world driven through the game's
Mind by the scripted model, with no GPU and no network, and the ModelProbe that counts what the model path did."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chits.sim.world import World

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "harness"))
import mindrun  # noqa: E402
import scripted  # noqa: E402


def _short(**kw):
    opts = dict(seed=3, days=1, size=64, chits=6)
    opts.update(kw)
    return mindrun.run_world(opts.pop("seed"), opts.pop("days"), **opts)


def test_the_scripted_mind_runs_a_short_world_through_the_model_path():
    w, p, mp, low, r = _short()
    assert w.tick == 240
    b = r["brain"]["scripted"]
    assert b["requests"] > 0 and b["failed"] == 0  # every request answered, none over a network
    assert r["decisions"].get("outcome:adopted", 0) > 0
    assert r["decisions"].get("style:choose", 0) > 0  # the cascade's one-letter choices ...
    assert r["escalation"].get("granted", 0) > 0 and r["decisions"].get("style:cascade-full", 0) > 0  # ... and its full plans
    assert r["decisions"].get("parse:invalid_choice", 0) > 0  # the planted bad letters were seen as bad
    src = r["steps_by_source"]
    assert src.get("model_selected", 0) > 0 and src.get("model_generated", 0) > 0
    assert r["model_steps"]["ok"] > 0
    assert sum(r["planted"].values()) > 0


def test_a_full_prompt_run_parses_retries_and_repairs():
    _, _, _, _, r = _short(style="full", bad_rate=0.5, bad_kinds=("prose", "unknown_verb", "cant_run"))
    b = r["brain"]["scripted"]
    assert b["retries"] > 0  # prose has no JSON: the mind asks again
    assert r["rejected_steps"] > 0  # a verb that doesn't exist is dropped from the plan
    assert r["repairs"]["asked"] > 0  # a model step that failed is put back to the model with its reason
    assert r["model_steps"]["failed_at_once"] > 0 and r["failed_at_once_by_verb"]


def test_a_planted_what_none_step_is_counted_as_a_failure_loop():
    _, _, mp, _, r = _short(style="full", bad_rate=1.0, bad_kinds=("none_what",))
    loops = [L for L in r["loops"] if L["origin"] == "model" and L["failure"].startswith("gather None |")]
    assert loops and loops[0]["longest"] > mindrun.LOOP_AFTER
    assert r["model_loops"] >= loops[0]["episodes"] >= 1
    assert r["failed_at_once_by_verb"].get("gather", 0) > 0
    assert "gather None" in mp.autopsy_text()  # the autopsy shows the plan, its source, the step and the result
    assert "plan:" in mp.autopsy_text() and "source model_" in mp.autopsy_text()


def test_the_loop_count_needs_more_than_n_failures_in_a_row():
    w = World("A", "A", 1, "direct", 64, 2)
    a = next(iter(w.agents.values()))

    class _Mind:
        on_decision = None
        brains = {}

    mp = mindrun.ModelProbe(w, _Mind(), loop_after=3)
    step = {"do": "gather", "what": None, "_origin": "model_generated", "_tick_started": w.tick}
    for _ in range(3):
        mp._finished(a, dict(step), "None can't be gathered from the land")
    assert not mp.loops  # three in a row is not more than three
    mp._finished(a, dict(step), "None can't be gathered from the land")
    (L,) = mp.loops.values()
    assert L["failure"] == "gather None | None can't be gathered from the land" and L["longest"] == 4
    mp._finished(a, {"do": "rest", "_origin": "model_generated"}, "done")
    for _ in range(4):
        mp._finished(a, dict(step), "None can't be gathered from the land")
    assert L["episodes"] == 2  # a success in between ends the run of failures


def test_metrics_are_deterministic_for_a_seed():
    one = _short(seed=5)
    two = _short(seed=5)
    assert one[4] == two[4]
    assert (one[0].tick, len(one[0].agents), len(one[0].first)) == (two[0].tick, len(two[0].agents), len(two[0].first))
    other = _short(seed=6)
    assert other[4] != one[4]


def test_run_py_mind_rows_are_the_same_in_two_processes():
    """run.py pins the string hash for a --mind run: a prompt's text depends on it (world.village_failed)."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    cmd = [sys.executable, str(ROOT / "tools" / "harness" / "run.py"), "4", "--days", "1", "--size", "64", "--chits",
           "6", "--mind", "scripted"]
    rows = [subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300) for _ in range(2)]
    for r in rows:
        assert r.returncode == 0, r.stderr[-2000:]
    a, b = (json.loads(r.stdout.strip().splitlines()[-1]) for r in rows)
    assert a == b and a["mind"]["brain"]["scripted"]["requests"] > 0
    assert a["mind"]["hashseed"] == "0"


def test_a_reply_takes_the_ticks_it_is_given():
    """The world waits for every request to reach the reply clock before it steps on: a quick reply never leaves a
    chit idle long enough for instinct to fill in, a slow one does."""
    quick = _short(style="full", bad_rate=0, plan_ticks=1)[4]
    slow = _short(style="full", bad_rate=0, plan_ticks=30)[4]
    assert quick["plans"].get("filler", 0) == 0 and quick["plans"].get("model", 0) > 0
    assert slow["plans"].get("filler", 0) > 0
    three = _short(style="full", bad_rate=0, plan_ticks=3)[4]
    assert list(three["reply_ticks"]) == ["3"]  # every answer exactly three ticks after the chit's mind was asked
    mp = _short(style="full", bad_rate=0, plan_ticks=3, slots=1)[2]  # one slot: the first plans all queue at once ...
    first = [t for t, kind in mp.transport.received[:4]]
    assert first == [first[0], first[0] + 3, first[0] + 6, first[0] + 9]  # ... and each is sent as the one before ends


def test_never_a_real_server_by_default():
    sys.path.insert(0, str(ROOT / "tools" / "harness"))
    import run as R

    src = (ROOT / "tools" / "harness" / "run.py").read_text()
    assert '"--mind", default=""' in src  # no --mind: instinct only, no brain at all
    with pytest.raises(ValueError):
        mindrun.run_world(1, 1, mind="rtx5090")  # a brain id or a typo is refused, never guessed at
    row, p = R.run(2, 0, 64, 4)
    assert "mind" not in row and p.mind is None


def test_scripted_answers_are_seeded_by_the_request():
    body = {"max_tokens": 600, "messages": [{"role": "system", "content": "s"},
                                            {"role": "user", "content": "Hunger 20/100\nCarrying (2/12): 2 berries.\n"}]}
    a, b = scripted.ScriptedModel(seed=1, bad_rate=0), scripted.ScriptedModel(seed=1, bad_rate=0)
    ra, rb = a.respond(body), b.respond(body)
    assert ra == rb
    plan = json.loads(ra["choices"][0]["message"]["content"])
    assert plan["plan"][0] == {"do": "eat", "what": "berries"}  # hungry with food in hand: eat it
    with pytest.raises(ValueError):
        scripted.ScriptedModel(bad_kinds=("no_such_kind",))
