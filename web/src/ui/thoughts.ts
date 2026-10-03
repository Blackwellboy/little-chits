// One line of the Brains dialog's "Recent thoughts".
//
// A cascade brain that picks "my own idea" logs the choice first (what it chose, how sure it was, that it went on to
// write a plan) and the plan as a second entry. The first has no steps. Rendering it as a plan threw, and with no
// error boundary the whole page went blank whenever such an entry was among the last ones shown (issue #74, found
// and diagnosed by kagankongar).

export function stepText(s: any): string {
  const what = s?.what ? ` ${Array.isArray(s.what) ? s.what.join("+") : s.what}`
    : Array.isArray(s?.with) ? ` ${s.with.join("+")}` : "";
  return `${s?.do ?? "?"}${what}`;
}

export type ThoughtLine = { quote: string; goal: string; rest: string };

export function thoughtLine(l: any): ThoughtLine {
  const quote = typeof l?.thought === "string" ? l.thought : "";
  const goal = typeof l?.goal === "string" ? l.goal : "";
  if (Array.isArray(l?.steps)) return { quote, goal, rest: l.steps.map(stepText).join(" → ") };
  const sure = typeof l?.confidence === "number" ? ` (${Math.round(l.confidence * 100)}% sure)` : "";
  const picked = l?.chose ? `picked option ${l.chose}${sure}` : "made a choice";
  return { quote, goal, rest: picked + (l?.escalated ? ", then wrote its own plan" : "") };
}
