import { create } from "zustand";
import type { BrainSummary, Control, WorldEvent, WorldMeta } from "../types";
import { Socket, socketUrl, type ConnStatus } from "../net/socket";
import { WorldData } from "./world";

export type Tab = "progress" | "chronicle" | "people" | "knowledge" | "stats" | null;

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
  toasts: (WorldEvent & { world: string; key: string })[];
  focus: { world: string; x: number; y: number; t: number } | null;
  director: boolean; // 🎬 the camera cuts to the drama by itself
  godOpen: boolean;
  recordingsOpen: boolean;
  recording: boolean; // 🎞 auto-record is filming
  godTool: { action: string; item?: string; label: string } | null; // armed: the next map click applies it
  set: (p: Partial<UI>) => void;
};

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

let frameCount = 0;
socket.onStatus((s) => useUI.getState().set({ conn: s }));
socket.onMessage((m) => {
  const ui = useUI.getState();
  switch (m.type) {
    case "hello":
      ui.set({ worlds: m.worlds, control: m.control, brains: m.brains });
      for (const w of m.worlds) if (!worlds[w.id]) worlds[w.id] = new WorldData(w.id);
      if (m.worlds.length === 1 && ui.view !== "A") ui.set({ view: "A" });
      break;
    case "snapshot":
      (worlds[m.world.id] ||= new WorldData(m.world.id)).snapshot(m);
      ui.set({ tick: ui.tick + 1 });
      break;
    case "frame": {
      const w = worlds[m.world];
      if (!w) return;
      w.frame(m);
      const big = (m.events as WorldEvent[]).filter((e) => e.importance >= 4);
      if (big.length) {
        const now = Date.now();
        const toasts = [...ui.toasts, ...big.map((e) => ({ ...e, world: m.world, key: `${m.world}-${e.seq}` }))]
          .filter((t: any) => (t._t ||= now) > now - 9000).slice(-4);
        ui.set({ toasts });
      }
      if (++frameCount % 2 === 0) ui.set({ tick: ui.tick + 1 });
      break;
    }
    case "status":
      ui.set({ control: m.control, brains: m.brains });
      break;
  }
});
socket.connect();
