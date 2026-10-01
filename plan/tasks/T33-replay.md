# T33 · Replays you can share

**Why:** a civilisation takes hours to grow, and nobody watches all of it. Replays let you scrub back through
the whole history, and a replay bundle is a single file anyone can open in their browser, with no GPU and no
server. "Here are 40 days of my two AIs, watch it yourself" is the post.

## Build
1. **Keyframes.**
   - `Runtime.record_keyframe(world)` stores a compact frame in a new store table
     `keyframes(world_id TEXT, tick INTEGER, data TEXT, PRIMARY KEY(world_id, tick))`.
   - `data` is JSON `{"t": tick, "a": [[id, x, y, activity], …], "s": <structures>}`. `s` is the full
     structure list (`views`' compact form) every 240 ticks, and `null` otherwise.
   - The runtime loop calls it every 24 ticks per world. Retention has two tiers, so the whole history stays
     replayable:
     - **hot:** every 24 ticks for the last 60 in-game days
     - **cold:** older keyframes are thinned daily to one per 240 ticks, and kept
   - Keyframes, the replay API and bundles carry `world_uuid` and `epoch` (F3). A replay never mixes epochs:
     `?epoch=` selects one, defaulting to the current epoch.
   - `Store.keyframes(world_id, from_tick, to_tick) -> list`.
2. **API.**
   - `GET /api/worlds/{wid}/replay?from=&to=` returns `{"meta": world_meta, "keyframes": [...], "events":
     [...]}`, where `events` are the importance ≥ 2 events in range.
   - `GET /api/replay/export?days=N` (default 7) returns a downloadable JSON bundle:
     `{"version": 1, "exported": iso time, "mode", "worlds": {wid: {"meta", "brain", "terrain":
     {"size", "seed", "tiles": base64 of the tile bytes}, "keyframes", "events", "names": {id: name}}}}`.
3. **Viewer.**
   - `web/replay.html` plus `web/src/replay.tsx` is a standalone page. Add it as a second Vite input, so
     `web/dist/replay.html` is built.
   - It loads a bundle from `?src=<url>`, or by drag and drop. It draws the terrain and chits with the same
     renderer, interpolating between keyframes.
   - It has a play/pause button, speed control (1×–32×), a timeline scrubber with event markers, and split
     view for two worlds.
   - It needs no server API.
4. **In the live app.**
   - A ▶ **Replay** button in the top bar opens a scrubber over the live world, using `/replay`. Leaving it
     returns to live.
   - The ⬇ in the Stats tab downloads the bundle.

5. **One view cursor.** While replaying, every panel reads the same `ViewCursor` (world, epoch, tick): map,
   Inspector, knowledge, relationships, chronicle. A Day-10 view never shows Day-40 knowledge.

## Done when
`python scripts/plan.py verify T33` passes.
