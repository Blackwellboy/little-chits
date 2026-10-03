import { describe, expect, it } from "vitest";
import { addToasts, milestoneOf, nextStep, stepLabel, TOAST_MAX, TOAST_MS, type Checklist, type Toast } from "../../web/src/state/milestones";
import type { WorldEvent } from "../../web/src/types";

const ev = (seq: number, kind: string, importance = 5, data: Record<string, any> = {}): WorldEvent =>
  ({ seq, tick: 240, kind, text: kind, importance, actor: null, x: null, y: null, data });

describe("milestoneOf", () => {
  it("knows the milestones the simulator already tells", () => {
    expect(milestoneOf(ev(1, "era", 5, { era: "Copper Age" }))).toMatchObject({ kind: "age", banner: true, label: "a new age" });
    expect(milestoneOf(ev(2, "town_rank", 5, { rank: "town" }))).toMatchObject({ kind: "rank", banner: true, label: "now a town" });
    expect(milestoneOf(ev(3, "town_rank", 5, { rank: "city" }))).toMatchObject({ banner: true, label: "now a city", icon: "🏙" });
    expect(milestoneOf(ev(4, "project_done"))).toMatchObject({ kind: "project", banner: false, label: "village project done" });
    expect(milestoneOf(ev(5, "discovery", 5, { knowledge: "recipe:cord" }))).toMatchObject({ kind: "discovery", banner: false });
    expect(milestoneOf(ev(6, "invention"))).toMatchObject({ kind: "discovery", label: "a new invention" });
  });

  it("leaves everything else alone", () => {
    for (const k of ["learned", "death", "birth", "built", "storyteller", "village_growth", "error"]) expect(milestoneOf(ev(1, k))).toBeNull();
    expect(milestoneOf(ev(1, "town_rank", 5, { rank: "village" }))!.banner).toBe(false);
  });
});

describe("addToasts", () => {
  it("gives big moments and milestones a toast, and nothing else", () => {
    const t = addToasts([], [ev(1, "speech", 1), ev(2, "death", 4), ev(3, "project_done", 5)], "A", 1000);
    expect(t.map((x) => x.key)).toEqual(["A-2", "A-3"]);
    const same: Toast[] = [];
    expect(addToasts(same, [ev(4, "speech", 2)], "A", 1000)).toBe(same);
  });

  it("keeps a milestone when a busy day would push it out", () => {
    let t = addToasts([], [ev(1, "era")], "B", 0);
    t = addToasts(t, [ev(2, "death", 4), ev(3, "birth", 4), ev(4, "death", 4), ev(5, "built", 4), ev(6, "death", 4)], "B", 100);
    expect(t).toHaveLength(TOAST_MAX);
    expect(t[0].key).toBe("B-1");
    expect(t.slice(1).map((x) => x.seq)).toEqual([4, 5, 6]);
  });

  it("lets old toasts go", () => {
    const t = addToasts([], [ev(1, "era")], "A", 0);
    expect(addToasts(t, [ev(2, "death", 4)], "A", TOAST_MS + 1).map((x) => x.seq)).toEqual([2]);
  });
});

describe("the road checklist", () => {
  const c: Checklist = { age: "Copper Age", done: 2, total: 5, steps: [
    { action: "discover", key: "recipe:charcoal", name: "charcoal", done: true, detail: "" },
    { action: "discover", key: "recipe:brick", name: "brick", done: true, detail: "" },
    { action: "make", key: "recipe:brick", name: "brick", done: false, detail: "2 of 6 for the furnace" },
    { action: "build", key: "design:furnace", name: "furnace", done: false, detail: "" },
    { action: "discover", key: "recipe:copper", name: "copper", done: false, detail: "" },
  ] };

  it("says each step as discover, make or build", () => {
    expect(c.steps.map(stepLabel)).toEqual(["Discover charcoal", "Discover brick", "Make brick (2 of 6 for the furnace)", "Build furnace", "Discover copper"]);
  });

  it("marks the first step still to do", () => {
    expect(nextStep(c)).toBe(2);
    expect(nextStep({ ...c, steps: c.steps.map((s) => ({ ...s, done: true })) })).toBe(-1);
  });
});
