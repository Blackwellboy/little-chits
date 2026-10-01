// The director: watches the event stream and decides where the camera should be. Pure logic, no pixi/react.

export type DirectorEvent = {
  seq: number; tick: number; kind: string; importance: number;
  x: number | null; y: number | null; text: string; world: string;
};
export type DirectorAgent = { id: string; x: number; y: number; act: string };
export type Shot = { world: string; x: number; y: number; zoom: number; caption: string; seq: number; until: number };

const BONUS: Record<string, number> = {
  discovery: 20, first: 20, settlement: 15, legacy: 15, storm: 10, built: 8, birth: 5, death: 5, ambition: 3,
};
const BUSY = /building|crafting|experimenting|teaching|talking|harvesting/;
const QUEUE_MAX = 20;
const CAPTION_MAX = 90;

export function scoreEvent(e: DirectorEvent): number {
  return e.importance * 10 + (BONUS[e.kind] ?? 0);
}

function cut(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…";
}

type Queued = { e: DirectorEvent; at: number; score: number };

export class Director {
  private minDwellMs: number;
  private idleMs: number;
  private maxAgeMs: number;
  private queue: Queued[] = [];
  private active = new Map<string, Shot>();
  private idleTarget = new Map<string, string>();

  constructor(opts: { minDwellMs?: number; idleMs?: number; maxAgeMs?: number } = {}) {
    this.minDwellMs = opts.minDwellMs ?? 8000;
    this.idleMs = opts.idleMs ?? 12000;
    this.maxAgeMs = opts.maxAgeMs ?? 60000;
  }

  offer(e: DirectorEvent, now: number): void {
    if (e.importance < 3 || e.x == null || e.y == null) return;
    this.queue.push({ e, at: now, score: scoreEvent(e) });
    if (this.queue.length > QUEUE_MAX) {
      let lo = 0;
      for (let i = 1; i < this.queue.length; i++) {
        const q = this.queue[i], l = this.queue[lo];
        if (q.score < l.score || (q.score === l.score && q.e.seq < l.e.seq)) lo = i;
      }
      this.queue.splice(lo, 1);
    }
  }

  current(now: number, world: string, agents: DirectorAgent[]): Shot | null {
    const act = this.active.get(world);
    if (act && now < act.until) return act;
    let best = -1;
    for (let i = 0; i < this.queue.length; i++) {
      const q = this.queue[i];
      if (q.e.world !== world || now - q.at > this.maxAgeMs) continue;
      const b = best >= 0 ? this.queue[best] : null;
      if (!b || q.score > b.score || (q.score === b.score && q.e.seq > b.e.seq)) best = i;
    }
    if (best >= 0) {
      const { e } = this.queue.splice(best, 1)[0];
      const shot: Shot = {
        world, x: e.x as number, y: e.y as number, zoom: e.importance >= 5 ? 4.2 : 3.5,
        caption: cut(e.text, CAPTION_MAX), seq: e.seq, until: now + this.minDwellMs,
      };
      this.active.set(world, shot);
      return shot;
    }
    if (!agents.length) return null;
    const prev = this.idleTarget.get(world);
    let cands = agents.filter((a) => BUSY.test(a.act) && a.id !== prev);
    if (!cands.length) cands = agents.filter((a) => a.id !== prev);
    if (!cands.length) cands = agents;
    const pick = cands.reduce((m, a) => (a.id < m.id ? a : m));
    this.idleTarget.set(world, pick.id);
    const shot: Shot = { world, x: pick.x, y: pick.y, zoom: 3, caption: "", seq: -1, until: now + this.idleMs };
    this.active.set(world, shot);
    return shot;
  }
}
