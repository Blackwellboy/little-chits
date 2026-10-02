"""F11 gate 1: ore in mines must reach the stores a furnace can draw from."""

from chits.brain.instinct import FURNACE_ORE_TARGET, feed_furnace_plan
from chits.sim.actions import era_path
from chits.sim import actions as ACT
from chits.sim.world import World


def _complete(w, a, design, x, y):
    st = w.place_site(design, *w.find_site(design, x, y, 8, reach=(a.x, a.y)), a)
    w.complete_structure(st, a)
    return st


def test_feed_furnace_moves_mine_ore_to_a_furnace_store():
    w = World("A", "A", 17, "direct", 96, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["stone_pick"] = 1
    a.learn("recipe:iron", "taught", w.tick)
    a.learn("recipe:copper", "taught", w.tick)
    kind = "iron_ore" if "iron" in era_path(w) else "ore"  # (issue #4: the ore the furnace needs next)
    furnace = _complete(w, a, "furnace", a.x + 5, a.y)
    pile = _complete(w, a, "stockpile", furnace.x + 3, furnace.y)
    pile.storage.update({kind: 1, "charcoal": 20})
    mine = _complete(w, a, "mine", a.x + 10, a.y + 5)
    mine.storage.update({"ore": 20, "iron_ore": 20})

    a.plan_source = "instinct"
    trips = 0
    while pile.storage.get(kind, 0) < FURNACE_ORE_TARGET and trips < 3:
        plan = feed_furnace_plan(w, a)
        assert plan and plan["goal"] == "feed the furnace with ore"
        assert plan["steps"][0] == {"do": "go", "to": mine.id}
        gather = next(s for s in plan["steps"] if s["do"] == "gather")
        assert gather["what"] == kind and gather["qty"] <= int(a.free_space() // w.item(kind).weight)
        assert plan["steps"][-1]["target"] == pile.id
        for step in plan["steps"]:
            for _ in range(1000):
                r = ACT.advance(w, a, step)
                if r != ACT.RUNNING:
                    assert r == ACT.DONE, (step, r)
                    break
                w.tick += 1
            else:
                raise AssertionError(f"step timed out: {step}")
        trips += 1

    # Ore is heavy: with a pick in hand the first physical trip carries only five, then instinct schedules another.
    assert trips == 2
    assert pile.storage[kind] >= FURNACE_ORE_TARGET
    bill, why = ACT.plan_bill(w, a, {"furnace"}, target=furnace)
    assert bill is not None, why
    assert bill.r.key == ("iron" if kind == "iron_ore" else "copper")


def test_feed_furnace_does_nothing_when_local_ore_is_already_enough():
    w = World("A", "A", 19, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory["stone_pick"] = 1
    a.learn("recipe:iron", "taught", w.tick)
    furnace = _complete(w, a, "furnace", a.x + 4, a.y)
    pile = _complete(w, a, "stockpile", furnace.x + 2, furnace.y)
    pile.storage.update({"ore": FURNACE_ORE_TARGET, "charcoal": 20})
    mine = _complete(w, a, "mine", a.x + 8, a.y + 4)
    mine.storage["ore"] = 20
    assert feed_furnace_plan(w, a) is None



def test_feed_furnace_does_not_target_an_unseen_remote_mine():
    w = World("A", "A", 23, "direct", 128, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["stone_pick"] = 1
    a.learn("recipe:iron", "taught", w.tick)
    furnace = _complete(w, a, "furnace", a.x + 4, a.y)
    pile = _complete(w, a, "stockpile", furnace.x + 2, furnace.y)
    pile.storage.update({"ore": 0, "charcoal": 20})
    mine = _complete(w, a, "mine", a.x + 32, a.y + 12)
    mine.storage["ore"] = 30
    assert mine.dist(a.x, a.y) > 14
    # No local sight and no remembered/heard ore location: instinct must not use the mine's private id/storage.
    assert feed_furnace_plan(w, a) is None


def test_feed_furnace_can_finish_a_one_unit_top_up():
    w = World("A", "A", 29, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.inventory["stone_pick"] = 1
    a.learn("recipe:iron", "taught", w.tick)
    furnace = _complete(w, a, "furnace", a.x + 4, a.y)
    pile = _complete(w, a, "stockpile", furnace.x + 2, furnace.y)
    pile.storage.update({"ore": FURNACE_ORE_TARGET - 1, "charcoal": 20})
    mine = _complete(w, a, "mine", a.x + 8, a.y + 4)
    mine.storage["ore"] = 20
    plan = feed_furnace_plan(w, a)
    assert plan is not None
    gather = next(s for s in plan["steps"] if s["do"] == "gather")
    assert gather["qty"] == 1
