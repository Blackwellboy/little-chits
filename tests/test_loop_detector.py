"""The loop detector (research plan item 41): the same step failing for the same reason over and over is a loop. It is
counted by who planned it, so a model comparison sees which one adapts after failure, and in play (never in an
experiment) the chit's next prompt says so."""

from chits import diag
from chits.brain import prompt as P
from chits.sim import actions
from chits.sim.world import World


def setup(n=2):
    w = World("A", "A", 1, "direct", 64, n)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = a.energy = a.warmth = 100
    return w, a


def fail(w, a, n, origin="model_generated", reason="you don't know how", what="spear"):
    for _ in range(n):
        diag.step_failed(w, a, "craft", reason, what, origin)


def test_the_same_failure_n_times_in_a_row_is_one_loop_counted_by_origin():
    w, a = setup()
    fail(w, a, diag.LOOP_N - 1)
    assert not diag.of(w).loops
    fail(w, a, 1)
    assert diag.of(w).loops == {"model": 1}
    fail(w, a, 3)  # still the same loop: counted once
    assert diag.of(w).loops == {"model": 1}
    ex = diag.of(w).loop_examples[-1]
    assert ex["name"] == a.name and "craft spear" in ex["failure"]


def test_a_different_failure_or_a_success_breaks_the_run():
    w, a = setup()
    fail(w, a, diag.LOOP_N - 1)
    fail(w, a, 1, what="bow")  # a different object: not the same step
    fail(w, a, diag.LOOP_N - 1)
    assert not diag.of(w).loops
    diag.step_done(w, a, "gather")
    assert "_loop" not in a.__dict__
    fail(w, a, diag.LOOP_N - 1)
    assert not diag.of(w).loops
    fail(w, a, 1, reason="you're too tired")  # a different reason
    assert not diag.of(w).loops


def test_numbers_in_the_reason_do_not_hide_a_loop():
    w, a = setup()
    for i in range(diag.LOOP_N):
        diag.step_failed(w, a, "take", f"the stockpile has {i} stone", "stone", "model_selected")
    assert diag.of(w).loops == {"model": 1}


def test_instinct_loops_are_kept_apart_from_model_loops():
    w, a = setup()
    fail(w, a, diag.LOOP_N, origin="instinct")
    b = list(w.agents.values())[1]
    fail(w, b, diag.LOOP_N, origin="")
    assert diag.of(w).loops == {"instinct": 2}


def test_run_feeds_the_detector_with_the_plan_origin():
    w, a = setup()
    for _ in range(diag.LOOP_N):
        a.plan = [{"do": "craft", "what": "no_such_thing", "_origin": "model_generated"}]
        for _ in range(50):
            actions.run(w, a)
            w.tick += 1
            if not a.plan:
                break
        assert a.last_result.startswith("Could not"), a.last_result
    assert diag.of(w).loops == {"model": 1}, (diag.of(w).loops, a.last_result)


def test_play_prompts_say_so_and_experiment_prompts_do_not():
    w, a = setup()
    a.last_result = "Could not craft spear: you don't know how"
    fail(w, a, diag.LOOP_N - 1)
    assert "NOTE:" not in P.scene(w, a)
    fail(w, a, 1)
    assert "'craft spear' has now failed 4 times" in P.scene(w, a)
    assert "has now failed 4 times" in P.compact_scene(w, a)
    w.__dict__["_mind_strict"] = True  # an experiment: the model gets the world as it is
    assert "NOTE:" not in P.scene(w, a) and "NOTE:" not in P.compact_scene(w, a)


def test_the_report_carries_the_loops_and_warns_about_a_looping_model(tmp_path):
    import asyncio

    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    w = next(iter(rt.worlds.values()))
    agents = list(w.agents.values())
    for a in agents[:5]:
        fail(w, a, diag.LOOP_N)
    rep = diag.report(rt)
    wd = rep["worlds"][w.id]
    assert wd["loops"] == {"model": 5} and len(wd["loop_examples"]) == 4
    assert any("looped 5 times" in x for x in rep["warnings"]), rep["warnings"]
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_a_new_world_never_inherits_a_freed_worlds_counts():
    import weakref

    old, _ = setup()
    w, a = setup()
    stale = diag.of(old)
    stale.loops["model"] = 9
    diag._DIAG[id(w)] = (weakref.ref(old), stale)  # as if w had been given old's id after old was freed
    assert not diag.of(w).loops


def test_the_mind_tells_the_prompt_whether_this_is_an_experiment():
    from chits.brain.mind import Mind

    w, a = setup()
    m = Mind(None)
    m.upsert({"id": "test", "model": "fake", "base_url": "http://127.0.0.1:9/v1"})
    m.assign(w, "test")
    m._ask = lambda world, agent, brain: None
    for strict in (True, False):
        m.strict = strict
        m.hook(w, a)
        assert w.__dict__["_mind_strict"] is strict
