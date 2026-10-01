"""Great works: a great library, a lighthouse and an aqueduct. Each needs a big village, and each really does
something: study goes twice as far, voyages take half the time, fields near the water keep growing through a drought."""

from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import projects, research
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS
from chits.sim.world import World


def _village(n=30):
    w = World("A", "A", 5, "direct", 128, n)
    for o in w.agents.values():
        o.hunger = o.energy = o.warmth = 95.0
    w.tick = TICKS_PER_DAY + 60
    return w, next(iter(w.agents.values()))


def _put(w, a, design, near=None, radius=8):
    x, y = near or (a.x, a.y)
    s = w.place_site(design, *w.find_site(design, x, y, radius, reach=(a.x, a.y)), a)
    w.complete_structure(s, a)
    w.__dict__.pop("_bfx", None)  # (the buildings' effects are looked up once a tick; this is the same tick)
    return s


def test_a_great_work_needs_a_big_village():
    w, a = _village(3)
    a.learn("design:lighthouse", "insight", w.tick)
    a.inventory.update({"stone": 20, "wood": 10, "glass": 4, "copper": 2})
    msg = actions.advance(w, a, {"do": "build", "what": "lighthouse"})
    assert "great work" in msg and str(DESIGNS["lighthouse"].min_pop) in msg
    assert all(DESIGNS[k].min_pop >= 20 for k in ("great_library", "lighthouse", "aqueduct"))


def test_a_lighthouse_stands_on_the_shore_and_halves_a_voyage():
    w, a = _village()
    b = next(o for o in w.agents.values() if o is not a)
    w.depart(b)
    assert w.outbox[-1]["arrive_tick"] - w.tick == 120
    lh = _put(w, a, "lighthouse", radius=60)
    assert w.coastal(lh.x, lh.y)
    c = next(o for o in w.agents.values() if o is not a)
    w.depart(c)
    assert w.outbox[-1]["arrive_tick"] - w.tick == 60


def test_study_near_a_great_library_goes_twice_as_far():
    w, a = _village()
    before = research.study_gain(w, a, 5)
    _put(w, a, "great_library")
    assert research.study_gain(w, a, 5) == round(before * BLD.STUDY_MULT, 2)
    far = next(o for o in w.agents.values() if o is not a)
    far.x, far.y = min(w.w - 2, a.x + BLD.LIBRARY_REACH + 20), a.y
    assert BLD.study_mult(w, far) == 1.0


def test_fields_an_aqueduct_reaches_grow_faster_and_through_a_drought():
    w, a = _village()
    near = _put(w, a, "farm")
    far = _put(w, a, "farm", near=(min(w.w - 10, a.x + 45), a.y), radius=20)
    for f in (near, far):
        f.planted, f.growth = True, 0.0
    base = BLD.growth_mult(w, near)
    _put(w, a, "aqueduct", near=(near.x, near.y), radius=12)
    assert BLD.growth_mult(w, near) == base * BLD.AQUEDUCT_GROWTH and BLD.growth_mult(w, far) == BLD.growth_mult(w, far)
    w.weather = "drought"
    for _ in range(20):
        w.tick += 1
        w._structure_tick(near, False)
        w._structure_tick(far, False)
    assert near.growth > 0 and far.growth == 0


def test_a_big_village_can_take_on_a_great_work_as_its_project():
    w, a = _village()
    for k in ("recipe:brick", "recipe:clay_tablet", "design:great_library"):  # (its materials must be makeable)
        a.learn(k, "insight", w.tick)
    assert ("build", "great_library") in {(c[1], c[2]) for c in projects.candidates(w)}
    w2, b = _village(10)
    for k in ("recipe:brick", "recipe:clay_tablet", "design:great_library"):
        b.learn(k, "insight", w2.tick)
    assert ("build", "great_library") not in {(c[1], c[2]) for c in projects.candidates(w2)}
