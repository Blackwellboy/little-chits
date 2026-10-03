/** ⏩ Skip ahead: the choices, what the top bar says while skipping, and how a skip ended. */

export type SkipState = { until: "discovery" | "moment" | "days"; days: number; from_day: number; day: number; seconds: number };
export type SkipResult = {
  until: string; reason: "found" | "days" | "limit" | "stopped" | "storage"; text: string; ended: number;
  from_day: number; day: number; ticks: number; seconds: number;
};

export const SKIP_NOTE = "Skipped time is mostly instinct-driven: the models can't answer this fast, so instinct fills in for them.";

export const SKIP_CHOICES: { label: string; until: SkipState["until"]; days?: number }[] = [
  { label: "To the next discovery", until: "discovery" },
  { label: "To the next big moment", until: "moment" },
  { label: "1 day", until: "days", days: 1 },
  { label: "7 days", until: "days", days: 7 },
];

/** "Skipping: day 3112, 14 s" */
export function skipProgress(s: SkipState): string {
  return `Skipping: day ${s.day}, ${s.seconds} s`;
}

/** One plain sentence for how the last skip ended ("" when there was none). */
export function skipResult(r: SkipResult | null | undefined): string {
  if (!r) return "";
  const n = Math.round(r.ticks / 240);
  const days = `${n} day${n === 1 ? "" : "s"}`;
  switch (r.reason) {
    case "found": return `Stopped on day ${r.day}: ${r.text}`;
    case "days": return `Skipped ${days}. It is day ${r.day}.`;
    case "limit": return `Nothing new in ${days}. Stopped on day ${r.day}.`;
    case "storage": return `The skip stopped on day ${r.day}: the game could not be saved.`;
    default: return `The skip stopped on day ${r.day}.`;
  }
}
