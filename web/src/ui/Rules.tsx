import { useEffect, useState } from "react";
import { api } from "../net/socket";
import { useUI } from "../state/store";

/** World rules (server/chits/sim/rules.py, docs/WORLD_RULES.md): what kinds of civilisation a world allows. */
export type RuleSpec = { default: boolean; label: string; off: string };
export type Preset = { label: string; rules: Record<string, boolean>; model_led: boolean; about: string };
export type RulesInfo = {
  version: number; rules: Record<string, RuleSpec>; presets: Record<string, Preset>;
  current: Record<string, unknown>; worlds: Record<string, Record<string, unknown>>;
};

export function useRules(open = true): RulesInfo | null {
  const [info, setInfo] = useState<RulesInfo | null>(null);
  useEffect(() => {
    if (!open) return;
    api<RulesInfo>("/api/rules").then(setInfo).catch(() => setInfo(null));
  }, [open]);
  return info;
}

/** Every rule at its value: a preset's (or the chosen) ones over the defaults. */
export function fullRules(info: RulesInfo, chosen: Record<string, boolean>): Record<string, boolean> {
  return Object.fromEntries(Object.entries(info.rules).map(([k, s]) => [k, chosen[k] ?? s.default]));
}

/** The New Game Rules section: presets, then each rule with what switching it off means. Fixed for the game's life. */
export function RulesPicker({ info, rules, setRules, modelLed, setModelLed, strict }: {
  info: RulesInfo; rules: Record<string, boolean>; setRules: (r: Record<string, boolean>) => void;
  modelLed: boolean; setModelLed: (v: boolean) => void; strict: boolean;
}) {
  const [advanced, setAdvanced] = useState(false);
  const full = fullRules(info, rules);
  const preset = Object.entries(info.presets).find(([, p]) =>
    Object.entries(fullRules(info, p.rules)).every(([k, v]) => full[k] === v) && (strict || p.model_led === modelLed))?.[0];
  return (
    <div className="nw-rules">
      <b>📜 Rules of this world</b>{" "}
      <span className="muted">what is possible here. Fixed for the game's life, saved with it, and shown in the 📜 panel.</span>
      <div className="nw-presets">
        {Object.entries(info.presets).map(([id, p]) => (
          <button key={id} className={preset === id ? "on" : ""} title={p.about}
            onClick={() => { setRules({ ...p.rules }); setModelLed(p.model_led); }}>
            <b>{p.label}</b><small>{p.about}</small>
          </button>
        ))}
      </div>
      {!strict && (
        <label className="nw-strict" title="The model supplies the intelligence; the chit keeps its body (reflexes) and the simulator carries out each step. No instinct plans, filler or fallback for a model's chits: a slow or absent model leaves them waiting, shown, never on hidden instinct.">
          <input type="checkbox" checked={modelLed} onChange={(e) => setModelLed(e.target.checked)} />
          <span><b>🧠 Model-led</b> — the model decides; the body keeps its reflexes; nothing hidden stands in.</span>
        </label>
      )}
      <p><button className="link" onClick={() => setAdvanced(!advanced)}>{advanced ? "▾" : "▸"} Advanced rules</button></p>
      {advanced && (
        <div className="nw-rule-list">
          {Object.entries(info.rules).map(([k, s]) => (
            <label key={k} title={`Off: ${s.off}`}>
              <input type="checkbox" checked={full[k]} onChange={(e) => setRules({ ...rules, [k]: e.target.checked })} />
              <span>{s.label}{full[k] === s.default ? "" : <small className="muted"> (changed)</small>}
                <br /><small className="muted">Off: {s.off}</small></span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

/** The 📜 panel: the rules the running worlds were made with, read-only. */
export function RulesPanel() {
  const info = useRules(true);  // (the rules' descriptions: they don't change)
  // the running worlds' own rules come with their metadata, so a new game shows its rules at once (Codex on #143)
  const metas = useUI((s) => s.worlds);
  if (!info) return <p className="muted">Loading…</p>;
  const ids = Object.keys(info.worlds);
  const r = (metas[0]?.rules ?? (ids.length ? info.worlds[ids[0]] : info.current)) as Record<string, unknown>;
  return (
    <div>
      <div className="panel-head"><h3>📜 World rules</h3><small className="muted">version {String(r.version ?? info.version)}</small></div>
      <p className="muted small">Chosen when this game began and fixed for its life (docs/WORLD_RULES.md). Every world of the game shares them.</p>
      <table className="rules-table"><tbody>
        {Object.entries(info.rules).map(([k, s]) => {
          const on = r[k] !== false;
          return (
            <tr key={k} title={on ? "" : `Off: ${s.off}`}>
              <td>{on ? "✅" : "⛔"}</td><td>{s.label}{on === s.default ? "" : <small className="muted"> (changed)</small>}
                {!on && <><br /><small className="muted">{s.off}</small></>}</td>
            </tr>
          );
        })}
      </tbody></table>
    </div>
  );
}
