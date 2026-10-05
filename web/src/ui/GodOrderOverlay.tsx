import { useShallow } from "zustand/react/shallow";
import { useEffect, useMemo, useState } from "react";
import { api, errorText } from "../net/socket";
import { useUI } from "../state/store";

type Chit = { id: string; name: string; alive: boolean; goal?: string };

type LastOrder = {
  label: string;
  who: string;
  outcome: string;
  detail: string;
  at: number;
};

const VERBS: { action: string; label: string; target: string }[] = [
  { action: "mine", label: "⛏ Mine", target: "e.g. iron, clay, stone" },
  { action: "smelt", label: "🔥 Smelt", target: "e.g. copper, iron" },
  { action: "forge", label: "⚒ Forge", target: "e.g. steel, gear" },
  { action: "build", label: "🏗 Build", target: "e.g. forge, farm" },
  { action: "teach", label: "📖 Teach", target: "a chit or a recipe" },
  { action: "haul", label: "📦 Haul", target: "" },
  { action: "cancel", label: "✖ Cancel sidequest", target: "" },
];

const LAST_KEY = "chits.godOrder.last";

function loadLast(): LastOrder[] {
  try {
    const raw = sessionStorage.getItem(LAST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, 5) : [];
  } catch {
    return [];
  }
}

function saveLast(entries: LastOrder[]) {
  try {
    sessionStorage.setItem(LAST_KEY, JSON.stringify(entries.slice(0, 5)));
  } catch { /* ignore */ }
}

/** Resolve what Send will submit. NL (non-empty) always wins over verb chips — never a silent mismatch. */
function resolveOrder(verb: string | null, target: string, text: string) {
  const nl = text.trim();
  if (nl) return { mode: "nl" as const, label: nl, action: null as string | null, target: null as string | null, text: nl };
  if (verb) {
    const v = VERBS.find((x) => x.action === verb);
    const t = target.trim();
    const label = t ? `${v?.label.replace(/^[^\s]+\s/, "") || verb} ${t}` : (v?.label.replace(/^[^\s]+\s/, "") || verb);
    return { mode: "chip" as const, label, action: verb, target: t || null, text: null as string | null };
  }
  return null;
}

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
  const [last, setLast] = useState<LastOrder[]>(() => loadLast());

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

  const nlActive = text.trim().length > 0;
  const order = useMemo(() => resolveOrder(verb, target, text), [verb, target, text]);
  const whoLabel = chit === "auto"
    ? "Auto"
    : (chits.find((c) => c.id === chit)?.name || "picked chit");
  const preview = order ? `Order: ${order.label} → ${whoLabel}` : null;
  const active = !nlActive ? VERBS.find((v) => v.action === verb) : undefined;
  const needsTarget = !!active && active.target !== "";

  const pickVerb = (action: string) => {
    if (nlActive) return; // NL wins — chips disabled while typing
    setVerb(action);
    setText(""); // chip path: clear NL so nothing fights the chip
    setMsg(""); setErr(false);
  };

  const onNlChange = (value: string) => {
    setText(value);
    if (value.trim()) {
      // NL overrides: clear chip selection so the UI can't lie
      setVerb(null);
      setTarget("");
    }
    setMsg(""); setErr(false);
  };

  const pushLast = (entry: LastOrder) => {
    setLast((prev) => {
      const next = [entry, ...prev].slice(0, 5);
      saveLast(next);
      return next;
    });
  };

  const send = () => {
    if (busy) return;
    const resolved = resolveOrder(verb, target, text);
    if (!resolved) { setErr(true); setMsg("pick a job or type one"); return; }
    const body: Record<string, unknown> = { agent_id: chit === "auto" ? null : chit };
    // NL non-empty → send only text (never also action). Chip path → action + optional target.
    if (resolved.mode === "nl") {
      body.text = resolved.text;
    } else {
      body.action = resolved.action;
      if (resolved.target) body.target = resolved.target;
    }
    setBusy(true); setMsg(""); setErr(false);
    api(`/api/worlds/${wid}/god/order`, body)
      .then((r: any) => {
        setErr(false);
        const outcome = String(r.outcome || "done");
        const name = r.agent_name || (chit === "auto" ? null : whoLabel);
        let status: string;
        if (outcome === "assigned") {
          status = `Assigned: ${name || "a chit"}${r.goal ? ` — ${r.goal}` : ""}`;
        } else if (outcome === "queued") {
          status = r.message || `Queued${name ? ` for ${name}` : ""}`;
        } else {
          status = r.message || r.goal || outcome;
        }
        setMsg(status);
        pushLast({
          label: resolved.label,
          who: chit === "auto" ? `Auto${name ? ` (${name})` : ""}` : whoLabel,
          outcome,
          detail: status,
          at: Date.now(),
        });
        setVerb(null); setTarget(""); setText("");
      })
      .catch((e) => {
        const reason = errorText(e);
        setErr(true);
        setMsg(reason);
        pushLast({
          label: resolved.label,
          who: whoLabel,
          outcome: "refused",
          detail: reason,
          at: Date.now(),
        });
      })
      .finally(() => setBusy(false));
  };

  if (!open) return null;

  return (
    <div className="god-order">
      <button className="x" onClick={() => set({ godOrderOpen: false })}>✕</button>
      <h3>🪄 Orders</h3>
      <p className="muted small">One job, one chit — Auto, or a picked chit.</p>
      <div className={`verb-btns${nlActive ? " dimmed" : ""}`}>
        {VERBS.map((v) => (
          <button
            key={v.action}
            type="button"
            className={verb === v.action && !nlActive ? "on" : ""}
            disabled={nlActive}
            title={nlActive ? "Clear the tell-them field to use chips" : undefined}
            onClick={() => pickVerb(v.action)}
          >
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
      <input
        className="god-nl"
        placeholder="tell them… (e.g. mine iron)"
        value={text}
        onChange={(e) => onNlChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") send(); }}
      />
      <p className="hint">
        {nlActive
          ? "Typing wins over chips — chips stay off until the field is empty"
          : "e.g. mine iron · or pick a chip"}
      </p>
      {preview && <p className="god-preview">{preview}</p>}
      <button className="primary god-send" disabled={busy || !order} onClick={send}>
        {busy ? "Sending…" : "Send"}
      </button>
      {msg && <p className={`god-order-msg${err ? " err" : ""}`}>{msg}</p>}
      {last.length > 0 && (
        <div className="god-last">
          <p className="god-last-title">Last orders</p>
          <ul>
            {last.map((e, i) => (
              <li key={`${e.at}-${i}`}>
                <span className={`god-last-out ${e.outcome}`}>{e.outcome}</span>
                {" "}{e.label} → {e.who}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
