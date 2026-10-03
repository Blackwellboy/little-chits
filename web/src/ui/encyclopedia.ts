/** The Knowledge tab's encyclopedia: what a discovered thing is for (GET /api/worlds/{id}/encyclopedia/{key}).
 *  Pure, for testing: the entry the server sent, as labelled lines. Nothing is added that the server didn't send. */
type Named = { key: string; name: string; icon?: string; n?: number };
export type Entry = {
  key: string; kind: "recipe" | "design"; name: string; world: string; icon: string; local_name?: string | null;
  first_by: string | null; first_day: number | null; undiscovered_uses: number;
  // an item
  props?: string[]; made_from?: { inputs: Named[]; station: string | null; makes: number }; effects?: string[];
  used_in_recipes?: Named[]; used_in_buildings?: Named[];
  invention?: { purpose: string; purpose_text: string; by: string; day: number } | null;
  // a building
  blurb?: string; materials?: Named[]; size?: number[]; work?: number; station?: string | null; min_pop?: number;
  made_here?: Named[];
};

export type EntryLine = { label: string; text: string };

const count = (x: Named) => (x.n && x.n > 1 ? `${x.n} ${x.name}` : x.name);
const list = (xs: Named[]) => xs.map((x) => x.name).join(", ");

export function entryLines(e: Entry): EntryLine[] {
  const out: EntryLine[] = [];
  const add = (label: string, text: string | undefined | null) => { if (text) out.push({ label, text }); };
  if (e.kind === "design") {
    add("What it does", e.blurb ? e.blurb.charAt(0).toUpperCase() + e.blurb.slice(1) + "." : "");
    add("Materials", (e.materials ?? []).map(count).join(", "));
    add("Size", e.size ? `${e.size[0]} by ${e.size[1]} tiles` : "");
    add("Needs", e.min_pop ? `a village of ${e.min_pop} or more` : "");
    add("Made here", list(e.made_here ?? []));
  } else {
    if (e.invention) add("Invention", `${e.invention.by} invented it on day ${e.invention.day}, for ${e.invention.purpose}.`);
    add("Properties", (e.props ?? []).join(", "));
    const m = e.made_from;
    if (m) add("Made from", m.inputs.map(count).join(" + ") + (m.station ? `, at a ${m.station}` : "") + (m.makes > 1 ? ` (makes ${m.makes})` : ""));
    for (const fx of e.effects ?? []) add("Effect", fx);
    add("Used to make", list(e.used_in_recipes ?? []));
    add("Used to build", (e.used_in_buildings ?? []).map((x) => `${x.name} (takes ${x.n})`).join(", "));
  }
  if (e.undiscovered_uses > 0) add("Still unknown", `${e.undiscovered_uses} more use${e.undiscovered_uses === 1 ? "" : "s"} this world has not found yet.`);  return out;
}
