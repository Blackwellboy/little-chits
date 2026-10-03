"""☑ Milestones: the road to the next age as a checklist, and the events the observer's milestone toasts read."""

from chits import views
from chits.sim import projects
from chits.sim.world import World


def _scribes():
    """A village of scribes that knows bricks and charcoal and has the idea of a furnace, but hasn't built one."""
    w = World("A", "A", 3, "direct", 64, 6)
    chit = next(iter(w.agents.values()))
    w.first["recipe:clay_tablet"] = {"tick": 10, "by": chit.id, "name": chit.name}
    for k in ("recipe:brick", "recipe:charcoal", "design:furnace"):
        chit.learn(k, "taught", 0, None)
    return w, chit


def test_the_road_to_the_next_age_is_a_checklist_of_discover_make_and_build():
    w, chit = _scribes()
    chit.inventory["brick"] = 2
    m = views.progress(w, [])["milestones"]
    assert m["age"] == "Copper Age"
    steps = [(s["action"], s["name"], s["done"], s["detail"]) for s in m["steps"]]
    assert ("discover", "charcoal", True, "") in steps
    assert ("discover", "brick", True, "") in steps
    assert ("make", "brick", False, "2 of 6 for the furnace") in steps
    assert steps[-2:] == [("build", "furnace", False, ""), ("discover", "copper", False, "")]
    assert steps.index(("make", "brick", False, "2 of 6 for the furnace")) < steps.index(("build", "furnace", False, ""))
    assert m["done"] == 2 and m["total"] == len(steps) == 5
    assert {s["key"] for s in m["steps"]} == {"recipe:charcoal", "recipe:brick", "design:furnace", "recipe:copper"}


def test_a_step_is_ticked_off_from_the_worlds_own_state():
    w, chit = _scribes()
    chit.inventory["brick"] = 6  # enough for the furnace: nothing left to make
    m = views.milestones(w, projects.road(w))
    assert not any(s["action"] == "make" for s in m["steps"])
    chit.learn("recipe:copper", "discovered", w.tick, None)
    w.first["recipe:copper"] = {"tick": w.tick, "by": chit.id, "name": chit.name}
    after = views.progress(w, [])["milestones"]
    assert after["age"] == "Iron Age", "the list moves on to the next age once this one is reached"
    assert [(s["action"], s["key"], s["done"]) for s in after["steps"]][-2:] == [
        ("build", "design:furnace", False), ("discover", "recipe:iron", False)]


def test_a_building_nobody_has_imagined_says_so_and_the_last_age_has_no_list():
    w = World("A", "A", 3, "direct", 64, 6)
    chit = next(iter(w.agents.values()))
    w.first["design:farm"] = {"tick": 10, "by": chit.id, "name": chit.name}
    steps = views.progress(w, [])["milestones"]["steps"]  # Farmers -> Potters: a kiln, then the pot
    assert [(s["action"], s["name"]) for s in steps] == [("build", "kiln"), ("discover", "clay pot")]
    assert steps[0]["detail"].startswith("nobody has")
    assert views.milestones(w, None) is None


def test_the_checklist_only_reads_the_world():
    w, chit = _scribes()
    before = (w.tick, w.seq, w.rng.getstate(), dict(chit.inventory), sorted(w.first))
    views.progress(w, [])
    assert before == (w.tick, w.seq, w.rng.getstate(), dict(chit.inventory), sorted(w.first))


def test_the_simulator_already_tells_the_milestones_the_observer_toasts():
    """The observer's milestone toasts (web/src/state/milestones.ts) read these kinds and fields: no new event."""
    w = World("A", "A", 3, "direct", 64, 6)
    a, b = list(w.agents.values())[:2]
    w.learned(a, "recipe:cord", "discovered")
    w.learned(a, "recipe:sharp_stone", "discovered")
    w.learned(a, "recipe:stone_axe", "discovered")
    w.learned(b, "recipe:cord", "taught", a)
    evs = [e.to_dict() for e in w.events]
    firsts = [e for e in evs if e["kind"] == "discovery"]
    assert {"recipe:cord", "recipe:stone_axe"} <= {e["data"]["knowledge"] for e in firsts}
    assert all(e["importance"] == 5 for e in firsts)
    assert [e["actor"] for e in evs if e["data"].get("knowledge") == "recipe:cord"] == [a.id, b.id]
    assert [e["kind"] for e in evs if e["data"].get("knowledge") == "recipe:cord"] == ["discovery", "learned"], \
        "only the first in the world is a discovery"
    era = [e for e in evs if e["kind"] == "era"]
    assert era and era[-1]["data"]["era"] == "Toolmakers" and era[-1]["importance"] == 5
