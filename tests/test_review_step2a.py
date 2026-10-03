"""The 2026-10-04 review, step 2a (F32): one radius table, a great library is a library, every design has a planner
that can choose it, a believer builds a shrine, and the civic lists name only real designs."""

import random
import re
from pathlib import Path

from chits.brain import builder as BR
from chits.sim import actions as A, buildings as BLD, settlements as SE
from chits.sim.items import DESIGNS, STARTING_DESIGNS
from chits.sim.world import Tablet, World

ROOT = Path(__file__).resolve().parents[1] / "server" / "chits"


def _world(seed=3, n=2, culture="direct"):
    w = World("A", "A", seed, culture, 64, n)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = o.health = 95.0
        o.inventory.clear()
        o.plan = []
    w.tick = 240 * 2 + 120  # midday
    return w, a


def _place(w, a, design, x, y):
    pos = w.find_site(design, x, y, 4)
    assert pos, (design, x, y)
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


def test_nothing_is_reused_from_farther_than_its_effect_reaches():
    for d, r in BLD.EFFECT_RADIUS.items():
        assert A.REUSE_WITHIN[d] <= r, (d, A.REUSE_WITHIN[d], r)
    # and the builder looks at least as far as the build reuses, or it proposes what the build then refuses
    assert A.REUSE_WITHIN["town_hall"] <= SE.HALL_REACH
    assert A.REUSE_WITHIN["palisade"] <= BLD.PALISADE_RADIUS
    assert A.REUSE_WITHIN["university"] <= SE.HALL_REACH and A.REUSE_WITHIN["theatre"] <= SE.HALL_REACH
    assert A.REUSE_WITHIN["granary"] <= BLD.GRANARY_RADIUS and A.REUSE_WITHIN["well"] <= BLD.WELL_RADIUS


def test_a_granary_for_a_pile_just_past_anothers_reach_is_not_refused():
    w, a = _world()
    g = _place(w, a, "granary", a.x - 7, a.y)
    # a stockpile exactly 11 tiles from the granary: past its reach (10), inside the old reuse (12)
    spot = next((p for dy in (0, 1, -1, 2, -2, 3, -3) for p in [w.find_site("stockpile", g.x + g.w + 10, g.y + dy, 0)]
                 if p and g.dist(p[0], p[1]) == 11), None)
    assert spot, "no free tile 11 from the granary"
    pile = w.place_site("stockpile", spot[0], spot[1], a)
    w.complete_structure(pile, a)
    pile.storage["bread"] = 30
    assert g.dist(pile.x, pile.y) == 11
    assert not BLD.keeps_fresh(w, pile)  # so this pile rots...
    assert A._use_existing(w, a, "granary", {}, pile.x, pile.y) is None  # ...and a granary beside it is not refused


def test_a_great_library_is_a_library_for_reading_study_and_writing():
    w, a = _world(seed=5)
    lib = _place(w, a, "great_library", a.x + 4, a.y)
    tid = w._new_id("tablet")
    w.tablets[tid] = Tablet(tid, "recipe:cord", "", "someone long ago", w.tick, lib.x, lib.y, lib.id, "2 plant fiber -> cord")
    lib.shelf.append(tid)
    assert not a.knows_recipe("cord")
    run(w, a, {"do": "read"})
    assert a.knows_recipe("cord"), a.last_result
    run(w, a, {"do": "study"})
    assert "tudied the" in a.last_result, a.last_result
    a.learn("recipe:sharp_stone", "discovered", w.tick)
    a.add("clay_tablet", 1)
    run(w, a, {"do": "write", "what": "sharp stone"})
    assert len(lib.shelf) == 2, a.last_result


PLANNERS = [ROOT / "brain" / f for f in ("builder.py", "instinct.py", "civic.py", "outposts.py", "voyages.py", "pioneers.py",
                                          "prospect.py")] + [ROOT / "sim" / f for f in ("projects.py", "pioneers.py")]
MODEL_ONLY = ()  # designs only a model-minded chit ever builds (none today: say so here if one is meant to be)


def test_every_design_has_a_planner_that_can_choose_it():
    """Live, the sand pit was known by 61 and affordable by 58 and never started; the shrine known by 89. A design nothing
    plans for is decoration. Upgrades count (a longhouse is reached by rebuilding a hut)."""
    text = "\n".join(p.read_text() for p in PLANNERS if p.exists())
    from chits.sim.world import ERAS

    upgrades = {k for vs in BLD.UPGRADES.values() for k in vs}
    upgrades |= {k.split(":", 1)[1] for _, k in ERAS if k and k.startswith("design:")}  # the road to the next age builds these
    unplanned = [d for d in DESIGNS if d not in STARTING_DESIGNS and d not in upgrades and d not in MODEL_ONLY
                 and not re.search(rf"\b{d}\b", text)]
    assert not unplanned, unplanned


def test_a_believer_raises_a_shrine_for_its_faith():
    w, a = _world(seed=7)
    a.belief = "b1"
    a.learn("design:shrine", "discovered", w.tick)
    a.add("stone", 6)
    a.add("wood", 2)
    opts = BR.building_options(w, a, random.Random(1))
    shrine = [p for _, p in opts if p["steps"][-1].get("what") == "shrine"]
    assert shrine, [p["goal"] for _, p in opts]
    # a shrine of its own faith already standing: no second one
    s = _place(w, a, "shrine", a.x + 3, a.y)
    s.belief = "b1"
    assert not [p for _, p in BR.building_options(w, a, random.Random(1)) if p["steps"][-1].get("what") == "shrine"]


def test_the_civic_lists_name_only_real_designs():
    for d in SE.CIVIC + BLD.TOWN_CENTRE:
        assert d in DESIGNS, d


def test_every_purpose_the_guide_names_is_understood():
    """The guide tells a model which purposes the world understands; each of those words, as written, has to be one
    (whole-word matching without the -ing forms refused five of them: Codex, #69)."""
    from chits.brain import prompt as P
    from chits.sim.invent import judge, mentions

    w, _ = _world()
    guide = P.verb_guide(w)
    listed = guide.split("It understands purposes like ", 1)[1].split(")", 1)[0]
    words = [x.strip() for x in listed.replace(", or ", ", ").split(",") if x.strip()]
    assert len(words) == 12, words
    for word in words:
        _, pid, _, _ = judge({"wood": 1, "stone": 1}, word)
        assert pid is not None, word
    for text, kw in (("a cutter", "cut"), ("digging stick", "dig"), ("for carrying water", "carry"), ("dancing", "dance"),
                     ("runners", "run")):
        assert mentions(text, kw), (text, kw)
    for text, kw in (("a pointed stick", "sick"), ("a shoe", "hoe"), ("heat", "eat"), ("wheat", "eat"), ("prune", "run")):
        assert not mentions(text, kw), (text, kw)
