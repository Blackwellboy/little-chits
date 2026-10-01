"""Whole-run totals don't come from the recent-event window (audit F6): World.events keeps the last 4,000 events for
the viewer; lifetime counts are tallied as events happen, saved with the world, and say from when they count."""

from chits import diag
from chits.lab import extract
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def world():
    return World("A", "A", 3, "direct", 64, 4)


def test_lifetime_counts_outlive_the_window():
    w = world()
    for i in range(5000):
        w.emit("forgotten", f"lost {i}", 4, recipe="spear")
    for i in range(10):
        w.emit("abandoned", "gone", 1, design="hut")
    assert len(w.events) == 4000 and w.recent("forgotten") == 3990
    assert w.lifetime("forgotten") == 5000 and w.lifetime("forgotten", "spear") == 5000
    assert w.lifetime("abandoned", "hut") == 10 and w.lifetime("abandoned", "kiln") == 0
    assert w.tallies_since == 0


def test_tallies_survive_a_save():
    w = world()
    for _ in range(4100):
        w.emit("birth", "a child", 2)
    b = World.from_dict(w.to_dict())
    assert b.lifetime("birth") == 4100 and b.tallies_since == 0
    assert len(b.events) == 1500  # (a save keeps a shorter window; the totals don't shrink with it)


def test_a_save_from_before_tallies_counts_from_its_oldest_event_and_says_so():
    w = world()
    w.tick = 10_000
    for i in range(2000):
        w.tick += 1
        w.emit("forgotten", "lost", 4)
    d = w.to_dict()
    d.pop("tallies")
    d.pop("tallies_since")
    b = World.from_dict(d)
    assert b.lifetime("forgotten") == 1500  # what the save remembers...
    assert b.tallies_since == b.events[0].tick > 10_000  # ...and from when: not a whole-run number


def test_the_lab_and_the_diagnostics_use_lifetime_counts():
    w = world()
    for _ in range(4500):
        w.emit("forgotten", "lost", 4)
    assert extract.row(w, 4)["forgotten"] == 4500
    w.emit("abandoned", "gone", 1, design="hut")
    assert diag.opportunities(w)["design:hut"]["sites_abandoned"] == 1


def test_an_abandoned_site_is_an_event():
    w = world()
    a = next(iter(w.agents.values()))
    site = w.place_site("hut", *w.find_site("hut", a.x, a.y), a)
    site.builders = set()
    w.tick += TICKS_PER_DAY * 7
    w._structure_tick(site, False)
    assert site.id not in w.structures and w.lifetime("abandoned", "hut") == 1
