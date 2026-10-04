"""The self-reporting test harness (tools/harness): its preventable-death autopsy, stuck detector and fired counters,
on small worlds over a few hundred ticks."""

import sys
from pathlib import Path

from chits import diag
from chits.sim.world import World

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "harness"))
import probe as P  # noqa: E402


def village(n=2, seed=1):
    w = World("A", "A", seed, "direct", 64, n)
    ags = list(w.agents.values())
    for a in ags:
        a.plan = []
        a.inventory.clear()
    return w, ags


def store_for(w, a, food=0):
    a.learn("design:stockpile", "taught", w.tick)
    pos = w.find_site("stockpile", a.x, a.y)
    st = w.place_site("stockpile", pos[0], pos[1], a)
    w.complete_structure(st, a)
    st.storage.clear()
    if food:
        st.storage["berries"] = food
    return st


class Brain:
    """A planner that hands out the same plan every time it is asked."""

    def __init__(self, *plans):
        self.plans, self.n = plans, 0

    def plan(self, world, a):
        p = self.plans[self.n % len(self.plans)]
        self.n += 1
        return {"goal": p[0], "steps": [dict(s) for s in p[1]]}


def starve(w, p, a):
    a.hunger = 0.0
    p.after_tick()  # (what it was doing goes into its ring buffer)
    w.kill(a, "starvation")


def test_a_starved_chit_beside_a_store_with_food_is_a_preventable_death():
    w, (a, _) = village()
    p = P.Probe(w, Brain(("rest", [{"do": "rest"}])))
    st = store_for(w, a, food=8)
    starve(w, p, a)
    r = p.report()
    assert r["preventable"] == 1
    death = p.starved[0]
    assert death["preventable"] and death["store"]["id"] == st.id and death["store"]["food"] == 8
    assert death["buffer"] and death["buffer"][-1]["store"]["id"] == st.id
    assert "PREVENTABLE" in p.autopsy_text()


def test_a_starved_chit_with_no_food_on_its_land_is_not_flagged():
    w, (a, b) = village()
    p = P.Probe(w, Brain(("rest", [{"do": "rest"}])))
    store_for(w, a)  # a store, but nothing to eat in it
    starve(w, p, a)
    st = store_for(w, b, food=8)
    w.same_land = lambda who, s: False  # food in a store, but across the water
    starve(w, p, b)
    assert len(p.starved) == 2 and p.report()["preventable"] == 0
    assert st.storage["berries"] == 8


def test_food_further_than_thirty_tiles_away_is_not_flagged():
    w, (a, _) = village()
    p = P.Probe(w, Brain(("rest", [{"do": "rest"}])))
    st = store_for(w, a, food=8)
    a.x, a.y = next((x, y) for y in range(w.h) for x in range(w.w)
                    if w.passable(x, y) and st.dist(x, y) > P.PREVENTABLE_NEAR + 2)
    starve(w, p, a)
    assert len(p.starved) == 1 and p.report()["preventable"] == 0


def test_only_starvation_is_autopsied():
    w, (a, _) = village()
    p = P.Probe(w, Brain(("rest", [{"do": "rest"}])))
    store_for(w, a, food=8)
    w.kill(a, "old age")
    assert p.starved == [] and p.fired()["death"] == 1 and p.breakdown()["death"] == {"old age": 1}


def run(w, p, ticks):
    with p:
        for _ in range(ticks):
            w.step(p.hook)
            p.after_tick()


def test_a_chit_replanning_the_same_failing_goal_is_stuck():
    w, (a,) = village(1)
    p = P.Probe(w, Brain(("fetch the moon", [{"do": "pickup", "what": "moon"}])))
    run(w, p, 40)
    r = p.report()
    assert r["stuck"] == 1 and r["stuck_episodes"] == 1
    assert p.stuck[0]["goal"] == "fetch the moon" and p.stuck[0]["times"] > P.STUCK_AFTER + 1
    assert "fetch the moon" in p.autopsy_text()
    assert diag.action_finished is p._orig  # (the probe puts the game's own hook back)


def test_failing_under_different_goals_is_not_stuck():
    w, (a,) = village(1)
    p = P.Probe(w, Brain(("fetch the moon", [{"do": "pickup", "what": "moon"}]),
                         ("fetch the sun", [{"do": "pickup", "what": "sun"}])))
    run(w, p, 40)
    r = p.report()
    assert r["stuck"] == 0 and r["fail_streaks"].get("1", 0) > P.STUCK_AFTER + 1


def test_a_later_step_failing_is_not_a_failing_first_step():
    w, (a,) = village(1)
    p = P.Probe(w, Brain(("fetch the moon", [{"do": "say", "what": "hi"}, {"do": "pickup", "what": "moon"}])))
    run(w, p, 80)
    assert a.stats.get("failures", 0) > P.STUCK_AFTER + 1
    assert p.report()["stuck"] == 0 and p.report()["fail_streaks"] == {}


def test_the_counters_count_a_craft_and_a_build():
    w, (a, b) = village()
    p = P.Probe(w, Brain(("make cord", [{"do": "craft", "what": "cord"}]), ("rest", [{"do": "rest"}])))
    assert "craft" in p.report()["never_fired"] and "build" in p.report()["never_fired"]
    a.learn("recipe:cord", "taught", w.tick)
    a.inventory["fiber"] = 2
    run(w, p, 60)
    assert a.stats.get("made_cord") == 1
    fired, by = p.fired(), p.breakdown()
    assert fired["craft"] == 1 and by["craft"] == {"cord": 1}
    store_for(w, b)
    assert p.fired()["build"] == 1 and p.breakdown()["build"] == {"stockpile": 1}
    never = p.report()["never_fired"]
    assert "craft" not in never and "build" not in never and "invention" in never
