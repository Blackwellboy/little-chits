"""A starving chit on a food-fetching reflex eats. The food reflex is itself a reflex, and a reflex head was never
interrupted for food: on one 60-day run three chits starved at hunger 0 on a "gather fish" reflex, two holding the
fish they had caught (the step wanted three) and one walking between spent fish tiles with 550 food in a store 25
tiles away on the same land."""

from chits.sim import actions
from test_buildings import put, village


def starving(fish=0):
    w, (a, _) = village()
    a.hunger = 3.0
    if fish:
        a.add("fish", fish)
    a.plan = [{"do": "gather", "what": "fish", "qty": 3, "_reflex": True}]
    return w, a


def test_a_starving_chit_eats_the_fish_it_holds_instead_of_fishing_on():
    w, a = starving(fish=2)
    actions.reflexes(w, a)
    # the eat takes the fetch's place: left behind it, the fetch walked the fed chit back out to the water
    assert a.plan == [{"do": "eat", "_reflex": True}]
    for _ in range(50):
        w.tick += 1
        actions.run(w, a)
        if not a.plan:
            break
    assert a.hunger > 20 and a.inventory.get("fish", 0) < 2


def test_after_a_while_fetching_in_vain_a_starving_chit_goes_to_the_stores():
    w, a = starving()
    pile = put(w, "stockpile", a)
    pile.storage["bread"] = 20
    a.plan[0]["_s"] = {"ticks": actions.FETCH_PATIENCE // 2}
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "gather"  # (not straight away: the fish may be close)
    fetch = a.plan[0]
    pile.storage.clear()
    fetch["_s"]["ticks"] = actions.FETCH_PATIENCE + 1
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "gather"  # nothing stored: fishing is still the best it has
    pile.storage["bread"] = 20
    actions.reflexes(w, a)
    assert a.plan == [{"do": "eat", "_reflex": True}]


def test_a_chit_that_is_only_hungry_fetches_on():
    w, a = starving(fish=2)
    a.hunger = actions.STARVING + 5
    actions.reflexes(w, a)
    assert a.plan[0]["do"] == "gather"


def test_a_hungry_chit_sheltering_from_the_weather_goes_for_food_at_the_same_hunger_as_any_other():
    # seed 42, 60 days: two chits sheltered and warmed up from hunger 30 down to 8 before food came first, and
    # starved walking to a store; any other step gives way to food below 16
    from chits.sim import actions as A
    from chits.sim.world import World
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["berries"] = 2
    for kind in ("shelter", "warm_up", "sleep", "store"):
        a.plan = [{"do": kind, "_reflex": True}]
        a.hunger = 12.0
        A._reflexes(w, a)
        assert a.plan[0]["do"] == "eat", (kind, a.plan)
    a.plan = [{"do": "shelter", "_reflex": True}]
    a.hunger = 20.0  # not yet hungry enough: the weather comes first
    A._reflexes(w, a)
    assert a.plan[0]["do"] == "shelter", a.plan
