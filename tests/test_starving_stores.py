"""Hungry past the stores (actions.STARVING_STORES). Six chits of one world starved beside full stores (tools/harness,
seed 32, days 36-47): camped at a fire across a lake from the village, a store 12 tiles off as the crow flies was ~85
steps on foot. The hunger margin counted the 12 tiles; the eat step marked the two stores beside the village "a long
way round" and accepted a third further on foot; the marks blinded the chit as its walk led past them; and the food
reflex chose wild food over a store whose walk it could no longer spare.
Each test here fails with the switch off."""

import pytest

from chits.sim import actions as A
from chits.sim import terrain as T
from test_buildings import put, village


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(A, "STARVING_STORES", True)


def _walled(berries=None):
    """Flat grass, a chit at (20, 20), a rock wall along y=26 from x=0 to 45 (south of it is a long way round), and no
    wild food (or berries at one tile)."""
    w, (a, b) = village()
    for i in range(len(w.tiles)):
        x, y = i % w.w, i // w.w
        w.tiles[i] = T.ROCK if (y == 26 and x <= 45) else T.GRASS
    w.rebuild_block()
    a.x, a.y = 20, 20
    b.x, b.y = 60, 2
    w.nearest_resource = lambda x, y, kind, radius, *args, **kw: berries if kind == "berries" and berries and max(
        abs(berries[0] - x), abs(berries[1] - y)) <= radius else None
    w.piles_near = lambda *args, **kw: iter(())
    return w, a


def _store(w, a, x, y, food=40):
    st = put(w, "stockpile", a, near=(x, y), radius=2)
    st.storage["grain"] = food
    return st


def _walk(w, a, st):
    return len(w.find_path(a.x, a.y, A._structure_goals(w, st)))


def _two_stores():
    """Store `near` 12 tiles south as the crow flies, past the wall (~50 steps); store `far` 26 tiles off, ~65 steps."""
    w, a = _walled()
    near, far = _store(w, a, 20, 31), _store(w, a, 8, 46)
    assert near.dist(a.x, a.y) < far.dist(a.x, a.y)
    assert _walk(w, a, near) > A.LONG_WAY * A._crow(a, near.x, near.y)  # "a long way round" by its own distance...
    assert _walk(w, a, far) <= A.LONG_WAY * A._crow(a, far.x, far.y)  # ...and the further one isn't by its own
    assert _walk(w, a, near) < _walk(w, a, far)  # yet the near one is the shorter walk
    return w, a, near, far


def test_a_marked_store_beside_the_way_is_taken():
    # its walk to the third store led right past the second (4 tiles off, 228 food), marked, and it starved there
    w, a = _walled()
    far = _store(w, a, 40, 12)
    beside = _store(w, a, 22, 20, food=20)
    assert beside.dist(a.x, a.y) <= A.PASSING_STORE
    a.reflex_rest["unreach:" + beside.id] = w.tick + 240
    a.hunger = 10.0
    s = {"store": far.id}
    A._do_eat(w, a, {"do": "eat"}, s)
    assert s["store"] == beside.id


def test_the_margin_counts_the_walk_to_the_store_not_the_crow():
    # warming up 12 tiles from the store as the crow flies, ~50 steps on foot: from hunger 30 the walk can't wait
    w, a = _walled()
    store = _store(w, a, 20, 31)
    a.hunger, a.energy = 30.0, 90.0
    a.plan = [{"do": "warm_up", "_reflex": True}]
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "eat" and a.plan[1]["do"] == "warm_up"
    a.plan = [{"do": "warm_up", "_reflex": True}]
    a.hunger = 60.0  # (above MARGIN_FROM: nothing is looked up)
    A.reflexes(w, a)
    assert a.plan[0]["do"] == "warm_up"


def test_a_starving_chit_goes_to_the_store_not_to_wild_food_further_than_wild_near():
    # berries 9 tiles off beat the store 13 tiles off as the crow flies (~55 steps on foot); with the store's walk
    # short, the store
    w, a = _walled(berries=(29, 20))
    store = _store(w, a, 20, 33)
    assert A._crow(a, *store.center()) > 9 + 2  # (berries +2: picking takes a moment)
    a.hunger = 12.0
    assert A._food_reflex(w, a)["do"] == "eat"
    a.hunger = 20.0  # not yet starving (WILD_BELOW): wild food is no gamble
    assert A._food_reflex(w, a)["do"] == "gather"
    a.hunger = 12.0
    w.nearest_resource = lambda x, y, kind, *args, **kw: (23, 20) if kind == "berries" else None
    assert A._food_reflex(w, a)["do"] == "gather"  # within WILD_NEAR: a try costs little


def test_a_walk_longer_than_one_given_up_as_a_long_way_round_is_given_up_too():
    # after the two stores beside the village (~85 steps, 12 tiles off) were given up as a long way round, a third 29
    # tiles off passed at 115 steps, against its own distance, and the chit starved on the walk (seed 32)
    w, a, near, far = _two_stores()
    w.nearest_resource = lambda x, y, kind, radius, *args, **kw: (25, 20) if kind == "berries" else None  # forage
    a.hunger = 18.0
    s = {}
    assert A._do_eat(w, a, {"do": "eat"}, s) == A.RUNNING
    assert a.reflex_rest.get("unreach:" + near.id, 0) > w.tick and "store" not in s  # foraging instead
    A._do_eat(w, a, {"do": "eat"}, s)  # the next tick it looks again: only the further store is left
    assert s.get("store") != far.id and a.reflex_rest.get("unreach:" + far.id, 0) > w.tick
