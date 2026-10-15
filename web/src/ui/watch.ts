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
