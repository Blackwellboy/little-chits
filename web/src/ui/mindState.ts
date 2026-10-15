import type { BrainSummary } from "../types";

/** A world's model that has answered nothing for a day is down (the server's Mind.watch): its chits are on instinct.
 *  Live, World A's model stopped at day 806 and the brain pill still named it, as if it were thinking, for ~1,100
 *  days. Every place that names a world's model names its state too. */
export const NOT_ANSWERING = "not answering — instinct";

export function mindDown(b: BrainSummary | undefined | null): boolean {
  return !!b && b.id !== "instinct" && !!b.down;
}

/** The model's name as the pill and the welcome show it: "env", or "env (not answering — instinct)". */
export function mindLabel(b: BrainSummary | undefined | null, fallback = "…"): string {
  const label = b?.label ?? fallback;
  return mindDown(b) ? `${label} (${NOT_ANSWERING})` : label;
}

/** One line per world whose model is down, for the chip kept up while it is. */
export function mindsDown(brains: Record<string, BrainSummary>, ticksPerDay = 240): string[] {
  return Object.entries(brains)
    .filter(([, b]) => mindDown(b))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([wid, b]) => {
      const since = b.failing_since != null ? ` since day ${Math.floor(b.failing_since / ticksPerDay) + 1}` : "";
      return `World ${wid}'s mind ${b.label} has stopped answering${since}: the chits are running on instinct.`;
    });
}
