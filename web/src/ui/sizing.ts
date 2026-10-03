/** Size the world to the model: what the server's advice (server/chits/sizing.py) means for the New game dialog. */

export type Capacity = { chits: number | null; latency_ms: number; slots: number; source: "live" | "probe" | null; text: string; error?: string };
export type Advice = { chits: number | null; unmeasured: string[]; limited_by: string | null; text: string };

export const MIN_CHITS = 2;
export const MAX_CHITS = 60;

export function clampChits(n: number): number {
  return Math.max(MIN_CHITS, Math.min(MAX_CHITS, Math.round(n) || MIN_CHITS));
}

/** The line under "Chits per world": the advice, how the chosen number compares, and the number to offer (if any). */
export function adviceLine(advice: Advice | null, chits: number): { text: string; level: "good" | "warn" | "muted"; use: number | null; measure: boolean } {
  if (!advice) return { text: "", level: "muted", use: null, measure: false };
  if (advice.chits == null) return { text: advice.text, level: "muted", use: null, measure: advice.unmeasured.length > 0 };
  if (chits > advice.chits) {
    return { text: `${advice.text} With ${chits} chits most moves will be instinct.`, level: "warn", use: advice.chits, measure: false };
  }
  return { text: advice.text, level: "good", use: chits < advice.chits ? advice.chits : null, measure: false };
}

/** New advice arrived (another model was picked, or one was measured). A number the user typed stays; a number
 *  taken from the advice follows it. */
export function followAdvice(chits: number, following: boolean, advice: Advice | null): number {
  return following && advice?.chits != null ? clampChits(advice.chits) : chits;
}
