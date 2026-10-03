"""SQLite persistence: compressed world snapshots + an append-only event log."""

from __future__ import annotations

import gzip
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

OUTCOME_TICKS = 240 * 7  # action outcomes are kept for the last week of world time


def _epoch_clause(epoch, seq: bool = True) -> tuple:
    """SQL for rows of one timeline. `epoch` is one epoch id (that epoch alone), or World.timeline(): the current
    epoch, then each ancestor up to where it was forked from (by event seq, or by tick for old forks and for tables
    without a seq). Rows written before timelines existed belong to every epoch."""
    parts, args = ["epoch IS NULL", "epoch=''"], []
    for e, until in ([(epoch, None)] if isinstance(epoch, str) else epoch):
        if until is None:
            parts.append("epoch=?")
            args.append(e)
        elif seq and until[0] is not None:
            parts.append("(epoch=? AND seq<=?)")
            args += [e, until[0]]
        else:
            parts.append("(epoch=? AND tick<?)")
            args += [e, until[1]]
    return " AND (" + " OR ".join(parts) + ")", args

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  world_id TEXT NOT NULL, tick INTEGER NOT NULL, created REAL DEFAULT (strftime('%s','now')),
  data BLOB NOT NULL, PRIMARY KEY (world_id, tick)
);
CREATE TABLE IF NOT EXISTS events (
  world_id TEXT NOT NULL, seq INTEGER NOT NULL, tick INTEGER NOT NULL, kind TEXT NOT NULL,
  importance INTEGER NOT NULL, actor TEXT, text TEXT NOT NULL, data TEXT, PRIMARY KEY (world_id, seq)
);
CREATE INDEX IF NOT EXISTS events_by_tick ON events (world_id, tick);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  world_id TEXT NOT NULL, tick INTEGER NOT NULL, agent_id TEXT, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS decisions_by_world ON decisions (world_id, tick);
CREATE TABLE IF NOT EXISTS keyframes (
  world_id TEXT, tick INTEGER, data TEXT, world_uuid TEXT, epoch TEXT, PRIMARY KEY(world_id, tick)
);
CREATE TABLE IF NOT EXISTS savepoints (
  id INTEGER PRIMARY KEY, name TEXT, created REAL, tick INTEGER, data TEXT
);
CREATE TABLE IF NOT EXISTS quarantine (
  world_id TEXT NOT NULL, saved REAL DEFAULT (strftime('%s','now')), data BLOB, error TEXT
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.execute("PRAGMA journal_mode=WAL")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(events)")}
        for col in ("world_uuid", "epoch"):
            if col not in cols:
                self.db.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT")
        self.db.execute("CREATE INDEX IF NOT EXISTS events_by_epoch ON events (world_id, epoch)")
        if "summary" not in {r[1] for r in self.db.execute("PRAGMA table_info(savepoints)")}:
            self.db.execute("ALTER TABLE savepoints ADD COLUMN summary TEXT")  # what the Saves list shows
        self.db.commit()
        self._migrate_timelines()

    def _migrate_timelines(self) -> None:
        """Retain old evidence while giving restored timelines independent identities."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            pk = [r[1] for r in self.db.execute("PRAGMA table_info(events)") if r[5]]
            if "epoch" not in pk:
                self.db.execute("CREATE TABLE events_v3 (world_id TEXT NOT NULL, seq INTEGER NOT NULL, tick INTEGER NOT NULL, "
                                "kind TEXT NOT NULL, importance INTEGER NOT NULL, actor TEXT, text TEXT NOT NULL, data TEXT, "
                                "world_uuid TEXT NOT NULL DEFAULT '', epoch TEXT NOT NULL DEFAULT '', "
                                "PRIMARY KEY(world_id, world_uuid, epoch, seq))")
                self.db.execute("INSERT INTO events_v3 SELECT world_id,seq,tick,kind,importance,actor,text,data,"
                                "coalesce(world_uuid,''),coalesce(epoch,'') FROM events")
                self.db.execute("DROP TABLE events")
                self.db.execute("ALTER TABLE events_v3 RENAME TO events")
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(snapshots)")}
            if "epoch" not in cols:
                self.db.execute("CREATE TABLE snapshots_v3 (world_id TEXT NOT NULL, tick INTEGER NOT NULL, "
                                "created REAL DEFAULT (strftime('%s','now')), data BLOB NOT NULL, "
                                "world_uuid TEXT NOT NULL DEFAULT '', epoch TEXT NOT NULL DEFAULT '', "
                                "PRIMARY KEY(world_id, world_uuid, epoch, tick))")
                for wid, tick, created, data in self.db.execute("SELECT world_id,tick,created,data FROM snapshots").fetchall():
                    try:
                        d = json.loads(gzip.decompress(data))
                    except (OSError, ValueError, EOFError):
                        d = {}  # preserve unreadable originals for the existing quarantine path
                    if not isinstance(d, dict):
                        d = {}
                    self.db.execute("INSERT INTO snapshots_v3 VALUES (?,?,?,?,?,?)",
                                    (wid, tick, created, data, d.get("uuid", ""), d.get("epoch", "")))
                self.db.execute("DROP TABLE snapshots")
                self.db.execute("ALTER TABLE snapshots_v3 RENAME TO snapshots")
            pk = [r[1] for r in self.db.execute("PRAGMA table_info(keyframes)") if r[5]]
            if "epoch" not in pk:
                self.db.execute("CREATE TABLE keyframes_v3 (world_id TEXT, tick INTEGER, data TEXT, "
                                "world_uuid TEXT NOT NULL DEFAULT '', epoch TEXT NOT NULL DEFAULT '', "
                                "PRIMARY KEY(world_id, world_uuid, epoch, tick))")
                self.db.execute("INSERT INTO keyframes_v3 SELECT world_id,tick,data,coalesce(world_uuid,''),coalesce(epoch,'') FROM keyframes")
                self.db.execute("DROP TABLE keyframes")
                self.db.execute("ALTER TABLE keyframes_v3 RENAME TO keyframes")
            self.db.execute("CREATE INDEX IF NOT EXISTS events_by_tick ON events(world_id,tick)")
            self.db.execute("CREATE INDEX IF NOT EXISTS events_by_epoch ON events(world_id,epoch)")
            self.db.execute("CREATE TABLE IF NOT EXISTS action_outcomes (world_id TEXT, tick INTEGER, plan_id TEXT, data TEXT NOT NULL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS actions_by_plan ON action_outcomes(world_id,plan_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS actions_by_tick ON action_outcomes(world_id,tick)")
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', '3')")

    def save_world(self, world_dict: Dict[str, Any], keep: int = 6, *, events=None, outcomes=None,
                   outcome_ticks: int = OUTCOME_TICKS) -> None:
        blob = gzip.compress(json.dumps(world_dict, separators=(",", ":")).encode(), 1)  # level 5 took twice as long for 25% less
        wid, tick = world_dict["id"], world_dict["tick"]
        identity = (wid, world_dict.get("uuid", ""), world_dict.get("epoch", ""))
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO snapshots (world_id,tick,data,world_uuid,epoch) VALUES (?,?,?,?,?)",
                            (wid, tick, blob, identity[1], identity[2]))
            self.db.execute("DELETE FROM snapshots WHERE world_id=? AND world_uuid=? AND epoch=? AND tick NOT IN "
                            "(SELECT tick FROM snapshots WHERE world_id=? AND world_uuid=? AND epoch=? ORDER BY tick DESC LIMIT ?)",
                            (*identity, *identity, keep))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                            ("active_snapshot:" + wid, json.dumps([identity[1], identity[2], tick])))
            if events:
                self._insert_events(identity, events)
            if outcomes:
                self.db.executemany("INSERT INTO action_outcomes VALUES (?,?,?,?)",
                                    [(wid, x["tick"], x.get("plan_id"), json.dumps(x)) for x in outcomes])
                # every finished step is a row: two 60-chit worlds wrote tens of MB a day
                self.db.execute("DELETE FROM action_outcomes WHERE world_id=? AND tick<?", (wid, tick - outcome_ticks))

    def load_world(self, world_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            active = self.db.execute("SELECT value FROM meta WHERE key=?", ("active_snapshot:" + world_id,)).fetchone()
            if active:
                uuid, epoch, tick = json.loads(active[0])
                row = self.db.execute("SELECT data FROM snapshots WHERE world_id=? AND world_uuid=? AND epoch=? AND tick=?",
                                      (world_id, uuid, epoch, tick)).fetchone()
                if row is None:
                    raise RuntimeError("active checkpoint is missing; refusing a different timeline")
            else:
                row = self.db.execute("SELECT data FROM snapshots WHERE world_id=? ORDER BY tick DESC LIMIT 1",
                                      (world_id,)).fetchone()
        return json.loads(gzip.decompress(row[0])) if row else None

    def action_outcomes(self, world_id: str, plan_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query, args = "SELECT data FROM action_outcomes WHERE world_id=?", [world_id]
        if plan_id:
            query += " AND plan_id=?"
            args.append(plan_id)
        with self.lock:
            rows = self.db.execute(query + " ORDER BY rowid DESC LIMIT ?", [*args, limit]).fetchall()
        return [json.loads(row[0]) for row in rows]

    def has_future_events(self, world) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM events WHERE world_id=? AND world_uuid=? AND epoch=? AND tick>? LIMIT 1",
                                   (world.id, world.uuid, world.epoch, world.tick)).fetchone() is not None

    def quarantine_world(self, world_id: str, error: str) -> None:
        """Set an unreadable save aside (instead of silently overwriting it) and remove it from the snapshots."""
        with self.lock:
            rows = self.db.execute("SELECT data FROM snapshots WHERE world_id=?", (world_id,)).fetchall()
            for (data,) in rows:
                self.db.execute("INSERT INTO quarantine (world_id, data, error) VALUES (?,?,?)", (world_id, data, error[:500]))
            self.db.execute("DELETE FROM snapshots WHERE world_id=?", (world_id,))
            self.db.execute("DELETE FROM meta WHERE key=?", ("active_snapshot:" + world_id,))
            self.db.commit()

    def save_decision(self, rec: Dict[str, Any]) -> None:
        with self.lock:
            self.db.execute("INSERT INTO decisions VALUES (?,?,?,?)",
                            (rec.get("world"), rec.get("tick_requested") or 0, rec.get("agent"), json.dumps(rec, default=str)))
            self.db.commit()

    def decisions(self, world_id: Optional[str] = None, agent_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        q, args = "SELECT data FROM decisions WHERE 1=1", []
        if world_id:
            q += " AND world_id=?"
            args.append(world_id)
        if agent_id:
            q += " AND agent_id=?"
            args.append(agent_id)
        q += " ORDER BY rowid DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute(q, args).fetchall()]

    def _insert_events(self, identity, events) -> None:
        wid, wuuid, epoch = identity
        rows = [(wid, e.seq, e.tick, e.kind, e.importance, e.actor, e.text, json.dumps(e.data, default=str), wuuid or "", epoch or "")
                for e in events]
        self.db.executemany("INSERT OR IGNORE INTO events (world_id,seq,tick,kind,importance,actor,text,data,world_uuid,epoch) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    def append_events(self, world, events: List[Any]) -> None:
        if not events:
            return
        identity = (world, "", "") if isinstance(world, str) else (world.id, world.uuid, world.epoch)
        with self.lock, self.db:
            self._insert_events(identity, events)

    def events(self, world_id: str, *, since_tick: int = 0, until_tick: Optional[int] = None,
               min_importance: int = 1, limit: int = 500, epoch: Any = None) -> List[Dict[str, Any]]:
        q = "SELECT seq, tick, kind, importance, actor, text, data FROM events WHERE world_id=? AND tick>=? AND importance>=?"
        args: List[Any] = [world_id, since_tick, min_importance]
        if epoch:
            clause, more = _epoch_clause(epoch)
            q += clause
            args += more
        if until_tick is not None:
            q += " AND tick<?"
            args.append(until_tick)
        q += " ORDER BY seq DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        out = [{"seq": r[0], "tick": r[1], "kind": r[2], "importance": r[3], "actor": r[4], "text": r[5],
                "data": json.loads(r[6] or "{}")} for r in rows]
        out.reverse()
        return out

    def count_kinds(self, world_id: str, kinds, epoch: Any = None, unless: str = "") -> Dict[str, int]:
        """How many events of each kind a world's timeline holds (`unless`: not those whose data has that key)."""
        kinds = list(kinds)
        q = f"SELECT kind, COUNT(*) FROM events WHERE world_id=? AND kind IN ({','.join('?' * len(kinds))})"
        args: List[Any] = [world_id, *kinds]
        if unless:
            q += " AND (data IS NULL OR json_extract(data, '$.' || ?) IS NULL)"
            args.append(unless)
        if epoch:
            clause, more = _epoch_clause(epoch)
            q += clause
            args += more
        with self.lock:
            return dict(self.db.execute(q + " GROUP BY kind", args).fetchall())

    # replay keyframes (T33): a compact picture every 24 ticks, thinned to one a day after 60 days
    def save_keyframe(self, world_id: str, tick: int, data: Dict[str, Any], world_uuid: str = "", epoch: str = "") -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO keyframes (world_id, tick, data, world_uuid, epoch) VALUES (?,?,?,?,?)",
                            (world_id, tick, json.dumps(data, separators=(",", ":")), world_uuid or "", epoch or ""))
            self.db.commit()

    def keyframes(self, world_id: str, from_tick: int = 0, to_tick: Optional[int] = None,
                  epoch: Any = None) -> List[Dict[str, Any]]:
        q = "SELECT data FROM keyframes WHERE world_id=? AND tick>=?"
        args: List[Any] = [world_id, from_tick]
        if to_tick is not None:
            q += " AND tick<=?"
            args.append(to_tick)
        if epoch:
            clause, more = _epoch_clause(epoch, seq=False)
            q += clause
            args += more
        with self.lock:
            rows = self.db.execute(q + " ORDER BY tick", args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def thin_keyframes(self, world_id: str, before_tick: int) -> None:
        """Cold tier: older than this, keep only one keyframe per in-game day."""
        with self.lock:
            self.db.execute("DELETE FROM keyframes WHERE world_id=? AND tick<? AND tick % 240 != 0", (world_id, before_tick))
            self.db.commit()

    # save points (T28): every world at one moment, to rewind to after meddling
    def save_point(self, name: str, tick: int, worlds: Dict[str, Any], summary: Optional[Dict[str, Any]] = None) -> int:
        import time as _time

        with self.lock:
            cur = self.db.execute("INSERT INTO savepoints (name, created, tick, data, summary) VALUES (?,?,?,?,?)",
                                  (name, _time.time(), tick, json.dumps(worlds, separators=(",", ":")),
                                   json.dumps(summary) if summary is not None else None))
            self.db.commit()
            return int(cur.lastrowid)

    def save_summaries(self, summarise) -> List[Dict[str, Any]]:
        """Save points, newest first, each with its summary (day, population, era). A save made before summaries
        were kept gets one from its own data, once (`summarise(worlds) -> dict`)."""
        with self.lock:
            rows = self.db.execute("SELECT id, name, created, tick, summary FROM savepoints ORDER BY id DESC").fetchall()
        out = []
        for sid, name, created, tick, summary in rows:
            if summary is None:
                sp = self.load_save_point(sid)
                try:
                    made = summarise(sp["worlds"]) if sp else {}
                except Exception:
                    made = {}  # (an unreadable old save still lists, and can still be deleted)
                summary = json.dumps(made)
                with self.lock:
                    self.db.execute("UPDATE savepoints SET summary=? WHERE id=?", (summary, sid))
                    self.db.commit()
            out.append({"id": sid, "name": name, "created": created, "tick": tick, **json.loads(summary)})
        return out

    def save_points(self) -> List[Dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT id, name, created, tick FROM savepoints ORDER BY id DESC").fetchall()
        return [{"id": r[0], "name": r[1], "created": r[2], "tick": r[3]} for r in rows]

    def load_save_point(self, sid: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            r = self.db.execute("SELECT id, name, tick, data FROM savepoints WHERE id=?", (sid,)).fetchone()
        return {"id": r[0], "name": r[1], "tick": r[2], "worlds": json.loads(r[3])} if r else None

    def delete_save_point(self, sid: int) -> bool:
        with self.lock:
            cur = self.db.execute("DELETE FROM savepoints WHERE id=?", (sid,))
            self.db.commit()
            return cur.rowcount > 0

    def wipe(self) -> None:
        with self.lock:
            self.db.execute("DELETE FROM snapshots")
            self.db.execute("DELETE FROM events")
            self.db.execute("DELETE FROM decisions")
            self.db.execute("DELETE FROM keyframes")
            self.db.execute("DELETE FROM action_outcomes")
            self.db.execute("DELETE FROM meta WHERE key LIKE 'active_snapshot:%'")
            self.db.commit()

    def get_meta(self, key: str) -> Optional[str]:
        with self.lock:
            r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
            self.db.commit()
