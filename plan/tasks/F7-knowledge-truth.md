# F7 · What a chit believes vs what it has seen work, and who told whom

**Why:** "Mo told Lina how to make cord" is not the same as "Lina has made cord". A reflection that says
"copper cures sickness" isn't learning. For the twin-world experiment we need trustworthy lineage: *who
delivered what to whom, through which channel*, and whether the recipient ever made it work.

## Build
1. **Knowledge status.** Each `a.knows[k]` entry gains `"status"`:
   - `discovered`, `insight` and `built` → `"worked"`
   - `taught` and `read` → `"told"`
   - `observed` and `inspected` → `"seen"`

   A `told`/`seen` entry becomes `"worked"` (with `"worked_tick"`) the first time the chit crafts that recipe
   or completes that design. Old snapshots load with the status derived from `how`.
   - `scene()` marks untested knowledge `(told, untried)` or `(seen, untried)`.
   - The Knowledge tab shows how many chits *know* a thing versus how many have *made it work*.
2. **Deliveries.** `World.deliveries` keeps the last 3000 records and persists the last 500:
   `{"tick", "channel": "say"|"teach"|"write"|"read"|"observe"|"inspect"|"sign", "from": agent id|None,
   "to": agent id, "knowledge": key|None, "message": text|None}`.
   - `say` records one per listener who heard it.
   - `teach` records one on success, `read` one per tablet read, and `observe`/`inspect` one when knowledge
     is gained. `sign` belongs to T07.
   - `GET /api/worlds/{wid}/lineage/{knowledge}` returns the first discovery plus the chain of deliveries and
     `worked` events for that key, in order.
3. **Lessons cite memories.**
   - `Memory` gains `id: int`, per agent and increasing, persisted, and assigned in `Agent.remember`.
   - `reflection_messages` lists memories as `[m12] …` and asks for lessons as
     `{"text": "...", "from": [12, 15]}`.
   - F7 introduces `apply_reflection(world, agent, text)` in `brain/mind.py` (the daily reflection's apply
     step; T06 later extends it with ambitions). `parse_lessons`, or T06's `parse_reflection` once it exists, accepts both plain strings and those
     objects. `Agent.lesson_sources: Dict[str, List[int]]` maps a lesson to the memory ids it cited that
     actually exist.
   - A lesson with no valid citation is still kept, but the Inspector shows it as *unsupported*.

## Done when
`python scripts/plan.py verify F7` passes.
