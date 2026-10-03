/** 💾 Saves in the main UI: what a row says, what the confirm says, and the save file's trip to and from the server. */
import { accessToken, ApiError } from "../net/socket";

export type SaveRow = {
  id: number; name: string; created: number; tick: number;
  day?: number; population?: number; era?: string; imported?: boolean;
  worlds?: Record<string, { name: string; day: number; population: number; era: string }>;
};

export const SAVE_FILE_MAX = 64 * 1024 * 1024; // the server's limit for an uploaded save file

/** "just now", "5 min ago", "3 h ago", "2 days ago": how long ago a save was made (both in seconds). */
export function savedAgo(created: number, now: number): string {
  const s = Math.max(0, now - created);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

/** One line under a save's name: its day, how many chits, the era, and when it was made. */
export function saveLine(s: SaveRow, now: number): string {
  const day = s.day ?? Math.floor(s.tick / 240) + 1;
  const parts = [`Day ${day}`];
  if (s.population !== undefined) parts.push(`${s.population} chit${s.population === 1 ? "" : "s"}`);
  if (s.era) parts.push(s.era);
  parts.push(`saved ${savedAgo(s.created, now)}`);
  if (s.imported) parts.push("imported");
  return parts.join(" · ");
}

/** What Load asks before it rewinds: it starts a new timeline, and the game is marked as modified. */
export function loadConfirm(s: SaveRow): string {
  const day = s.day ?? Math.floor(s.tick / 240) + 1;
  return `Load “${s.name}”? Every world goes back to day ${day} and a new timeline starts from there. `
    + "What happened after this save stays in the old timeline. The game is marked as modified.";
}

/** A file name for an exported save that is safe everywhere. */
export function saveFileName(name: string): string {
  const slug = name.replace(/[^A-Za-z0-9]/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "save";
  return `little-chits-${slug}.lcsave`;
}

/** Why a picked file can't be a save, or "" when it may be sent to the server (which checks it properly). */
export function saveFileProblem(f: { name: string; size: number }): string {
  if (f.size === 0) return "This file is empty.";
  if (f.size > SAVE_FILE_MAX) return `This file is too big (the limit is ${SAVE_FILE_MAX / 1024 / 1024} MB).`;
  return "";
}

function auth(): Record<string, string> {
  const t = accessToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let r: Response;
  try {
    r = await fetch(path, init);
  } catch (e) {
    throw new ApiError(`Can't reach the game server (${(e as Error)?.message ?? e})`);
  }
  if (!r.ok) throw new ApiError(`${r.status} ${await r.text()}`);
  return r;
}

/** The save as one file (the token goes in a header, not in the address). */
export async function fetchSaveFile(id: number): Promise<Blob> {
  return (await send(`/api/saves/${id}/export`, { headers: auth() })).blob();
}

/** Send a save file; the server checks it and keeps it as a new save. */
export async function importSaveFile(file: Blob): Promise<SaveRow> {
  const r = await send("/api/saves/import", {
    method: "POST", headers: { ...auth(), "Content-Type": "application/octet-stream" }, body: file,
  });
  return r.json();
}
