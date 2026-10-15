/** Watching aids for the observer: who is thinking for a world, how long its next age has stalled, the scholars'
 *  insight counter, the Chronicle's repeated ideas and a People list that holds still. Pure, for testing. */

/** Who drove a world's last finished steps (server views.thinking, from the diagnostics' provenance categories). */
export type Thinking = {
  brain: string; steps: number; model_pct: number | null; body_pct: number | null; routine_pct: number | null;
  instinct_pct: number | null; fallback_pct: number | null; on_instinct: boolean; why: "" | "no_model" | "model_down";
};

/** The "running on instinct" chip by the world's name: a world with no model, or one whose model has decided none
 *  of its recent steps while instinct stood in. Nothing while a model is thinking. */
export function instinctChip(t: Thinking | null | undefined, brainId?: string): { text: string; title: string } | null {
  const why = t?.on_instinct ? t.why : !t && brainId === "instinct" ? "no_model" : "";
  if (why === "no_model") return { text: "⚙ running on instinct", title: "No model is set for this world: every chit acts on its built-in instinct." };
  if (why === "model_down") {
    return { text: "⚙ running on instinct", title: `The model decided none of the last ${t!.steps} steps: instinct is standing in for it.` };
  }
  return null;
}

/** The Progress panel's "who's thinking" line: shares of the last finished steps, the biggest first. */
export function thinkingLine(t: Thinking | null | undefined): string {
  if (!t || !t.steps) return "No steps finished yet.";
  const parts = ([["model", t.model_pct], ["instinct", t.instinct_pct], ["body reflexes", t.body_pct], ["upkeep", t.routine_pct]] as const)
    .filter(([, v]) => v != null && v > 0)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .map(([k, v]) => `${k} ${Math.round(v as number)}%`);
  const head = t.brain === "instinct" ? "No model: " : t.why === "model_down" ? "Model not deciding: " : "";
  return `${head}${parts.join(" · ")} of the last ${t.steps} steps`;
}

/** "X came up with the idea of a forge" from every chit that gets there after the first: once per idea per world.
 *  A first discovery of the same thing counts as its first telling. Order is kept. */
export function dropRepeatedIdeas<E extends { kind: string; data?: Record<string, any> | null }>(events: E[]): E[] {
  const seen = new Set<string>();
  return events.filter((e) => {
    const k = e.data?.knowledge;
    if (!k) return true;
    const idea = e.kind === "learned" && e.data?.how === "insight";
    if (idea && seen.has(k)) return false;
    if (idea || e.kind === "discovery") seen.add(k);
    return true;
  });
}

/** A list's order while the pointer is over it: the order it had when the pointer arrived, the departed dropped and
 *  newcomers at the end, so a click lands on the row that was under it. `held` null: the fresh order. */
export function holdOrder(held: string[] | null, ids: string[]): string[] {
  if (!held) return ids;
  const now = new Set(ids);
  const kept = held.filter((id) => now.has(id));
  const had = new Set(kept);
  return [...kept, ...ids.filter((id) => !had.has(id))];
}

/** Does Escape close the Inspector? Not while a dialog is open or a god-mode tool is armed (those take Escape
 *  first), and not while typing. */
export function escapeClosesInspector(s: { selected: boolean; dialogOpen: boolean; godTool: boolean; typing: boolean }): boolean {
  return s.selected && !s.dialogOpen && !s.godTool && !s.typing;
}
