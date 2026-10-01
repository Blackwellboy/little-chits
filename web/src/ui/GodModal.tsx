import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api } from "../net/socket";
import { useUI } from "../state/store";

type ItemRow = { key: string; name: string; icon: string; artifact: boolean; props: string[] };
type Save = { id: number; name: string; created: number; tick: number };

const ACTS: { action: string; icon: string; label: string; hint: string; needsTile: boolean }[] = [
  { action: "meteor", icon: "☄️", label: "Meteor", hint: "crashes down, damages buildings, leaves a meteorite", needsTile: true },
  { action: "bless", icon: "✨", label: "Bless", hint: "fills everyone nearby with food, warmth and health", needsTile: true },
  { action: "smite", icon: "⚡", label: "Smite", hint: "lightning: hurts (never kills) and damages", needsTile: true },
  { action: "feast", icon: "🍞", label: "Feast", hint: "30 bread appear", needsTile: true },
  { action: "plague", icon: "🦠", label: "Plague", hint: "a fifth of the chits fall ill", needsTile: false },
  { action: "storm", icon: "⛈", label: "Storm", hint: "a great storm for a day", needsTile: false },
  { action: "drought", icon: "☀️", label: "Drought", hint: "the rains stop", needsTile: false },
  { action: "snow", icon: "🌨", label: "Snow", hint: "snow out of season", needsTile: false },
];

/** 🪄 God mode (T28): drop anything, meddle, and save points to rewind to. */
export function GodModal() {
  const { godOpen, set, view } = useUI(useShallow((s) => ({ godOpen: s.godOpen, set: s.set, view: s.view })));
  const [tab, setTab] = useState<"artifacts" | "items" | "acts" | "saves">("artifacts");
  const [items, setItems] = useState<ItemRow[]>([]);
  const [q, setQ] = useState("");
  const [saves, setSaves] = useState<Save[]>([]);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const loadSaves = () => api<Save[]>("/api/savepoints").then(setSaves).catch(() => {});
  useEffect(() => {
    if (!godOpen) return;
    api<ItemRow[]>("/api/items").then(setItems).catch(() => {});
    loadSaves();
  }, [godOpen]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") useUI.getState().set({ godTool: null }); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!godOpen) return null;
  const arm = (t: { action: string; item?: string; label: string }) => set({ godTool: t, godOpen: false });
  const now = (action: string) => {
    const wid = view === "split" ? "A" : view;
    api(`/api/worlds/${wid}/god`, { action }).then((r: any) => setMsg(r.event)).catch((e) => setMsg(String(e.message || e)));
  };
  const shown = items.filter((i) => (tab === "artifacts" ? i.artifact : !i.artifact) &&
    (!q || i.name.toLowerCase().includes(q.toLowerCase()) || i.key.includes(q.toLowerCase())));
  return (
    <div className="modal-bg" onClick={() => set({ godOpen: false })}>
      <div className="modal god" onClick={(e) => e.stopPropagation()}>
        <h2>🪄 God mode</h2>
        <p className="muted small">Pick something, then click the map to put it there (Esc cancels). Chits find out what things
          do the usual way: picking them up, studying them, experimenting. Meddling marks this run as a sandbox.</p>
        <div className="tabs">
          {(["artifacts", "items", "acts", "saves"] as const).map((t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
              {{ artifacts: "👽 Artifacts", items: "📦 Items", acts: "⚡ Acts", saves: "💾 Save points" }[t]}</button>
          ))}
        </div>
        {(tab === "artifacts" || tab === "items") && (
          <>
            {tab === "items" && <input className="search" placeholder="search items…" value={q} onChange={(e) => setQ(e.target.value)} />}
            <div className="god-grid">
              {shown.map((i) => (
                <button key={i.key} title={i.props.join(", ")} onClick={() => arm({ action: "drop", item: i.key, label: `${i.icon} ${i.name}` })}>
                  <span className="gi">{i.icon || "📦"}</span><small>{i.name}</small>
                </button>
              ))}
            </div>
          </>
        )}
        {tab === "acts" && (
          <div className="god-grid acts">
            {ACTS.map((a) => (
              <button key={a.action} title={a.hint} onClick={() => (a.needsTile ? arm({ action: a.action, label: `${a.icon} ${a.label}` }) : now(a.action))}>
                <span className="gi">{a.icon}</span><small>{a.label}</small><small className="muted">{a.hint}</small>
              </button>
            ))}
          </div>
        )}
        {tab === "saves" && (
          <div className="saves">
            <div className="row">
              <input placeholder="name this moment (e.g. before the meteor)" value={name} onChange={(e) => setName(e.target.value)} />
              <button className="primary" onClick={() => api("/api/savepoints", { name }).then(() => { setName(""); loadSaves(); setMsg("Saved."); })}>💾 Save</button>
            </div>
            {saves.length === 0 && <small className="muted">No save points yet.</small>}
            {saves.map((s) => (
              <div key={s.id} className="save-row">
                <b>{s.name}</b> <small className="muted">day {Math.floor(s.tick / 240) + 1} · {new Date(s.created * 1000).toLocaleString()}</small>
                <span className="grow" />
                <button onClick={() => { if (confirm(`Rewind every world to “${s.name}”?`)) api(`/api/savepoints/${s.id}/restore`, {}).then(() => setMsg(`Restored “${s.name}”.`)).catch((e) => setMsg(String(e.message || e))); }}>Restore</button>
                <button onClick={() => api(`/api/savepoints/${s.id}`, undefined, "DELETE").then(loadSaves)}>Delete</button>
              </div>
            ))}
          </div>
        )}
        {msg && <p className="god-msg">{msg}</p>}
      </div>
    </div>
  );
}

/** Shown while a god tool is armed. */
export function GodBanner() {
  const tool = useUI((s) => s.godTool);
  if (!tool) return null;
  return <div className="god-banner">🪄 {tool.label}: click the map to place it <button onClick={() => useUI.getState().set({ godTool: null })}>cancel (Esc)</button></div>;
}
