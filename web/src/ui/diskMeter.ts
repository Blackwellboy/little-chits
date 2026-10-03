/** The recorder's disk use, as the server reports it (recorder.py storage_status). */
export type RecorderStorage = {
  bytes: number; run_bytes: number; frames_bytes: number; free_bytes: number; limit_bytes: number; warning: string;
};

const GIB = 1024 ** 3;
export const CAP_MIN_GB = 1;
export const CAP_MAX_GB = 500;

/** "340 MB", "1.2 GB", "28 GB": short enough for one line. */
export function size(bytes: number): string {
  if (!(bytes > 0)) return "0 MB";
  const gb = bytes / GIB;
  if (gb >= 10) return `${Math.round(gb)} GB`;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

/** What the Recordings modal shows: used / cap / free, and how full the bar is. */
export function diskMeter(s: RecorderStorage) {
  const cap = Math.max(0, s.limit_bytes);
  const percent = cap > 0 ? Math.min(100, Math.round((s.bytes / cap) * 100)) : 0;
  return {
    used: size(s.bytes), cap: size(cap), free: s.free_bytes >= 0 ? size(s.free_bytes) : "unknown",
    percent, over: cap > 0 && s.bytes > cap, capGb: Math.round((cap / GIB) * 10) / 10,
  };
}

/** The cap the user typed, in GB, or null when it isn't a number the server accepts (1 to 500). */
export function parseCapGb(text: string): number | null {
  if (!/^\s*\d+(\.\d+)?\s*$/.test(text)) return null;
  const v = Number(text);
  return v >= CAP_MIN_GB && v <= CAP_MAX_GB ? Math.round(v * 10) / 10 : null;
}
