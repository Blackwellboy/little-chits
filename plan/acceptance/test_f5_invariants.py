"""Cheap invariants that catch awful bugs: nothing is duplicated or lost, nothing goes negative, repeated or
concurrent actions don't double-count, the parser never lets garbage through, and long runs stay in sane ranges."""

import ast
import json
import random
from collections import Counter
from pathlib import Path

from chits.brain.instinct import Instinct
from chits.brain.parse import ParseError, parse_plan
from chits.sim import actions as A
from chits.sim.items import RECIPES
from chits.sim.world import World

ROOT = Path(__file__).resolve().parents[2]


def totals(w):
    c = Counter()
    for a in w.agents.values():
        c.update({k: n for k, n in a.inventory.items() if n})
    for s in w.structures.values():
        c.update({k: n for k, n in s.storage.items() if n})
    for pile in getattr(w, "ground", {}).values():
        c.update({k: n for k, n in pile.items() if k != "_t" and n})
    return c


def ready(w, n=2):
    ags = list(w.agents.values())[:n]
    for a in ags:
        a.hunger = a.energy = a.warmth = a.health = 100.0
        a.inventory.clear()
        a.plan = []
    return ags


def run(w, a, step, limit=200):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def stockpile(w, a):
    pos = w.find_site("stockpile", a.x, a.y)
    s = w.place_site("stockpile", pos[0], pos[1], a)
    w.complete_structure(s, a)
    return s


def test_store_and_take_conserve_items():
    w = World("A", "A", 3, "direct", 64, 2)
    a, b = ready(w)
    st = stockpile(w, a)
    a.add("wood", 5)
    a.add("stone", 3)
    before = totals(w)
    run(w, a, {"do": "store", "what": "all", "target": st.id})
    assert totals(w) == before and not a.inventory.get("wood")
    run(w, b, {"do": "take", "what": "wood", "qty": 3, "target": st.id})
    assert totals(w) == before and b.inventory.get("wood") == 3


def test_craft_consumes_exact_inputs_once_and_failures_consume_nothing():
    w = World("A", "A", 5, "direct", 64, 1)
    (a,) = ready(w, 1)
    a.learn("recipe:cord", "discovered", w.tick, None)
    a.add("fiber", 5)
    run(w, a, {"do": "craft", "what": "cord", "qty": 2})
    assert a.inventory.get("cord") == 2 and a.inventory.get("fiber") == 1
    before = dict(a.inventory)
    run(w, a, {"do": "craft", "what": "stone axe"})  # not known: must fail without consuming
    assert a.inventory == before


def test_two_builders_cannot_overfill_a_site_and_completion_is_idempotent():
    w = World("A", "A", 7, "direct", 64, 2)
    a, b = ready(w)
    pos = w.find_site("hut", a.x, a.y)
    site = w.place_site("hut", pos[0], pos[1], a)
    need_wood = site.needs.get("wood", 0)
    a.add("wood", need_wood)
    b.add("wood", need_wood)
    b.x, b.y = a.x, a.y
    a.plan = [{"do": "help", "site": site.id}]
    b.plan = [{"do": "help", "site": site.id}]
    for _ in range(80):
        w.step()
    delivered = (need_wood - a.inventory.get("wood", 0)) + (need_wood - b.inventory.get("wood", 0))
    assert delivered == need_wood, "the last wood was delivered twice"
    assert site.needs.get("wood", 0) == 0
    for k, n in site.needs.items():
        assert n >= 0
    evs = []
    w.listeners.append(evs.append)
    w.complete_structure(site, a)
    w.complete_structure(site, b)
    assert sum(e.kind == "built" for e in evs) <= 1


def test_save_restore_preserves_everything_countable():
    w = World("A", "A", 9, "direct", 96, 6)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan = p["steps"]

    for _ in range(240 * 3):
        w.step(hook)
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert totals(w2) == totals(w)
    assert sorted(w2.agents) == sorted(w.agents) and sorted(w2.structures) == sorted(w.structures)
    assert w2.res_amt == w.res_amt and w2.tick == w.tick


def test_long_run_stays_in_sane_ranges():
    w = World("A", "A", 11, "direct", 128, 16)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan = p["steps"]

    for day in range(40):
        for _ in range(240):
            w.step(hook)
        for a in w.agents.values():
            assert all(n >= 0 for n in a.inventory.values()), a.inventory
            assert 0 <= a.hunger <= 100 and 0 <= a.warmth <= 100 and a.health <= 100
        assert min(w.res_amt) >= 0
        for s in w.structures.values():
            assert all(n >= 0 for n in s.storage.values()) and all(n >= 0 for n in s.needs.values())
    pop = len(w.agents)
    assert 8 <= pop <= 60, pop
    assert len(w.structures) <= 3 * pop + 40, (len(w.structures), pop)
    ruins = sum(1 for s in w.structures.values() if s.complete and s.durability <= 0)
    assert ruins <= max(6, len(w.structures) // 4), ruins
    idle = sum(1 for a in w.agents.values() if not a.plan and not a.is_child(w.tick))
    assert idle <= max(2, pop // 3)


def test_parser_never_lets_garbage_through():
    rng = random.Random(1234)
    verbs = set(A.VERBS)
    pieces = ['{', '}', '[', ']', '"do"', ':', ',', '"gather"', '"wood"', '"qty"', '-5', '1e9', 'NaN', '"plan"',
              '<think>', '</think>', '```json', '```', '"steps"', '"what"', '"🪵"', '"build"', '"hut"', 'null',
              '"x"' * 50, '{"do":"fly","to":"moon"}', '{"do":"gather","what":"wood","qty":999999}',
              '{"do":"gather","what":"wood","qty":-3}', '{"do":"craft","what":{"nested":{"deep":[1,2,3]}}}']
    for _ in range(3000):
        text = " ".join(rng.choice(pieces) for _ in range(rng.randint(1, 18)))
        try:
            p = parse_plan(text)
        except ParseError:
            continue
        assert 1 <= len(p["steps"]) <= 6
        for s in p["steps"]:
            assert s["do"] in verbs, s
            if "qty" in s:
                assert isinstance(s["qty"], int) and 1 <= s["qty"] <= 99, s
            for v in s.values():
                assert not isinstance(v, dict), s  # no arbitrary nesting reaches the simulator


def test_story_never_feeds_back_into_minds():
    """One-way data path: simulation -> events -> moments -> stories. The brain must never import story code."""
    for f in (ROOT / "server" / "chits" / "brain").glob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", "") or ""
                names = [n.name for n in node.names]
                assert "story" not in mod and not any("story" in n for n in names), f"{f.name} imports story code"
