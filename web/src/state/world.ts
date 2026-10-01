import type { AgentBrief, Clock, Stats, StructureView, WorldEvent, WorldMeta } from "../types";

function b64(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export type AgentState = AgentBrief & {
  px: number; py: number; // previous position
  tx: number; ty: number; // target position
  t0: number; // time target was set
  facing: number;
  born: number;
};

export interface WorldListener {
  reset(w: WorldData): void;
  res(i: number): void;
  structure(s: StructureView, isNew: boolean): void;
  removed(id: string): void;
  paths(i: number, level: number): void;
  events(evs: WorldEvent[]): void;
  agentGone(id: string): void;
}

/** Mutable, non-React world mirror. The renderer listens to fine-grained changes. */
export class WorldData {
  meta!: WorldMeta;
  size = 128;
  tiles = new Uint8Array(0);
  resKind = new Uint8Array(0);
  resAmt = new Uint8Array(0);
  paths = new Uint8Array(0); // 0 none, 1 trail, 2 road
  structures = new Map<string, StructureView>();
  agents = new Map<string, AgentState>();
  tablets: { id: string; x: number; y: number }[] = [];
  signs: { id: string; x: number; y: number; symbol: string; author_name?: string }[] = [];
  ground: { x: number; y: number; items: Record<string, number>; icon: string; name: string }[] = [];
  animals: [string, string, number, number, number][] = []; // id, kind, x, y, tame
  events: WorldEvent[] = [];
  clock: Clock | null = null;
  stats: Stats | null = null;
  history: Stats[] = [];
  ready = false;
  frameInterval = 125;
  private lastFrameAt = 0;
  listeners = new Set<Partial<WorldListener>>();

  constructor(public id: string) {}

  listen(l: Partial<WorldListener>) { this.listeners.add(l); return () => this.listeners.delete(l); }

  snapshot(m: any) {
    this.meta = m.world;
    this.size = m.world.size;
    this.tiles = b64(m.tiles);
    this.resKind = b64(m.res_kind);
    this.resAmt = b64(m.res_amt);
    this.paths = new Uint8Array(this.size * this.size);
    for (const i of m.trails) this.paths[i] = 1;
    for (const i of m.roads) this.paths[i] = 2;
    this.structures = new Map(m.structures.map((s: StructureView) => [s.id, s]));
    const now = performance.now();
    this.agents = new Map(m.agents.map((a: AgentBrief) => [a.id, { ...a, px: a.x, py: a.y, tx: a.x, ty: a.y, t0: now, facing: 1, born: now - 10000 }]));
    this.tablets = m.tablets;
    this.signs = m.signs || [];
    this.ground = m.ground || [];
    this.animals = m.animals || [];
    this.events = m.events;
    this.clock = m.clock;
    this.stats = m.stats;
    this.history = m.history || [];
    this.ready = true;
    for (const l of this.listeners) l.reset?.(this);
  }

  frame(f: any) {
    if (!this.ready) return;
    const now = performance.now();
    if (this.lastFrameAt) this.frameInterval = this.frameInterval * 0.9 + Math.min(400, now - this.lastFrameAt) * 0.1;
    this.lastFrameAt = now;
    this.clock = f.clock;
    if (f.stats) {
      this.stats = f.stats;
      const last = this.history[this.history.length - 1];
      if (!last || last.day !== f.stats.day) { /* daily history arrives via snapshot; keep last live */ }
    }
    for (const [i, k, amt] of f.res as number[][]) {
      this.resKind[i] = k;
      this.resAmt[i] = amt;
      for (const l of this.listeners) l.res?.(i);
    }
    for (const s of f.structures as StructureView[]) {
      const isNew = !this.structures.has(s.id);
      this.structures.set(s.id, s);
      for (const l of this.listeners) l.structure?.(s, isNew);
    }
    for (const id of f.removed as string[]) {
      this.structures.delete(id);
      for (const l of this.listeners) l.removed?.(id);
    }
    for (const [i, lvl] of f.paths as number[][]) {
      this.paths[i] = lvl;
      for (const l of this.listeners) l.paths?.(i, lvl);
    }
    if (f.tablets) this.tablets = f.tablets;
    if (Array.isArray(f.signs)) this.signs = f.signs;
    if (Array.isArray(f.ground)) this.ground = f.ground;
    if (Array.isArray(f.animals)) this.animals = f.animals;
    const seen = new Set<string>();
    for (const a of f.agents as AgentBrief[]) {
      seen.add(a.id);
      const cur = this.agents.get(a.id);
      if (!cur) {
        this.agents.set(a.id, { ...a, px: a.x, py: a.y, tx: a.x, ty: a.y, t0: now, facing: 1, born: now });
        continue;
      }
      // start the next segment from wherever we're currently drawn
      const [cx, cy] = this.agentPos(cur, now);
      if (a.x !== cur.tx || a.y !== cur.ty) {
        if (a.x !== cur.tx) cur.facing = a.x > cur.tx ? 1 : -1;
        cur.px = cx; cur.py = cy; cur.tx = a.x; cur.ty = a.y; cur.t0 = now;
      }
      Object.assign(cur, a, { x: a.x, y: a.y });
    }
    for (const id of [...this.agents.keys()]) {
      if (!seen.has(id)) {
        this.agents.delete(id);
        for (const l of this.listeners) l.agentGone?.(id);
      }
    }
    if (f.events?.length) {
      this.events.push(...f.events);
      if (this.events.length > 400) this.events.splice(0, this.events.length - 400);
      for (const l of this.listeners) l.events?.(f.events);
    }
  }

  agentPos(a: AgentState, now: number): [number, number] {
    const d = Math.max(60, this.frameInterval * 1.05);
    const k = Math.min(1, (now - a.t0) / d);
    const dist = Math.hypot(a.tx - a.px, a.ty - a.py);
    if (dist > 6) return [a.tx, a.ty]; // teleports / big jumps at high speed: snap
    return [a.px + (a.tx - a.px) * k, a.py + (a.ty - a.py) * k];
  }

  tile(x: number, y: number) { return this.tiles[y * this.size + x]; }
}
