# T16 · 🎬 Director camera: auto-cuts to the drama

**Why:** a screen recording is only interesting if the camera is where the action is. The director watches the
event stream and cuts to discoveries, births, storms and builds, and hangs around busy chits in between.

## Build
Create `web/src/render/director.ts`. It must be pure, with no imports from pixi or react:

```ts
export type DirectorEvent = { seq: number; tick: number; kind: string; importance: number;
  x: number | null; y: number | null; text: string; world: string };
export type DirectorAgent = { id: string; x: number; y: number; act: string };
export type Shot = { world: string; x: number; y: number; zoom: number; caption: string; seq: number; until: number };

export function scoreEvent(e: DirectorEvent): number
export class Director {
  constructor(opts?: { minDwellMs?: number; idleMs?: number; maxAgeMs?: number });
  offer(e: DirectorEvent, now: number): void;
  current(now: number, world: string, agents: DirectorAgent[]): Shot | null;
}
```
- **`scoreEvent`**: `importance*10` plus a bonus: discovery/first +20, settlement +15, legacy +15, storm +10,
  built +8, birth +5, death +5, ambition +3, else 0.
- **`offer`** keeps only events with `importance >= 3` and non-null x/y, remembering when each was offered.
  At most 20 are queued; drop the lowest score.
- **`current(now, world, agents)`**:
  1. The active shot and the previous idle target are tracked **per world**. If this world's active shot has `now < until`, return it.
  2. Otherwise take the best-scoring queued event for `world` that was offered ≤ `maxAgeMs` ago (default
     60000). Ties go to the newest.
     - Build a shot: `zoom = importance >= 5 ? 4.2 : 3.5`, `caption` = text cut to 90 characters with "…",
       `until = now + minDwellMs` (default 8000).
     - Remove the event from the queue and return the shot.
  3. Otherwise run an idle cut. Candidates are the agents whose `act` matches
     `/building|crafting|experimenting|teaching|talking|harvesting/`, minus the previous idle target. If that
     is empty, use all agents minus the previous target. If that is still empty, use all agents. Pick the
     candidate with the lowest id (string compare) and return `{x, y, zoom: 3, caption: "", seq: -1,
     until: now + idleMs}` (idleMs defaults to 12000).
  4. If there are no agents, return null.
- **UI:**
  - A "🎬" toggle button in the TopBar, with state `director: boolean` in the store (persisted to
    localStorage).
  - When it's on, each `WorldCanvas` owns a `Director`, feeds it its world's new events (WorldData
    `events` listener), and every frame calls `WorldView.flyTo(shot.x, shot.y, shot.zoom)` whenever the shot
    changes.
  - A caption lower-third (`.caption`) shows the shot caption for its dwell time.
  - Manual drag or click turns the director off.

## Done when
`python scripts/plan.py verify T16` passes (vitest + web build).
