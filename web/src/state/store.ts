import { create } from "zustand";
import type { BrainSummary, Control, WorldEvent, WorldMeta } from "../types";
import { Socket, socketUrl, type ConnStatus } from "../net/socket";
import { WorldData } from "./world";
import { pickTheme, setTheme, type ThemeId } from "../theme";
import { addToasts, type Toast } from "./milestones";

export type Tab = "progress" | "why" | "chronicle" | "people" | "knowledge" | "stats" | null;

type UI = {
  conn: ConnStatus;
  worlds: WorldMeta[];
  control: Control | null;
  brains: Record<string, BrainSummary>;
  view: "A" | "B" | "split";
  selected: { world: string; id: string } | null;
  follow: boolean;
  tab: Tab;
  brainsOpen: boolean;
  newWorldOpen: boolean;
  nightMode: "normal" | "soft" | "off";
  tick: number; // bumps ~8/s to refresh clock-driven UI
  toasts: Toast[];
  focus: { world: string; x: number; y: number; t: number } | null;
  director: boolean; // 🎬 the camera cuts to the drama by itself
  godOpen: boolean;
  recordingsOpen: boolean;
  recording: boolean; // 🎞 auto-record is filming
  godTool: { action: string; item?: string; label: string } | null; // armed: the next map click applies it
  theme: ThemeId;
  set: (p: Partial<UI>) => void;
};

const firstTheme = pickTheme(null, window.location.search);
setTheme(firstTheme);

export const useUI = create<UI>((set) => ({
  conn: "connecting",
  worlds: [],
  control: null,
  brains: {},
  view: (localStorageGet("view") as any) || "A",
  selected: null,
  follow: false,
  tab: (localStorageGet("tab") as any) || "chronicle",
  brainsOpen: false,
  newWorldOpen: false,
  nightMode: (localStorageGet("night") as any) || "normal",
  tick: 0,
  toasts: [],
  focus: null,
  director: localStorageGet("director") === "1",
  godOpen: false,
  recordingsOpen: false,
  recording: false,
  godTool: null,
  theme: firstTheme,
  set: (p) => set(p),
}));

function localStorageGet(k: string): string | null {
  try { return localStorage.getItem("chits:" + k); } catch { return null; }
}
export function localStorageSet(k: string, v: string) {
  try { localStorage.setItem("chits:" + k, v); } catch { /* ignore */ }
}

export const worlds: Record<string, WorldData> = { A: new WorldData("A"), B: new WorldData("B") };

export const socket = new Socket(socketUrl());

let errSeq = 0;
/** Say a failed action out loud: a toast with the server's reason (issue #63). */
export function notifyError(text: string) {
  const ui = useUI.getState();
  ui.set({ toasts: [...ui.toasts, { seq: 0, tick: 0, kind: "error", text, importance: 4, actor: null, x: null, y: null, data: {},
    world: "", key: `err-${++errSeq}` }].slice(-5) });
}

let frameCount = 0;
let helloSeen = false;
socket.onStatus((s) => useUI.getState().set({ conn: s }));
socket.onMessage((m) => {
  const ui = useUI.getState();
  switch (m.type) {
    case "hello": {
      const theme = pickTheme(m.theme, window.location.search);
      // the art already drawn belongs to the old theme (the server restarted with another): start over
      if (setTheme(theme) && helloSeen) { window.location.reload(); return; }
      helloSeen = true;
      ui.set({ worlds: m.worlds, control: m.control, brains: m.brains, theme });
      for (const w of m.worlds) if (!worlds[w.id]) worlds[w.id] = new WorldData(w.id);
      if (m.worlds.length === 1 && ui.view !== "A") ui.set({ view: "A" });
      break;
    }
    case "snapshot":
      (worlds[m.world.id] ||= new WorldData(m.world.id)).snapshot(m);
      ui.set({ tick: ui.tick + 1 });
      break;
    case "frame": {
      const w = worlds[m.world];
      if (!w) return;
      w.frame(m);
      // big moments and milestones (a new age, a town, a project done, a first discovery) get a toast
      const toasts = addToasts(ui.toasts, m.events as WorldEvent[], m.world, Date.now());
      if (toasts !== ui.toasts) ui.set({ toasts });
      if (++frameCount % 2 === 0) ui.set({ tick: ui.tick + 1 });
      break;
    }
    case "status":
      ui.set({ control: m.control, brains: m.brains });
      break;
  }
});
socket.connect();
