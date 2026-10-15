/** Watching aids for the observer: who is thinking for a world, how long its next age has stalled, the scholars'
 *  insight counter, the Chronicle's repeated ideas and a People list that holds still. Pure, for testing. */

/** Who drove a world's last finished steps (server views.thinking, from the diagnostics' provenance categories). */
export type Thinking = {
  brain: string; steps: number; model_pct: number | null; body_pct: number | null; routine_pct: number | null;
  instinct_pct: number | null; fallback_pct: number | null; waiting_pct?: number | null; on_instinct: boolean;
  why: "" | "no_model" | "model_down" | "busy";
};

/** The "running on instinct" chip by the world's name: a world with no model, or one whose model is not answering.
 *  Nothing while a model is thinking, and nothing for a model that is only slow (busy): that one is still there.
 *  Where nothing stands in for a down model (model-led, model-only, an experiment: `chitsWait`) its chits wait. */
export function instinctChip(t: Thinking | null | undefined, brainId?: string, chitsWait = false): { text: string; title: string } | null {
  const why = t?.on_instinct ? t.why : !t && brainId === "instinct" ? "no_model" : "";
  if (why === "no_model") {
    const brought = t?.model_pct ? Math.round(t.model_pct) : 0;  // (a voyager keeps the model it sailed with)
    return { text: "⚙ running on instinct", title: brought
      ? `No model is set for this world: its chits act on instinct, apart from a few who brought a model with them (${brought}% of recent steps).`
      : "No model is set for this world: every chit acts on its built-in instinct." };
  }
  if (why === "model_down") return chitsWait
    ? { text: "⏳ waiting for the model", title: "The model is not answering: nothing stands in for it in this run, so its chits wait until it does." }
    : { text: "⚙ running on instinct", title: "The model is not answering: instinct is standing in for it until it does." };
  return null;
}

/** The top bar's chips, one per world shown: none for a world whose model the watchdog says is down, since the 🧠
 *  chip (Overlays.MindDown) already tells that outage, with the day it began. Two chips for one outage was noise. */
export function topBarChips(ids: string[], thinking: Record<string, Thinking | undefined>,
  brains: Record<string, { id: string; down?: boolean; chits_wait?: boolean } | undefined>): { id: string; text: string; title: string }[] {
  return ids.flatMap((id) => {
    const b = brains[id];
    if (b && b.id !== "instinct" && b.down) return [];
    const c = instinctChip(thinking[id], b?.id, !!b?.chits_wait);
    return c ? [{ id, ...c }] : [];
  });
}

/** The Progress panel's "who's thinking" line: shares of the last finished steps, the biggest first. */
export function thinkingLine(t: Thinking | null | undefined): string {
  if (!t || !t.steps) return "No steps finished yet.";
  const parts = ([["model", t.model_pct], ["instinct", t.instinct_pct], ["body reflexes", t.body_pct], ["upkeep", t.routine_pct]] as const)
    .filter(([, v]) => v != null && v > 0)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .map(([k, v]) => `${k} ${Math.round(v as number)}%`);
  const waited = t.waiting_pct ? `, chits waited ${Math.round(t.waiting_pct)}% of the time` : "";
  const head = t.brain === "instinct" ? "No model: " : t.why === "model_down" ? "Model not answering: "
    : t.why === "busy" ? `The model is busy (${Math.round(t.fallback_pct ?? 0)}% of steps fell back to instinct${waited}): ` : "";
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

/** One moment of a chit's life (server views.life): its own, or one it was part of (`role`). */
export type LifeEvent = { seq: number; day: number; kind: string; role: "self" | "child" | "helped" | "fight"; text: string; importance: number;
  what?: string };  // (what a "learned" moment learned)

const LIFE_ICON: Record<string, string> = {
  birth: "🍼", death: "🕯", discovery: "✦", first: "★", invention: "💡", learned: "📘", built: "🏠", job: "🧰",
  election: "🗳", elder: "👑", belief: "🕯", convert: "🙏", fight: "💢", theft: "🫳", caught: "🛡", voyage: "⛵",
  arrival: "🏝", wish: "🌟", project_done: "🏆", tablet: "📜", legacy: "📜", last_keeper: "⏳",
};

const LIFE_SHOW_NAMES = 5;
// within a day its own birth comes first and its death last (a newborn learns from its parents before the birth is told)
const lifeRank = (e: LifeEvent) => (e.role === "self" && e.kind === "birth" ? 0 : e.role === "self" && e.kind === "death" ? 2 : 1);

/** The Life tab's lines, oldest first, an icon for each moment (a child's birth is "👶", whoever's event it is). A
 *  day's learning is one line ("Learned 12 things: cord, clay pot, …"): a newborn learns dozens at once. */
export function lifeLines(events: LifeEvent[]): (LifeEvent & { icon: string })[] {
  const sorted = events.slice().sort((a, b) => a.day - b.day || lifeRank(a) - lifeRank(b) || a.seq - b.seq);
  const out: (LifeEvent & { icon: string; _what?: string[] })[] = [];
  for (const e of sorted) {
    const last = out[out.length - 1];
    if (e.kind === "learned" && e.what && last?.kind === "learned" && last._what && last.day === e.day) {
      last._what.push(e.what);
      last.importance = Math.max(last.importance, e.importance);
      continue;
    }
    out.push({ ...e, icon: e.role === "child" ? "👶" : LIFE_ICON[e.kind] ?? "·", ...(e.kind === "learned" && e.what ? { _what: [e.what] } : {}) });
  }
  return out.map(({ _what, ...l }) => {
    if (!_what || _what.length < 2) return l;
    const more = _what.length - LIFE_SHOW_NAMES;
    return { ...l, text: `Learned ${_what.length} things: ${_what.slice(0, LIFE_SHOW_NAMES).join(", ")}${more > 0 ? ` and ${more} more` : ""}` };
  });
}

/** The scholars' insight towards their next idea. Insight keeps piling up while the village already has as many open
 *  ideas as it can hold (or none is left to give): the panel said "1094.8/24". Over the mark it says why it waits. */
export function insightLabel(insight: number, next: number): { text: string; title: string } {
  if (!next) return { text: `${Math.floor(insight)} insight`, title: "Insight the scholars have gathered" };
  if (insight < next) return { text: `${Math.floor(insight)}/${Math.round(next)} insight to the next`, title: `${Math.floor(insight)} of ${Math.round(next)} insight` };
  return { text: "next idea ready: waits for an open one to come true",
    title: `The scholars have ${Math.round(insight)} insight, more than the ${Math.round(next)} a new idea takes. One comes once an open idea comes true (or once there is something left to hint at).` };
}

export const STALL_DAYS = 10;

/** When the next age hasn't come for a long while: how long, the step the village is on, and the biggest reason the
 *  "Why slow?" panel gives for this world. Null while things move (under STALL_DAYS since the current age began). */
export function stallLine(day: number, ladder: { reached: boolean; day: number | null }[], nextStepLabel: string | null,
  reasons: { kind: string; text: string }[] | null | undefined, minDays = STALL_DAYS): string | null {
  const since = Math.max(1, ...ladder.filter((r) => r.reached && r.day != null).map((r) => r.day as number));
  const stalled = day - since;
  if (stalled < minDays) return null;
  const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
  const parts = [`No new age for ${stalled} days.`];
  if (nextStepLabel) parts.push(`They are on: ${lower(nextStepLabel)}.`);
  const top = (reasons ?? []).find((r) => !["paused", "pacing", "save", "invalid"].includes(r.kind));
  if (top) parts.push(`Biggest holdup: ${lower(top.text)}`);
  return parts.join(" ");
}
