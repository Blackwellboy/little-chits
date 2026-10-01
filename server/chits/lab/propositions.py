"""Deterministic research propositions: facts the simulator can prove without an LLM judge.

This layer is read-only. It never changes a world, a chit, a prompt or an experiment outcome. Keep propositions
narrow: if the simulator cannot point at the evidence, do not emit the claim.
"""

from __future__ import annotations

from typing import Any, Dict, List

DELIVERED_HOW = frozenset({"taught", "read", "observed", "inspected", "raised"})


def snapshot(world, blind: bool = False) -> Dict[str, Any]:
    """Return mechanically provable propositions plus their evidence.

    Blind Lab result files must not reveal an arm through pre-run treatment provenance. The evidence still records
    who learned what, how and when; treatment source ids stay in the separate sealed treatment artifact and are
    included here only for unblinded/direct callers.

    This deliberately does *not* claim that an invention was used successfully yet: current v2 records invention
    creation and physical holdings, but not a generic effect-use event for every invention purpose.
    """
    people = list(world.agents.values()) + list(world.dead.values())
    delivered: List[Dict[str, Any]] = []
    proven: List[Dict[str, Any]] = []
    for a in people:
        for key, k in sorted(a.knows.items()):
            how = k.get("how")
            tick = k.get("tick")
            if how in DELIVERED_HOW and tick is not None:
                ev = {"agent": a.id, "knowledge": key, "how": how, "tick": int(tick)}
                source = k.get("from")
                if source is not None and not (blind and str(source).startswith("treatment:")):
                    ev["source"] = source
                delivered.append(ev)
            # "instinct" and "insight" are marked worked at acquisition for gameplay, not because the chit executed
            # them. All other worked statuses are backed either by discovery/build success or made_it_work().
            if (k.get("status") == "worked" and k.get("worked_tick") is not None
                    and how not in {"instinct", "insight"}):
                proven.append({"agent": a.id, "knowledge": key, "tick": int(k["worked_tick"])})

    civic = getattr(world, "civic", None) or {}
    recent_multi = [{"project": p.get("id"), "kind": p.get("kind"), "key": p.get("key"),
                     "day": p.get("day"), "helpers": int(p.get("helpers", 0))}
                    for p in civic.get("done", []) if int(p.get("helpers", 0)) >= 2]
    multi = {
        "lifetime_count": world.lifetime("project_done", "multi_contributor"),
        "since_tick": int(getattr(world, "tallies_since", 0)),
        "recent_evidence": recent_multi,
    }

    # Physical existence is stronger than an authored invention record: a made unit must still be in a hand/store
    # or have been recorded as made by a chit. We do not infer successful *use* from existence.
    inventions = []
    for key, inv in sorted(getattr(world, "inventions", {}).items()):
        held = sum(a.inventory.get(key, 0) for a in people)
        stored = sum(s.storage.get(key, 0) for s in world.structures.values())
        ground = sum(pile.get(key, 0) for pile in getattr(world, "ground", {}).values())
        made = sum(a.stats.get(f"made_{key}", 0) + a.stats.get(f"produced_{key}", 0) for a in people)
        if held + stored + ground + made > 0:
            inventions.append({"invention": key, "name": inv.get("name", key), "held": held,
                                "stored": stored, "ground": ground, "made": made, "created_tick": inv.get("tick")})

    return {
        "knowledge_was_actually_delivered": delivered,
        "knowledge_was_physically_proven": proven,
        "project_has_multiple_verified_contributors": multi,
        "invention_physically_exists": inventions,
        "unsupported": ["invention_was_used_successfully"],
    }
