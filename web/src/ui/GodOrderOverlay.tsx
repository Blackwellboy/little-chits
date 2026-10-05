import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api, errorText } from "../net/socket";
import { useUI } from "../state/store";

type Chit = { id: string; name: string; alive: boolean; goal?: string };

const VERBS: { action: string; label: string; target: string }[] = [
  { action: "mine", label: "⛏ Mine", target: "e.g. iron, clay, stone" },
  { action: "smelt", label: "🔥 Smelt", target: "e.g. copper, iron" },
  { action: "forge", label: "⚒ Forge", target: "e.g. steel, gear" },
  { action: "build", label: "🏗 Build", target: "e.g. forge, farm" },
  { action: "teach", label: "📖 Teach", target: "a chit or a recipe" },
  { action: "haul", label: "📦 Haul", target: "" },
  { action: "cancel", label: "✖ Cancel sidequest", target: "" },
];

/** 🪄 God-mode Order overlay (SOK-284): dispatch one job to Auto or a picked chit. Map stays visible. */
export function GodOrderOverlay() {
  const { open, set, view } = useUI(useShallow((s) => ({ open: s.godOrderOpen, set: s.set, view: s.view })));
  const wid = view === "split" ? "A" : view;
  const [chits, setChits] = useState<Chit[]>([]);
  const [verb, setVerb] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [text, setText] = useState("");
  const [chit, setChit] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMsg(""); setErr(false);
    api<Chit[]>(`/api/worlds/${wid}/agents`).then((a) => setChits((a || []).filter((c) => c.alive))).catch(() => setChits([]));
  }, [open, wid]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") useUI.getState().set({ godOrderOpen: false }); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;

  const active = VERBS.find((v) => v.action === verb);
  const needsTarget = !!active && active.target !== "";

  const send = () => {
    if (busy) return;
    const body: any = { agent_id: chit === "auto" ? null : chit };
    if (verb) body.action = verb;
    if (target.trim()) body.target = target.trim();
    if (text.trim()) body.text = text.trim();
    if (!body.action && !body.text) { setErr(true); setMsg("pick a job or type one"); return; }
    setBusy(true); setMsg(""); setErr(false);
    api(`/api/worlds/${wid}/god/order`, body)
      .then((r: any) => {
        setErr(false);
        setMsg(r.goal || r.message || (r.outcome === "assigned" ? `ordered ${r.agent_name || "a chit"}` : "queued"));
        setVerb(null); setTarget(""); setText("");
      })
      .catch((e) => { setErr(true); setMsg(errorText(e)); })
      .finally(() => setBusy(false));
  };

  return (
    <div className="god-order">
      <button className="x" onClick={() => set({ godOrderOpen: false })}>✕</button>
      <h3>🪄 Orders</h3>
      <p className="muted small">One job, one chit — Auto, or a picked chit.</p>
      <div className="verb-btns">
        {VERBS.map((v) => (
          <button key={v.action} className={verb === v.action ? "on" : ""} onClick={() => setVerb(v.action)}>
            {v.label}
          </button>
        ))}
      </div>
      {needsTarget && (
        <input className="god-target" placeholder={active!.target} value={target} onChange={(e) => setTarget(e.target.value)} />
      )}
      <div className="row god-who">
        <select value={chit} onChange={(e) => setChit(e.target.value)}>
          <option value="auto">Auto</option>
          {chits.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <input className="god-nl" placeholder="tell them… (e.g. mine iron)" value={text} onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
      <p className="hint">e.g. mine iron · or pick a chip</p>
      <button className="primary god-send" disabled={busy} onClick={send}>{busy ? "Sending…" : "Send"}</button>
      {msg && <p className={`god-order-msg${err ? " err" : ""}`}>{msg}</p>}
    </div>
  );
}
