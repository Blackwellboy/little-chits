"""The Machine Age stall (audit F5/F11), distilled from the live World A at day 1630: the scholars' idea for the steam
engine had stood for 465 days. Traced on the live save, four gates stood in the way:

1. no steel was ever made (0 in ~470 days; ore thin near the village): still open, see docs/FIXES_2026-09-30.md;
2. gear shifts turned whatever steel the stores held into gears, so the engine's own 2 steel were never there;
3. the planners gave up on a forge 20-25 tiles away while the action walks 45 (65% of the idea's chances);
4. only the scholars' idea builds the engine's 5-item bag (blind experiments stop at 4).

Given the engine's inputs in its stores, the live village found it in 5 days once 2 and 3 were fixed, and never in 10
days before. This is that village, small."""

from chits.brain.mind import Mind
from chits.sim import actions, research
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import RECIPES
from chits.sim.world import World


def build(w, a, design, near, far=0):
    x, y = w.find_site(design, near[0] + far, near[1], 12, reach=(near[0] + far, near[1]))
    st = w.place_site(design, x, y, a)
    w.complete_structure(st, a)
    return st


def machine_age_village(forge_at=30, steel=4, gear=4):
    w = World("A", "A", 11, "direct", 128, 8)
    ags = list(w.agents.values())
    home = (ags[0].x, ags[0].y)
    for o in ags:
        o.hunger = o.energy = o.warmth = o.health = 95.0
        for k in ("recipe:steel", "recipe:gear", "recipe:pot", "recipe:charcoal", "recipe:iron", "design:forge"):
            o.learn(k, "taught", w.tick)
        o.familiar |= {"steel", "gear", "pot", "iron"}
    for i in range(0, len(ags), 2):
        hut = build(w, ags[i], "hut", home)
        for o in ags[i:i + 2]:
            o.home = hut.id
    build(w, ags[0], "campfire", home)
    pile = build(w, ags[0], "stockpile", home)
    pile.storage.update({"steel": steel, "gear": gear, "pot": 4, "wood": 20, "charcoal": 10})
    build(w, ags[0], "workshop", home)
    forge = build(w, ags[0], "forge", home, far=forge_at)
    for k in ("recipe:copper", "recipe:iron"):  # the Iron Age: next is the Machine Age, whose key is the engine
        w.first[k] = {"tick": 0, "by": ags[0].id}
    w.civic.setdefault("hints", []).append(
        {"id": "h1", "recipe": "engine", "parts": [[research.clue(i), n] for i, n in RECIPES["engine"].inputs],
         "station": "forge", "text": "", "tick": 0, "by": "", "by_name": "", "found": 0})
    return w, forge, pile


def run_until_engine(w, days=6):
    m = Mind(None)
    for _ in range(int(days * TICKS_PER_DAY)):
        w.step(m.hook)
        if "recipe:engine" in w.first:
            return True
    return False


def test_the_village_is_in_the_iron_age_with_the_forge_out_of_the_old_reach():
    w, forge, pile = machine_age_village()
    assert w.era()[1] == "Iron Age"  # (the Machine Age is next)
    assert actions.keep_stock(w)["steel"] == 2 and actions.keep_stock(w)["gear"] == 2
    d = max(abs(forge.center()[0] - pile.center()[0]), abs(forge.center()[1] - pile.center()[1]))
    assert 25 < d <= actions.STATION_REACH, d


def test_given_its_inputs_the_village_discovers_the_steam_engine():
    # steel in the stores and no gears yet, as live: the gears must be made without eating the engine's steel
    w, _, pile = machine_age_village(steel=4, gear=0)
    assert run_until_engine(w, days=10), ("the steam engine was not discovered", dict(pile.storage))


def test_gear_shifts_leave_the_engines_steel_in_the_stores():
    w, _, pile = machine_age_village(steel=4, gear=0)
    a = next(iter(w.agents.values()))
    r = w.recipe("gear")
    assert actions._batches(w, a, r, dict(pile.storage)) == 2  # 4 steel, 2 kept for the engine: 2 batches, 4 gears
    assert actions._batches(w, a, r, {"steel": 2}) == 0
