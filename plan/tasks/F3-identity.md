# F3 · World identity, timelines and versioned saves

**Why:** "World A, tick 5000" stops meaning one thing once there are new games, save-point restores, replays
and contact. Every world needs a durable identity, and every history needs a timeline id, so events, replays
and posts can never splice two futures together.

## Build
1. **Identity.** Persist all of these:
   - `World.uuid`: a uuid4 hex made when the world is created. `"A"`/`"B"` stays as the display slot (`world.id`).
   - `World.epoch`: a uuid4 hex for the current timeline, made at creation.
   - `World.epochs`: a list of `{"epoch", "parent", "from_tick", "created"}`, starting with the first epoch
     (parent `None`, `from_tick` 0).
   - `World.fork_epoch(reason) -> str` makes a new epoch whose parent is the current one and whose
     `from_tick` is the current tick, appends it, emits `"timeline"` (importance 2, `A new timeline begins
     ({reason})`) and returns the new id. Restoring a save point (T28), and anything else that rewinds time,
     must call it.
2. **Versioned snapshots.**
   - `to_dict()` includes `"schema": SNAPSHOT_SCHEMA` (2), `"uuid"`, `"epoch"`, `"epochs"` and `"build"`
     (`git rev-parse --short HEAD` at startup, or `"unknown"`).
   - `from_dict` does the following:
     - schema missing or 1: **migrate**, making a fresh uuid and epoch
     - schema 2: load as-is
     - a schema newer than the code: raise `ValueError("snapshot schema N is newer than this build")`
   - Migrations live in one function `migrate_snapshot(d) -> d`.
3. **Events carry identity.**
   - The store's `events` table gains `world_uuid` and `epoch` columns. Add them with a guarded `ALTER TABLE`
     in `Store.__init__`, and track `schema_version` in meta.
   - `Store.append_events(world, events)` records the world's current uuid and epoch.
   - `Store.events(world_id, …, epoch=None)` filters to the given epoch, or to the world's current epoch
     when the caller passes `epoch="current"` together with a world. The runtime's API endpoints read
     only the current epoch.
4. **Views.**
   - `views.world_meta` includes `uuid` and `epoch`. The run manifest (F1) includes both.
   - Decision records (F2) include `epoch`.

## Done when
`python scripts/plan.py verify F3` passes.
