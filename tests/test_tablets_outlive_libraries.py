"""Tablets outlive their library. A library that crumbled away kept its tablets "inside" it, where nothing could
read them: live World B held 180 of its 196 tablets that way by day 2,660, and the only tablet of steel was one of
them, so the village rediscovered steel twice and lost it again. And instinct only ever went to read at a library,
never a tablet lying loose."""

import random

from chits.brain.instinct import Instinct
from chits.sim import actions
from chits.sim.world import Tablet, World


def library_with_steel():
    w = World("A", "A", 5, "direct", 64, 4)
    a, b = list(w.agents.values())[:2]
    for o in (a, b):
        o.hunger = o.energy = o.warmth = o.health = 95.0
    lib = w.place_site("library", *w.find_site("library", a.x, a.y), a)
    w.complete_structure(lib, a)
    tb = Tablet("t1", "recipe:steel", a.id, a.name, w.tick, lib.x, lib.y, lib.id, "steel is iron and charcoal")
    w.tablets[tb.id] = tb
    lib.shelf.append(tb.id)
    b.knows.pop("recipe:steel", None)
    return w, lib, tb, b


def test_a_crumbled_librarys_tablets_lie_where_it_stood_and_can_be_read():
    w, lib, tb, b = library_with_steel()
    w.remove_structure(lib)
    assert tb.in_structure is None and (tb.x, tb.y) == (lib.x, lib.y)
    step = {"do": "read"}
    for _ in range(3000):
        w.tick += 1
        b.hunger = b.energy = b.warmth = 95.0
        if actions.advance(w, b, step) != actions.RUNNING:
            break
    assert "recipe:steel" in b.knows


def test_a_save_with_tablets_in_a_vanished_library_lets_them_go():
    w, lib, tb, b = library_with_steel()
    d = w.to_dict()
    d["structures"] = [s for s in d["structures"] if s["id"] != lib.id] if isinstance(d["structures"], list) else \
        {k: s for k, s in d["structures"].items() if k != lib.id}
    w2 = World.from_dict(d)
    assert w2.tablets["t1"].in_structure is None


def test_instinct_goes_to_read_a_loose_tablet_of_what_nobody_still_knows():
    w, lib, tb, b = library_with_steel()
    w.remove_structure(lib)
    b.x, b.y = tb.x + 3, tb.y
    ins = Instinct()
    for o in w.agents.values():
        o.knows.pop("recipe:steel", None)
    goals = {(ins._communal(w, b, random.Random(s)) or {}).get("goal") for s in range(300)}
    assert "read an old tablet" in goals
    # someone alive still knows it: it can be taught, so nobody walks off to read it
    other = next(o for o in w.agents.values() if o is not b)
    other.learn("recipe:steel", "discovered", w.tick)
    goals = {(ins._communal(w, b, random.Random(s)) or {}).get("goal") for s in range(300)}
    assert "read an old tablet" not in goals
