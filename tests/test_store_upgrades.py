"""Village storage (audit F10): one definition of usable nearby stores, and store upgrades that get finished. Live,
six stockpiles in each world stood half rebuilt as warehouses for want of stone and cord (only a chit's own home was
ever carried on), no more storage was begun while they did, and the "why not" panel said the warehouse was never
started. On the live save, six days of this fix finished all six."""

from chits import diag
from chits.brain import builder as BI
from chits.brain.instinct import Instinct
from chits.sim import actions, research
from chits.sim import buildings as BLD
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import World


def village():
    w = World("A", "A", 3, "direct", 64, 4)
    a = next(iter(w.agents.values()))
    a.inventory.clear()
    a.hunger = a.energy = a.warmth = 100
    for k in ("design:stockpile", "design:warehouse", "recipe:cord"):
        a.learn(k, "taught", w.tick)
    return w, a


def build(w, a, design):
    st = w.place_site(design, *w.find_site(design, a.x, a.y), a)
    w.complete_structure(st, a)
    return st


def half_rebuilt(w, a):
    pile = build(w, a, "stockpile")
    pile.upgrade = {"to": "warehouse", "needs": {"stone": 10, "cord": 4}, "work": 0.0,
                    "total": 40.0, "by": {}, "tick": w.tick}
    return pile


def test_village_stores_are_stockpiles_and_warehouses_the_chit_can_reach():
    w, a = village()
    pile, ware, camp = build(w, a, "stockpile"), build(w, a, "warehouse"), build(w, a, "outpost")
    got = {s.id for s in actions.village_stores(w, a.x, a.y, 40, a)}
    assert pile.id in got and ware.id in got and camp.id not in got
    a.reflex_rest["unreach:" + ware.id] = w.tick + 100
    assert ware.id not in {s.id for s in actions.village_stores(w, a.x, a.y, 40, a)}
    assert ware.id in {s.id for s in actions.village_stores(w, a.x, a.y, 40)}  # (no chit: every working store)


def test_warehouse_goods_count_for_research_and_rot_like_any_store():
    w, a = village()
    ware = build(w, a, "warehouse")
    ware.storage["steel"] = 2
    assert "steel" in research.village_handled(w)
    ware.storage["berries"] = 200
    for _ in range(5):
        BLD._spoil(w)
    assert ware.storage.get("berries", 0) < 200


def test_anyone_carries_on_a_stalled_store_upgrade_by_gathering_and_making_what_it_needs():
    w, a = village()
    pile = half_rebuilt(w, a)
    plan = BI.store_upgrade_plan(w, a)
    assert plan and plan["steps"][-1] == {"do": "upgrade", "target": pile.id}
    assert any(s["do"] == "gather" and s["what"] == "stone" for s in plan["steps"])
    assert pile.id != a.home  # (not its home: that was the only upgrade ever carried on)


def test_a_stalled_warehouse_gets_finished():
    w, a = village()
    pile = half_rebuilt(w, a)
    ins = Instinct()
    for _ in range(6 * TICKS_PER_DAY):
        for o in w.agents.values():
            o.hunger = o.energy = o.warmth = 100
        w.step(lambda world, o: (setattr(o, "plan", ins.plan(world, o)["steps"]) if not o.plan else None))
        if pile.design == "warehouse" or (w.structures.get(pile.id) is not None and w.structures[pile.id].design == "warehouse"):
            break
    assert w.structures[pile.id].design == "warehouse" and not w.structures[pile.id].upgrade


def test_the_why_not_panel_shows_upgrades_under_way():
    w, a = village()
    half_rebuilt(w, a)
    o = diag.opportunities(w)["design:warehouse"]
    assert o["upgrades_started"] == 1 and o["upgrades_waiting_for"] == {"stone": 10, "cord": 4}


def test_affordability_counts_warehouse_stock():
    from chits.sim.items import DESIGNS

    w, a = village()
    a.learn("design:well", "taught", w.tick)
    assert diag.opportunities(w)["design:well"]["affordable_by"] == 0
    build(w, a, "warehouse").storage.update(DESIGNS["well"].material_map)  # (only a warehouse holds them)
    assert diag.opportunities(w)["design:well"]["affordable_by"] == 1


def test_a_hemmed_in_stockpile_is_not_offered_as_a_warehouse():
    """Live, "there's no clear ground beside the stockpile to make it a warehouse" failed 1.6 million times in one
    2,600-day world: the fullest stockpile was offered for a warehouse whether or not a warehouse could stand there."""
    w, a = village()
    pile = build(w, a, "stockpile")
    pile.storage["stone"] = 10 ** 4
    a.x, a.y = pile.x, pile.y
    plan = Instinct._more_storage(w, a)
    assert plan and plan["steps"] == [{"do": "upgrade", "to": "warehouse", "target": pile.id}]
    own = set(pile.cells())
    for y in range(pile.y - 3, pile.y + pile.h + 3):
        for x in range(pile.x - 3, pile.x + pile.w + 3):
            if (x, y) not in own and w.inb(x, y):
                w.roads.add(y * w.w + x)
    assert BLD.upgrade_spot(w, pile, "warehouse") is None
    plan = Instinct._more_storage(w, a)
    assert not plan or {"do": "upgrade", "to": "warehouse", "target": pile.id} not in plan["steps"]
