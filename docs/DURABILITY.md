# Durability boundary

Little Chits keeps the live simulation in memory and persists it to SQLite as atomic checkpoints.

## What is authoritative

A checkpoint is one transaction containing:

- the compressed world snapshot at tick `T`;
- all new events represented by that snapshot;
- pending action-outcome rows;
- the `active_snapshot:<world>` pointer to tick `T`.

SQLite either commits that set together or rolls it back together. An event is therefore never intentionally
acknowledged as durable ahead of the state that produced it.

The runtime checkpoints every **60 ticks** (and at explicit saves / other durability boundaries). At the normal 1x
clock that is about 30 seconds. Between checkpoints the live in-memory world is newer than durable storage; a process
or machine crash may therefore roll back to the last committed tick. New matches also commit tick 0 before they are
allowed to run.

The current durable tick for each world is exposed in `/api/control`, `/api/diagnostics`, and the run manifest.

## A failed checkpoint

A failed checkpoint is not treated as a harmless logging error.

1. The database transaction rolls back.
2. The runtime records the error and **pauses every world immediately**. The inner stepping loop also checks the
   paused flag, so the in-memory/durable gap cannot continue growing during the same burst.
3. Play mode may retry the exact current state with `POST /api/save`. A successful retry clears that world's
   storage error. Resuming is refused while any storage error remains.
4. An **experiment** is permanently marked invalid after any durability failure. A later successful save can preserve
   the state for inspection, but that run cannot be resumed as a valid experiment; start a fresh experiment instead.

A skip ahead (the ⏩ control, play only) stops at once on a failed checkpoint and the game stays paused as above. A
skip also stops on a failed write that normal play only logs (a replay keyframe, a chronicle page, the diagnostics
log), so a long stretch is never run at full speed on storage that is failing.

Save files (the 💾 Saves entry, play only) add nothing to this boundary: an export reads a stored save point, and an
import adds one save-point row after the file has been checked. Loading a save is the save-point restore.

## Restoring a save point

A restore (god mode's Restore, or Load in Saves) replaces every world of the save as a unit:

1. every replacement world is built from the save first; a save that does not load changes nothing;
2. every world about to be replaced is checkpointed; if one checkpoint fails the game pauses as above, and every
   world in memory is still the current one;
3. one transaction commits, for all the restored worlds together, the events their snapshots carried, each world's
   first checkpoint in its new timeline, each `active_snapshot:<world>` pointer, and the sandbox mark;
4. only after that commit do the restored worlds replace the running ones.

So storage and memory never hold one world rewound and its twin not: after a failure at any step the running worlds
and the active pointers are all the pre-restore ones, and a restart resumes those.

A restart always follows `active_snapshot:<world>` and therefore resumes the last committed checkpoint, not whatever
newer tick happened to exist only in the dead process's memory.

## Claim boundary

This is checkpoint durability, not synchronous persistence of every simulation tick. Claims should say that the
runtime is crash-consistent at its explicit checkpoint boundary and may lose the in-memory suffix since the previous
checkpoint on an abrupt process/machine loss.
