"""Knowledge that outlives its keepers (sim/lore.py): an old last keeper passes it on by what its culture allows,
and a village that loses its last keeper is told it has forgotten."""

import random

from chits import views
from chits.brain import civic
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import lore
from chits.sim.world import CULTURE_FLAGS, World


def _village(culture="direct", n=4):
    w = World("A", "A", 5, culture, 64, n)
    a, *others = list(w.agents.values())
    for o in w.agents.values():
        o.x, o.y = a.x + (o is not a), a.y
        o.hunger = o.energy = o.warmth = 95.0
    a.learn("recipe:cord", "discovered", w.tick)
    w.first["recipe:cord"] = {"tick": 0, "by": a.id, "name": a.name}
    return w, a, others


def _grow_old(w, a):
    w.tick = a.born + int(lore.OLD * a.lifespan) + 1


def test_the_last_old_keeper_is_named_once_and_its_death_is_a_forgetting():
    w, a, others = _village()
    assert lore.at_risk(w) == [("recipe:cord", a)] and lore.last_of(w, a) == []  # young yet
    _grow_old(w, a)
    assert lore.last_of(w, a) == ["recipe:cord"]
    lore.daily(w)
    lore.daily(w)
    said = [e for e in w.events if e.kind == "last_keeper"]
    assert len(said) == 1 and a.name in said[0].text and "cord" in said[0].text
    assert views.progress(w, [])["at_risk"][0]["keeper"] == a.name
    w.kill(a, "old age")
    gone = [e for e in w.events if e.kind == "forgotten"]
    assert len(gone) == 1 and "cord" in gone[0].text


def test_nothing_is_forgotten_while_someone_else_knows_it():
    w, a, (b, *_) = _village()
    b.learn("recipe:cord", "taught", w.tick, a.id)
    assert lore.at_risk(w) == []
    w.kill(a, "old age")
    assert not any(e.kind == "forgotten" for e in w.events)


def test_an_old_last_keeper_passes_it_on_by_what_its_culture_allows():
    for culture, verb in (("direct", "teach"), ("stigmergy", "craft")):
        w, a, others = _village(culture)
        a.inventory.update(fiber=4)
        _grow_old(w, a)
        opts = civic.lore_options(Instinct(), w, a, random.Random(1))
        assert opts, culture
        weight, plan = opts[0]
        verbs = [s["do"] for s in plan["steps"]]
        assert verb in verbs and plan["goal"] == "pass on how to make cord", (culture, verbs)
        if not CULTURE_FLAGS[culture]["teach"]:
            assert "teach" not in verbs and "say" not in verbs  # no telling where chits can't talk
        line = P.lore_line(w, a)
        assert "last one alive" in line and (("teach" in line) is CULTURE_FLAGS[culture]["teach"]), line
        assert line in P.scene(w, a)
    # a young keeper, or one who isn't the last, isn't hurried
    w, a, (b, *_) = _village()
    assert civic.lore_options(Instinct(), w, a, random.Random(1)) == [] and P.lore_line(w, a) == ""
