"""R3 item 13 first slice: proposition monitors say only what simulator evidence proves."""

import copy

from chits.lab import propositions
from chits.sim.world import World


def test_propositions_are_read_only_and_evidence_backed():
    w = World("A", "A", 7, "direct", 64, 3)
    a, b = list(w.agents.values())[:2]
    a.learn("recipe:cord", "taught", 12, source=b.id)
    a.made_it_work("recipe:cord", 20)
    w.civic["done"].append({"id": "p1", "kind": "build", "key": "well", "day": 3, "helpers": 2})

    before = copy.deepcopy(w.to_dict())
    out = propositions.snapshot(w)
    assert w.to_dict() == before

    d = next(x for x in out["knowledge_was_actually_delivered"] if x["knowledge"] == "recipe:cord")
    assert d == {"agent": a.id, "knowledge": "recipe:cord", "how": "taught", "tick": 12, "source": b.id}
    p = next(x for x in out["knowledge_was_physically_proven"] if x["knowledge"] == "recipe:cord")
    assert p["agent"] == a.id and p["tick"] == 20
    assert out["project_has_multiple_verified_contributors"] == {
        "lifetime_count": 0, "since_tick": 0,
        "recent_evidence": [{"project": "p1", "kind": "build", "key": "well", "day": 3, "helpers": 2}],
    }
    assert "invention_was_used_successfully" in out["unsupported"]


def test_invention_existence_requires_physical_evidence():
    w = World("A", "A", 9, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    key = "inv_a_1"
    w.inventions[key] = {"key": key, "name": "Thing", "tick": 5, "by": a.id}
    assert propositions.snapshot(w)["invention_physically_exists"] == []

    # A manufactured/held unit is a fact; this still does not claim its authored effect was successfully used.
    a.inventory[key] = 1
    got = propositions.snapshot(w)["invention_physically_exists"]
    assert got == [{"invention": key, "name": "Thing", "held": 1, "stored": 0, "ground": 0,
                    "made": 0, "created_tick": 5}]


def test_blind_propositions_do_not_reveal_treatment_source():
    w = World("A", "A", 11, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.learn("recipe:cord", "taught", 0, source="treatment:keepers@1")

    blind = propositions.snapshot(w, blind=True)
    ev = next(x for x in blind["knowledge_was_actually_delivered"] if x["knowledge"] == "recipe:cord")
    assert "source" not in ev
    assert "treatment" not in str(blind)

    unblinded = propositions.snapshot(w)
    ev = next(x for x in unblinded["knowledge_was_actually_delivered"] if x["knowledge"] == "recipe:cord")
    assert ev["source"] == "treatment:keepers@1"



def test_instinct_and_unexecuted_insight_are_not_claimed_as_physically_proven():
    w = World("A", "A", 13, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.learn("recipe:paper", "insight", 7)
    got = propositions.snapshot(w)["knowledge_was_physically_proven"]
    keys = {x["knowledge"] for x in got if x["agent"] == a.id}
    assert "recipe:paper" not in keys
    assert "design:hut" not in keys and "design:campfire" not in keys


def test_multi_contributor_project_has_lifetime_tally_even_after_recent_window_forgets_it():
    w = World("A", "A", 15, "direct", 64, 2)
    w.emit("project_done", "done", 5, evidence="multi_contributor")
    # Recent civic detail may be capped independently; the proposition's run-level count is durable.
    got = propositions.snapshot(w)["project_has_multiple_verified_contributors"]
    assert got["lifetime_count"] == 1 and got["since_tick"] == 0


def test_dropped_invention_still_physically_exists():
    w = World("A", "A", 17, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    key = "inv_drop"
    w.inventions[key] = {"key": key, "name": "Dropped thing", "tick": 2, "by": a.id}
    w.ground["1,1"] = {key: 1, "_t": w.tick}
    got = propositions.snapshot(w)["invention_physically_exists"]
    assert got and got[0]["ground"] == 1
