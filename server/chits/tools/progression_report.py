"""Read-only audit of a saved run: python -m chits.tools.progression_report --db PATH --world A.

This does not instantiate Runtime/Store, migrate the database, contact a model, or write files.
Executed steps are not labelled useful; capability use still needs domain-specific evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3


def report(path: Path, world: str = "A", since_tick: int = 0) -> dict:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    try:
        active = db.execute("SELECT value FROM meta WHERE key=?", ("active_snapshot:" + world,)).fetchone()
        if active:
            uuid, epoch, tick = json.loads(active[0])
            row = db.execute("SELECT data FROM snapshots WHERE world_id=? AND world_uuid=? AND epoch=? AND tick=?",
                             (world, uuid, epoch, tick)).fetchone()
        else:
            row = db.execute("SELECT data FROM snapshots WHERE world_id=? ORDER BY tick DESC LIMIT 1", (world,)).fetchone()
        if not row:
            raise ValueError("No saved checkpoint for world " + world)
        snapshot = json.loads(gzip.decompress(row[0]))
        epoch = snapshot.get("epoch")
        decisions = {}
        for data, in db.execute("SELECT data FROM decisions WHERE world_id=? AND tick>=?", (world, since_tick)):
            record = json.loads(data)
            if record.get("epoch") == epoch and record.get("tick_resolved", snapshot["tick"]) is not None and record.get("tick_resolved", 0) <= snapshot["tick"]:
                decisions[record["request_id"]] = record
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        actions = []
        if "action_outcomes" in tables:
            for data, in db.execute("SELECT data FROM action_outcomes WHERE world_id=? AND tick>=? AND tick<=?",
                                   (world, since_tick, snapshot["tick"])):
                record = json.loads(data)
                if record.get("epoch") == epoch:
                    actions.append(record)
        capabilities = {}
        for a in snapshot["agents"]:
            for key, knowledge in a["knows"].items():
                if key.startswith("recipe:"):
                    row = capabilities.setdefault(key, {"known_by": 0, "worked_by": 0, "held_units": 0, "stored_units": 0})
                    row["known_by"] += 1
                    row["worked_by"] += knowledge.get("status") == "worked"
        for key, row in capabilities.items():
            item = key.split(":", 1)[1]
            row["held_units"] = sum(a["inventory"].get(item, 0) for a in snapshot["agents"])
            row["stored_units"] = sum(s.get("storage", {}).get(item, 0) for s in snapshot["structures"]
                                      if s.get("durability", 0) > 0 and s.get("complete"))
        successful = {a.get("decision_id") for a in actions if a["outcome"] == "executed" and a.get("decision_id") in decisions}
        return {"world": world, "epoch": epoch, "checkpoint_tick": snapshot["tick"], "since_tick": since_tick,
                "decision_outcomes": dict(Counter(r.get("outcome") for r in decisions.values())),
                "decision_styles": dict(Counter(r.get("style", "full") for r in decisions.values())),
                "escalations_requested": sum(bool(r.get("choice", {}).get("escalation_requested")) for r in decisions.values()),
                "escalations_granted": sum(bool(r.get("choice", {}).get("escalated")) for r in decisions.values()),
                "action_outcomes": dict(Counter(a["outcome"] for a in actions)),
                "action_sources": dict(Counter(a["source"] for a in actions)),
                "decisions_with_executed_steps": len(successful), "capabilities": capabilities,
                "limits": ["Executed does not mean useful or novel.", "No action outcomes exist before this audit build.",
                           "A worked recipe is demonstrated knowledge, not a continuing production rate."]}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--world", default="A")
    parser.add_argument("--since-tick", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(report(args.db, args.world, args.since_tick), indent=2))


if __name__ == "__main__":
    main()
