"""Belief spam: once a few faiths exist, new convictions mostly join one, and chits can join by name."""

import json

from chits.brain import prompt as P
from chits.brain.mind import apply_reflection
from chits.sim.world import World


def fresh(n=8, culture="direct"):
    w = World("A", "A", 3, culture, 64, n)
    ags = list(w.agents.values())
    for a in ags:
        a.x, a.y = 30, 30
    return w, ags


def test_new_faiths_are_rare_once_a_few_exist():
    w, ags = fresh()
    tenets = ["The fire remembers those who feed it", "The sea gives and the sea takes",
              "Stone endures where flesh does not"]
    for a, t in zip(ags, tenets):
        assert w.found_belief(a, f"Way {t.split()[1]}", t)
    assert len(w.beliefs) == 3
    # a fourth, soon after, from a chit that has heard the fire faith preached: it says much the same, so
    # its chit joins that one
    fire_id = next(b for b, v in w.beliefs.items() if "fire" in v["tenet"])
    ags[3].met_beliefs.append(fire_id)
    assert w.found_belief(ags[3], "Keepers of Embers", "Those who feed the fire are remembered") is None
    fire = next(b for b in w.beliefs.values() if "fire" in b["tenet"])
    assert len(w.beliefs) == 3 and ags[3].belief == fire["id"] and ags[3].id in fire["followers"]
    # nothing in common with any faith: kept to itself, no new faith
    assert w.found_belief(ags[4], "Quiet", "Silence holds wisdom") is None
    assert ags[4].belief == "" and len(w.beliefs) == 3
    # after two quiet days a genuinely new faith may appear again
    w.tick += 2 * 240
    assert w.found_belief(ags[5], "The Long Road", "Walk far and learn much") and len(w.beliefs) == 4


def test_reflection_can_join_a_belief_by_name_and_sees_the_ones_around():
    w, (a, b, c, *_) = fresh()
    w.found_belief(a, "The Ember Way", "The fire remembers those who feed it")
    # a neighbour's faith is only listed once the chit has met it: here, a close friend's
    assert "Beliefs held around you" not in json.dumps(P.reflection_messages(w, b))
    b.affinity[a.id] = 40.0
    msgs = P.reflection_messages(w, b)
    text = msgs[0]["content"] + msgs[1]["content"]
    assert "The Ember Way (founded by" in text and 'you may join it' in text
    apply_reflection(w, b, json.dumps({"lessons": [], "belief": {"name": "the ember way"}}))
    assert b.belief == a.belief and len(w.beliefs) == 1
    # a stigmergy world can't be told what others believe: nothing listed without a shrine in sight
    wb, (x, y, *_) = fresh(culture="stigmergy")
    wb.found_belief(x, "The Ember Way", "The fire remembers those who feed it")
    assert "Beliefs held around you" not in json.dumps(P.reflection_messages(wb, y))


def test_a_conviction_only_joins_a_faith_the_chit_has_met():
    w, ags = fresh()
    for a, t in zip(ags, ["The fire remembers those who feed it", "The sea gives and the sea takes",
                          "Stone endures where flesh does not"]):
        w.found_belief(a, f"Way {t.split()[1]}", t)
    stranger = ags[5]  # shares words with the fire faith, but nobody preached it to them
    assert w.found_belief(stranger, "Embers", "Those who feed the fire are remembered") is None
    assert stranger.belief == ""
