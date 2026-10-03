import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api, errorText } from "../net/socket";
import { useUI } from "../state/store";

type Speed = { level: "good" | "ok" | "slow" | "unknown"; capacity: number; chits: number; text: string };
type BrainRow = { config: any; stats: any; label: string; healthy: boolean; speed?: Speed };

const BLANK = { id: "", label: "", base_url: "http://127.0.0.1:18090/v1", model: "", api_key: "", max_concurrency: 6, disable_thinking: true, json_mode: true, temperature: 0.7, max_tokens: 600 };

function thoughtText(l: any): string {
  if (!l.ok) return "";
  if (l.steps) {
    const chain = l.steps.map((s: any) =>
      s.do + (s.what ? " " + (Array.isArray(s.what) ? s.what.join("+") : s.what) : s.with ? " " + s.with.join("+") : "")).join(" → ");
    return ": " + chain;
  }
  if (l.chose) {
    const conf = l.confidence != null ? " (" + Math.round(l.confidence * 100) + "%)" : "";
    return " picked " + l.chose + conf + (l.escalated ? " · escalated to a full plan" : "");
  }
  return "";
}

function ago(t: number): string {
  const s = Math.max(0, Date.now() / 1000 - t);
  return s < 90 ? "just now" : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}

export function BrainsModal() {
  const { brainsOpen, set, worlds: metas } = useUI(useShallow((s) => ({ brainsOpen: s.brainsOpen, set: s.set, worlds: s.worlds })));
  const [status, setStatus] = useState<any>(null);
  const [form, setForm] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [msg, setMsg] = useState<string>("");
  const [testing, setTesting] = useState<string>("");
  const [found, setFound] = useState<any[] | null>(null);

  const reload = () => api("/api/brains").then(setStatus);
  useEffect(() => {
    if (!brainsOpen) return;
    reload();
    const t = setInterval(reload, 2000);
    return () => clearInterval(t);
  }, [brainsOpen]);
  if (!brainsOpen) return null;

  const probe = async (url: string, key: string, base?: any) => {
    setMsg("Looking for models…"); setModels([]);
    const r = await api("/api/brains/probe", { base_url: url, api_key: key });
    if (r.ok) {
      setModels(r.models);
      // use the URL that actually answered, and the server's own slot count for parallel requests
      setForm((f: any) => ({ ...(base ?? f), base_url: r.base_url, max_concurrency: r.suggested.max_concurrency, model: (base ?? f)?.model || r.models[0] || "" }));
      setMsg(`Found ${r.models.length} model(s) at ${r.base_url}${r.slots ? ` · ${r.slots} slots → ${r.suggested.max_concurrency} parallel requests` : ""}.`);
    }
    else setMsg("Nothing answered there. Try 🔍 Scan, or check the port your model server uses. (" + r.error + ")");
  };
  const scan = async () => {
    setMsg("Scanning local ports for model servers…"); setFound(null);
    const r = await api("/api/brains/scan");
    setFound(r.found);
    setMsg(r.found.length ? `Found ${r.found.length} model server(s). Pick one to add it.` : "No model servers answered on the usual ports (18090, 18080, 8080, 8000, 11434, 1234, 5000, 30000…). Is llama-server / vLLM / Ollama running on this machine?");
  };
  const addFound = (f: any) => {
    const port = (f.base_url.match(/:(\d+)/) || [])[1];
    const preset = (status?.presets ?? []).find((p: any) => p.base_url.replace(/\/$/, "") === f.base_url.replace(/\/$/, ""));
    setForm({ ...BLANK, ...(preset ?? {}), id: preset?.id ?? "", label: preset?.label ?? `${f.models[0] ?? "model"} :${port}`, enabled: true,
      base_url: f.base_url, model: f.models[0] ?? "", max_concurrency: f.suggested.max_concurrency });
    setModels(f.models); setFound(null);
  };
  const save = async () => {
    const body = { ...form, max_concurrency: +form.max_concurrency, temperature: +form.temperature, max_tokens: +form.max_tokens };
    let r: any;
    try { r = await api("/api/brains", body); } catch (e) { setMsg(`✗ Not saved: ${errorText(e)}`); return; }
    setForm(null); setModels([]); setMsg(`Saved “${r.brain.label || r.brain.id}”.`);
    reload();
  };
  const assign = async (world: string, brain: string) => {
    try { await api(`/api/worlds/${world}/brain`, { brain }); }
    catch (e) { setMsg(`✗ World ${world} kept its brain: ${errorText(e)}`); }  // (a 409 used to vanish, issue #63)
    reload();
  };
  const test = async (id: string) => {
    setTesting(id);
    const r = await api(`/api/brains/${id}/test`, {});
    setTesting("");
    setMsg(r.ok ? `✓ ${r.model} replied in ${r.latency_ms} ms: ${r.reply}` : `✗ ${r.error}`);
  };
  const remove = async (id: string) => {
    try { await api(`/api/brains/${id}`, undefined, "DELETE"); } catch (e) { setMsg(`✗ Not removed: ${errorText(e)}`); }
    reload();
  };

  const brains: BrainRow[] = status?.brains ?? [];
  const ready = brains.filter((b) => b.config.enabled);
  const [wa, wb] = [metas[0]?.id ?? "A", metas[1]?.id];
  const matchup = async (a: string, b: string) => { await assign(wa, a); if (wb) await assign(wb, b); };
  return (
    <div className="modal-bg" onClick={() => set({ brainsOpen: false })}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={() => set({ brainsOpen: false })}>✕</button>
        <h2>🧠 Brains</h2>
        <p className="muted">Point any OpenAI-compatible server at the chits: llama.cpp, vLLM, Ollama, LM Studio, SGLang, OpenRouter… Each world can use a different model, which makes model comparisons easy. <b>Instinct</b> is the built-in no-model baseline, and it takes over automatically whenever a model is slow or down.</p>

        {wb && (
          <div className="matchups">
            <span className="muted">Matchup:</span>
            <button disabled={ready.length < 2} onClick={() => matchup(ready[0].config.id, ready[1].config.id)} title="A different model in each world">⚔ Model vs model</button>
            <button onClick={() => matchup("instinct", "instinct")}>🌱 Both on instinct</button>
          </div>
        )}
        <div className="assign">
          {metas.map((w) => (
            <label key={w.id}>
              <span><i className={`dot ${w.culture}`} /> {w.name} <small className="muted">{w.label}</small></span>
              <select value={status?.assign?.[w.id] ?? "instinct"} onChange={(e) => assign(w.id, e.target.value)}>
                <option value="instinct">Instinct (no model)</option>
                {brains.map((b) => <option key={b.config.id} value={b.config.id} disabled={!b.config.enabled}>{b.label}</option>)}
              </select>
            </label>
          ))}
        </div>

        <label className="narrator-pick" title="One storyteller for every world, so the better writer doesn't make its world look better">✒ Narrator
          <select value={status?.narrator ?? ""} onChange={(e) => api("/api/narrator", { brain: e.target.value }).then(reload)}>
            <option value="">Each world's own model</option>
            {brains.map((b) => <option key={b.config.id} value={b.config.id}>{b.label}</option>)}
          </select>
        </label>
        <h3>Endpoints</h3>
        <div className="brain-list">
          {brains.map((b) => (
            <div key={b.config.id} className={`brain ${b.healthy ? "" : "bad"}`}>
              <div>
                <b>{b.label}</b> <small className="muted">{b.config.base_url} · {b.stats.resolved_model || b.config.model || "auto"}</small>
                <div className="bstats">
                  <span>{b.stats.ok} ok</span><span>{b.stats.failed} failed</span><span>{b.stats.parse_failed} garbled</span>
                  <span>{Math.round(b.stats.latency_ms_avg)} ms</span><span>{Math.round(b.stats.tok_per_s)} tok/s</span>
                  <span>{b.stats.in_flight} in flight</span>{b.stats.queued > 0 && <span>{b.stats.queued} queued</span>}
                </div>
                {b.speed && b.speed.level !== "unknown" && (
                  <small className={`speed speed-${b.speed.level}`}>{b.speed.text}</small>
                )}
                {b.stats.last_error && <small className="err">{b.stats.last_error}{b.stats.last_error_at ? ` (${ago(b.stats.last_error_at)})` : ""}</small>}
              </div>
              <div className="actions">
                <button onClick={() => test(b.config.id)} disabled={testing === b.config.id}>{testing === b.config.id ? "…" : "Test"}</button>
                <button onClick={() => { setForm({ ...BLANK, ...b.config }); setModels([]); }}>Edit</button>
                <button className="danger" onClick={() => remove(b.config.id)}>✕</button>
              </div>
            </div>
          ))}
          {!brains.length && <p className="muted">No models yet. Add one below. The chits run on instinct until you do.</p>}
        </div>

        {!form && (
          <div className="presets">
            <button className="primary" onClick={scan}>🔍 Scan for models</button>
            <button onClick={() => setForm({ ...BLANK })}>+ Add by URL</button>
            {(status?.presets ?? []).map((p: any) => (
              <button key={p.id} onClick={() => { const f = { ...BLANK, ...p, enabled: true }; setForm(f); probe(p.base_url, "", f); }}>{p.label}</button>
            ))}
          </div>
        )}
        {!form && found && found.length > 0 && (
          <div className="brain-list">
            {found.map((f) => (
              <div key={f.base_url} className="brain">
                <div><b>{f.base_url}</b> <small className="muted">{f.models.slice(0, 3).join(", ")}{f.models.length > 3 ? "…" : ""}{f.slots ? ` · ${f.slots} slots` : ""}</small></div>
                <div className="actions">{f.added ? <small className="muted">added</small> : <button className="primary" onClick={() => addFound(f)}>Use</button>}</div>
              </div>
            ))}
          </div>
        )}

        {form && (
          <div className="form">
            <label>Name <input value={form.label} placeholder="e.g. Qwen 27B on the 5090" onChange={(e) => setForm({ ...form, label: e.target.value })} /></label>
            <label>Base URL <span className="inline"><input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} /><button onClick={() => probe(form.base_url, form.api_key)}>Find models</button></span></label>
            <label>Model
              {models.length ? (
                <select value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
                  <option value="">(first listed)</option>
                  {models.map((m) => <option key={m}>{m}</option>)}
                </select>
              ) : <input value={form.model} placeholder="blank = whatever the server serves" onChange={(e) => setForm({ ...form, model: e.target.value })} />}
            </label>
            <label>API key <input value={form.api_key} placeholder="optional · or env:MY_KEY_VAR" onChange={(e) => setForm({ ...form, api_key: e.target.value })} /></label>
            <div className="grid3">
              <label title="How many chits can think at once. Match your server’s slots (llama-server -np N); detected automatically.">Parallel requests <input type="number" min={1} max={64} value={form.max_concurrency} onChange={(e) => setForm({ ...form, max_concurrency: e.target.value })} /></label>
              <label title="0.7 is the sweet spot: varied plans, still valid JSON.">Temperature <input type="number" step={0.1} min={0} max={2} value={form.temperature} onChange={(e) => setForm({ ...form, temperature: e.target.value })} /></label>
              <label title="600 fits a plan plus a short thought. Raise for chatty reasoning models.">Max tokens <input type="number" min={100} max={4000} value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: e.target.value })} /></label>
            </div>
            <label>Prompt
              <select value={form.prompt_style ?? "full"} onChange={(e) => setForm({ ...form, prompt_style: e.target.value })}>
                <option value="full">Full (best for 14B+ models)</option>
                <option value="compact">Compact (small models or short context)</option>
                <option value="choose">Choose (fastest: the model picks one of a few drafted plans · slow GPUs)</option>
              </select>
            </label>
            <label className="check"><input type="checkbox" checked={form.disable_thinking} onChange={(e) => setForm({ ...form, disable_thinking: e.target.checked })} /> Ask reasoning models (Qwen3 etc.) to skip long thinking</label>
            <label className="check"><input type="checkbox" checked={form.json_mode} onChange={(e) => setForm({ ...form, json_mode: e.target.checked })} /> Request JSON mode (turned off automatically if the server doesn't support it)</label>
            <label className="check" title="Plans that are only eating, sleeping, resting or hauling go to instinct, so the model has time for the decisions that matter. Never in an experiment."><input type="checkbox" checked={form.focus ?? true} onChange={(e) => setForm({ ...form, focus: e.target.checked })} /> Focus the model on the decisions that matter (instinct handles eating, sleeping and hauling)</label>
            <div className="row"><button className="primary" onClick={save}>Save</button><button onClick={() => { setForm(null); setModels([]); }}>Cancel</button></div>
          </div>
        )}
        {msg && <p className="msg">{msg}</p>}

        {status?.log?.length > 0 && (
          <>
            <h3>Recent thoughts</h3>
            <ul className="thoughts">
              {status.log.slice().reverse().slice(0, 12).map((l: any, i: number) => (
                <li key={i} className={l.ok ? "" : "bad"}>
                  <b>{l.agent}</b> <small className="muted">{l.brain} · {l.wall_ms} ms</small>
                  {l.ok ? <p>“{l.thought}” → <i>{l.goal ?? l.chose}</i>{thoughtText(l)}</p>
                    : <p className="err">{l.error}{l.raw ? ` — “${l.raw.slice(0, 120)}”` : ""}</p>}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
