/** A content pack (docs/modding.md) as the server describes it. */
export type PackInfo = { id: string; name: string; version: string; sha256: string; items: string[]; recipes: string[] };

export const PACK_MAX_BYTES = 64 * 1024;

export type PackRead = { ok: true; pack: Record<string, unknown> } | { ok: false; error: string };

/** A first look at a picked file, before the server checks it properly: small enough, JSON, an object. */
export function readPackText(text: string): PackRead {
  if (new TextEncoder().encode(text).length > PACK_MAX_BYTES) return { ok: false, error: "That file is larger than 64 KB. A content pack is small." };
  let raw: unknown;
  try { raw = JSON.parse(text); } catch { return { ok: false, error: "That file is not JSON." }; }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ok: false, error: "That file is not a content pack." };
  return { ok: true, pack: raw as Record<string, unknown> };
}

export function packLabel(p: PackInfo | null | undefined): string {
  if (!p || !p.name) return "none";
  const n = (xs: string[] | undefined, one: string) => `${xs?.length ?? 0} ${one}${(xs?.length ?? 0) === 1 ? "" : "s"}`;
  return `${p.name} ${p.version} (${n(p.items, "item")}, ${n(p.recipes, "recipe")})`;
}

/** What the New game request carries: undefined keeps the running game's pack, {} plays without one.
 *  An experiment never takes a pack. */
export function packForReset(choice: Record<string, unknown> | "none" | null, strict: boolean): Record<string, unknown> | undefined {
  if (strict || choice === "none") return {};
  return choice ?? undefined;
}
