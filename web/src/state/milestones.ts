/**
 * Milestones: the few events an observer should not miss, and the road to the next age as a checklist.
 * Pure (no store, no DOM), so it can be tested without a browser. Everything here reads events the simulator
 * already emits; nothing is sent back.
 */
import type { WorldEvent } from "../types";

export type Milestone = {
  kind: "age" | "rank" | "project" | "discovery";
  label: string; // a few words for the toast or banner heading
  icon: string;
  banner: boolean; // fills the screen for a few seconds, like a new age
};

/** Is this event a milestone? A new age, a village becoming a town or city, a village project done, or a thing
 *  nobody in that world had found or invented before. */
export function milestoneOf(e: Pick<WorldEvent, "kind" | "data">): Milestone | null {
  const d = e.data || {};
  switch (e.kind) {
    case "era":
      return { kind: "age", label: "a new age", icon: "🏛", banner: true };
    case "town_rank": {
      const rank = String(d.rank || "town");
      return { kind: "rank", label: `now a ${rank}`, icon: rank === "city" ? "🏙" : "🏘", banner: rank === "town" || rank === "city" };
    }
    case "project_done":
      return { kind: "project", label: "village project done", icon: "🏆", banner: false };
    case "discovery": // (the simulator says "discovery" only for a first in that world; later learners are "learned")
    case "first":
      return { kind: "discovery", label: "first in this world", icon: "✦", banner: false };
    case "invention":
      return { kind: "discovery", label: "a new invention", icon: "💡", banner: false };
    default:
      return null;
  }
}

/** A village and its project, as the Progress panel lists them (a hamlet too small for a project of its own says
 *  whose it works on in `with`). */
export type VillageRow<P> = { id: string; name: string; x: number | null; y: number | null; population: number; with: string; active: P | null };

/** The villages in the order the panel shows them: the one in view first (the village nearest where the camera was
 *  last sent), then the rest as the game lists them (the chief's village first). With no place in view, the game's
 *  order stands. */
export function villageOrder<P>(rows: VillageRow<P>[], at: { x: number; y: number } | null): VillageRow<P>[] {
  if (!at || rows.length < 2) return rows;
  const far = (r: VillageRow<P>) => (r.x == null || r.y == null ? Infinity : Math.max(Math.abs(r.x - at.x), Math.abs(r.y - at.y)));
  const near = rows.reduce((best, r) => (far(r) < far(best) ? r : best), rows[0]);
  return [near, ...rows.filter((r) => r !== near)];
}

export type Toast = WorldEvent & { world: string; key: string; _t?: number };

export const TOAST_MAX = 4;
export const TOAST_MS = 9000;

/** The toasts after a frame's events: big moments (importance 4 and up) and every milestone get one. Old ones expire,
 *  and when there are too many the oldest ordinary toast goes first, so a milestone is not pushed out by a busy day. */
export function addToasts(old: Toast[], events: WorldEvent[], world: string, now: number): Toast[] {
  const fresh = events.filter((e) => e.importance >= 4 || milestoneOf(e))
    .map((e) => ({ ...e, world, key: `${world}-${e.seq}`, _t: now }));
  if (!fresh.length) return old;
  const all = [...old, ...fresh].filter((t) => (t._t ??= now) > now - TOAST_MS);
  while (all.length > TOAST_MAX) {
    const i = all.findIndex((t) => !milestoneOf(t));
    all.splice(i >= 0 ? i : 0, 1);
  }
  return all;
}

export type CheckStep = { action: "discover" | "make" | "build"; key: string; name: string; done: boolean; detail: string };
export type Checklist = { age: string; steps: CheckStep[]; done: number; total: number };

const VERB: Record<CheckStep["action"], string> = { discover: "Discover", make: "Make", build: "Build" };

/** One line of the checklist: "Discover steel", "Make brick (4 of 10 for the forge)", "Build forge". */
export function stepLabel(s: CheckStep): string {
  return `${VERB[s.action] ?? "Reach"} ${s.name}${s.detail ? ` (${s.detail})` : ""}`;
}

/** The first step still to do: where the village stands on the list. -1 once every step is done. */
export function nextStep(c: Checklist): number {
  return c.steps.findIndex((s) => !s.done);
}
