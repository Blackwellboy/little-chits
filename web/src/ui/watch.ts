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
