"""F34 stage 3: an invention can be made at a station, which lets the same parts make more, and then needs that
station to be made again. (Inventions that are buildings are not built: docs/INVENTION_STRUCTURES.md says why.)"""

import json
from pathlib import Path

from chits.brain import prompt as P
from chits.brain.parse import parse_plan
from chits.sim.items import DESIGNS, ITEMS
from chits.sim.world import World

ROOT = Path(__file__).resolve().parents[1]


def _world(seed=3):
    w = World("A", "A", seed, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.inventory.clear()
        o.plan = []
    return w, a


def _place(w, a, design, dx):
    pos = w.find_site(design, a.x + dx, a.y, 10)
    s = w.place_site(design, pos[0], pos[1], a)
    w.complete_structure(s, a)
    return s


def run(w, a, step, limit=400):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


BLADE = {"do": "invent", "with": ["copper", "wood"], "name": "Copper Cleaver", "purpose": "a blade to cut", "at": "workshop"}


def test_the_parser_keeps_the_station_of_an_invention():
    plan = parse_plan(json.dumps({"goal": "a blade", "steps": [BLADE]}))
    assert plan["steps"][0]["at"] == "workshop" and plan["steps"][0]["do"] == "invent"


def test_an_invention_made_at_a_station_needs_it_to_be_made_again():
    w, a = _world()
    a.add("copper", 1)
    a.add("wood", 1)
    # away from any bench unworked copper has no edge: refused, nothing used up, and told a station might do more
    msg = run(w, a, dict(BLADE, at=None))
    assert not w.inventions and a.inventory == {"copper": 1, "wood": 1} and "workshop" in msg, msg
    msg = run(w, a, BLADE)
    assert "no workshop nearby" in msg and not w.inventions
    msg = run(w, a, dict(BLADE, at="volcano"))
    assert "not a known kind of station" in msg
    shop = _place(w, a, "workshop", 6)
    run(w, a, BLADE)
    assert len(w.inventions) == 1, a.last_result
    key, inv = next(iter(w.inventions.items()))
    assert shop.dist(a.x, a.y) <= 2  # it walked there
    assert inv["rule"] == "forged_blade" and inv["station"] == "workshop" and w.recipe(key).station == "workshop"
    assert w.item(key).tool == "axe" and 2.4 < w.item(key).tool_power < ITEMS["copper_axe"].tool_power
    assert "at a workshop" in P.scene(w, a)  # the chit is told where its invention is made
    # made again: only at the bench
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.recipe(key).station == "workshop"  # ...and after a restart too
    a.inventory.clear()
    a.add("copper", 1)
    a.add("wood", 1)
    shop.durability = 0.0  # the bench falls to ruin
    msg = run(w, a, {"do": "craft", "what": "Copper Cleaver"})
    assert not a.inventory.get(key) and "workshop" in msg, msg
    shop.durability = 100.0
    run(w, a, {"do": "craft", "what": "Copper Cleaver"})
    assert a.inventory.get(key) == 1, a.last_result


def test_the_same_parts_with_and_without_a_station_are_two_inventions_and_what_stands_here_counts():
    w, a = _world(seed=5)
    meal = {"do": "invent", "with": ["berries", "berries", "grain"], "name": "Mash", "purpose": "a meal"}
    for k, n in (("berries", 4), ("grain", 2)):
        a.inventory[k] = n
    run(w, a, meal)
    plain = next(iter(w.inventions))
    assert w.inventions[plain]["station"] is None and w.recipe(plain).station is None
    _place(w, a, "campfire", 1)
    a.x, a.y = w.nearest_station(a.x, a.y, "fire").x, w.nearest_station(a.x, a.y, "fire").y
    run(w, a, dict(meal, name="Hot Mash"))  # no "at": it is standing at the fire
    assert len(w.inventions) == 2, a.last_result
    hot = [k for k in w.inventions if k != plain][0]
    assert w.inventions[hot]["station"] == "fire" and w.recipe(hot).station == "fire"
    assert w.item(hot).food > w.item(plain).food
    # an old save's invention has no station field: it loads needing none
    d = json.loads(json.dumps(w.to_dict()))
    for inv in d["inventions"].values():
        inv.pop("station", None)
        inv.pop("rule", None)
    w2 = World.from_dict(d)
    assert w2.recipe(hot).station is None and w2.item(hot).food == w.item(hot).food


def test_inventions_cannot_be_buildings_and_the_design_note_says_exactly_why():
    """Stage 3's second half was not built: a world-local design would have to be looked up through the catalogue at
    every place that indexes the shared DESIGNS table. The note counts those places; this keeps the count honest."""
    note = (ROOT / "docs" / "INVENTION_STRUCTURES.md").read_text()
    import re

    sites = 0
    for p in sorted((ROOT / "server" / "chits").rglob("*.py")):
        n = len(re.findall(r"\bDESIGNS\[", p.read_text()))
        if n:
            sites += n
            assert f"`{p.relative_to(ROOT / 'server' / 'chits').as_posix()}` | {n} |" in note, p.name
    assert f"**{sites}**" in note
    w, a = _world(seed=7)
    a.inventory.update({"wood": 4})
    run(w, a, {"do": "invent", "with": ["wood", "wood", "wood", "wood"], "name": "Wind Shelter", "purpose": "a shelter to keep warm"})
    assert not any(s.design not in DESIGNS for s in w.structures.values())
    assert "Wind Shelter" not in DESIGNS and all(not k.startswith("inv_") for k in DESIGNS)
