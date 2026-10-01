// Record mode (?record=1): clean frames for 16:9, 9:16 and 1:1 clips. Pure helpers.

export type Aspect = "16:9" | "9:16" | "1:1";
export type RecordParams = {
  record: boolean; aspect: Aspect; world: "A" | "B" | "split"; director: boolean; captions: boolean; speed: number | null;
};

const ASPECTS: Record<Aspect, number> = { "16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1 };
const SPEEDS = [1, 2, 5, 10, 25, 100];

export function parseRecordParams(search: string): RecordParams {
  const q = new URLSearchParams(search);
  const on = (v: string | null) => v === "1" || v === "true";
  const record = on(q.get("record"));
  const a = q.get("aspect") as Aspect;
  const w = q.get("world");
  const flag = (k: string) => (q.has(k) ? q.get(k) !== "0" && q.get(k) !== "false" : record);
  const sp = Number(q.get("speed"));
  return {
    record,
    aspect: a in ASPECTS ? a : "16:9",
    world: w === "A" || w === "B" || w === "split" ? w : "A",
    director: flag("director"),
    captions: flag("captions"),
    speed: q.has("speed") && SPEEDS.includes(sp) ? sp : null,
  };
}

/** A moment close-up (?record=1&world=A&focus=x,y&zoom=3.5&caption=...): the auto-recorder films a big event
 * where it happened, at live speed, with the event as the caption. Null when there is no valid focus. */
export type MomentParams = { x: number; y: number; zoom: number; caption: string; label: string };

export function parseMomentParams(search: string): MomentParams | null {
  const q = new URLSearchParams(search);
  const m = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/.exec(q.get("focus") ?? "");
  if (!m) return null;
  const z = Number(q.get("zoom"));
  return {
    x: Number(m[1]), y: Number(m[2]),
    zoom: Number.isFinite(z) && z > 0 ? Math.min(7, Math.max(1, z)) : 3.5,
    caption: (q.get("caption") ?? "").slice(0, 200),
    label: (q.get("label") ?? "").slice(0, 80),
  };
}

export function stageSize(aspect: Aspect, vw: number, vh: number) {
  const r = ASPECTS[aspect];
  let width = vw, height = vw / r;
  if (height > vh) { height = vh; width = vh * r; }
  width = Math.floor(width); height = Math.floor(height);
  return { width, height, left: Math.floor((vw - width) / 2), top: Math.floor((vh - height) / 2) };
}
