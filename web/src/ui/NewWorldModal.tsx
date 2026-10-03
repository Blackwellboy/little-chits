import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api } from "../net/socket";
import { useUI, worlds } from "../state/store";
import { packForReset, packLabel, readPackText, type PackInfo } from "./packFile";

/** Start a brand-new pair of worlds: new island (seed), population and map size. */
export function NewWorldModal() {
  const { newWorldOpen, set } = useUI(useShallow((s) => ({ newWorldOpen: s.newWorldOpen, set: s.set })));
  const current = worlds.A?.meta;
  const [seed, setSeed] = useState<string>("");
  const [chits, setChits] = useState(18);
  const [size, setSize] = useState(current?.size ?? 192);
  const { worlds: metas } = useUI(useShallow((s) => ({ worlds: s.worlds })));
  const [mode, setMode] = useState<string>(metas.length === 1 ? "single" : worlds.B?.meta?.culture === "stigmergy" ? "culture" : "versus");
  const [status, setStatus] = useState<any>(null);
  const [pick, setPick] = useState<Record<string, string>>({});
  const [strict, setStrict] = useState(false);
  const [contact, setContact] = useState(false);
  const [scanning, setScanning] = useState(false);
  // 📦 content pack: null keeps the running game's, "none" plays without, an object is a pack the server has checked
  const [packNow, setPackNow] = useState<PackInfo | null>(null);
  const [packChoice, setPackChoice] = useState<Record<string, unknown> | "none" | null>(null);
  const [packInfo, setPackInfo] = useState<PackInfo | null>(null);
  const [packErr, setPackErr] = useState("");
  const pickPack = async (file: File | undefined) => {
    setPackErr("");
    if (!file) return;
    const read = readPackText(await file.text());
    if (!read.ok) { setPackErr(read.error); return; }
    try {
      const r = await api<{ pack: PackInfo }>("/api/pack/check", { pack: read.pack });
      setPackChoice(read.pack); setPackInfo(r.pack);
    } catch (e: any) {
      setPackErr(String(e.message || e));
    }
  };
  const [scanMsg, setScanMsg] = useState("");
  const loadBrains = async () => {
    const s = await api("/api/brains");
    setStatus(s);
    return s;
  };
  // find model servers on this machine, add any new ones, and pre-pick one per world
  const findModels = async () => {
    setScanning(true); setScanMsg("Looking for model servers on this machine…");
    try {
      const r = await api("/api/brains/scan");
      const known = await loadBrains();
      const have = new Set((known.brains ?? []).map((b: any) => b.config.base_url.replace(/\/$/, "") + "|" + (b.config.model || "")));
      for (const f of r.found) {
        const port = (f.base_url.match(/:(\d+)/) || [])[1];
        const model = f.models[0] ?? "";
        if (have.has(f.base_url.replace(/\/$/, "") + "|" + model)) continue;
        await api("/api/brains", { id: `auto${port}`, label: `${model || "model"} :${port}`, base_url: f.base_url, model,
          max_concurrency: f.suggested.max_concurrency, temperature: 0.7, max_tokens: 600, enabled: true });
      }
      const s = await loadBrains();
      const ms = (s.brains ?? []).filter((b: any) => b.config.enabled).map((b: any) => b.config.id);
      if (ms.length) setPick({ A: ms[0], B: ms[1] ?? ms[0] });
      setScanMsg(r.found.length ? `Found ${r.found.length} model server${r.found.length > 1 ? "s" : ""}: ${r.found.map((f: any) => f.base_url.replace("http://", "")).join(", ")}`
        : "No model servers answered. Is llama-server / vLLM / Ollama running? You can also add one by URL in ⚙ Brains.");
    } catch (e: any) {
      setScanMsg("Scan failed: " + String(e.message || e));
    } finally {
      setScanning(false);
    }
  };
  useEffect(() => {
    if (!newWorldOpen) return;
    setPackChoice(null); setPackInfo(null); setPackErr("");
    api<{ pack: PackInfo | null }>("/api/pack").then((r) => setPackNow(r.pack)).catch(() => setPackNow(null));
    loadBrains().then((s) => {
      setPick({ A: s.assign?.A ?? "instinct", B: s.assign?.B ?? "instinct" });
      if (!(s.brains ?? []).some((b: any) => b.config.enabled)) findModels();
    });
  }, [newWorldOpen]);
  const models = (status?.brains ?? []).filter((b: any) => b.config.enabled);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!newWorldOpen) return null;
  const go = async () => {
    setBusy(true); setErr("");
    try {
      await api("/api/reset", { seed: seed.trim() ? parseInt(seed, 10) : Math.floor(Math.random() * 1e6), chits, size, mode, contract: strict ? "experiment" : "play", contact: mode !== "single" && !strict && contact,
        brains: mode === "single" ? { A: pick.A } : { A: pick.A, B: pick.B }, pack: packForReset(packChoice, strict) });
      set({ newWorldOpen: false, selected: null, follow: false });
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-bg" onClick={() => set({ newWorldOpen: false })}>
      <div className="modal" style={{ width: "min(680px, 100%)" }} onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={() => set({ newWorldOpen: false })}>✕</button>
        <h2>⟲ New game</h2>
        <p className="muted">Every world in a game starts from the same new island with the same starting chits.</p>
        <div className="nw-exp">
          {([
            ["versus", "⚔ Model vs model", "Two copies of the exact same island: same seed, same chits, same rules. The only difference is the model."],
            ["single", "🧠 Single model", "One world, one model. Just watch it grow."],
            ["rivals", "⚔🏝 Rivals (Age of Chitpires)", "The islands can find each other by boat. Trade, raid, or make peace."],
            ["culture", "🗣 Culture experiment", "Same island twice, but World B can't talk, teach or write. It can only watch and leave marks."],
          ] as const).map(([m, t, d]) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}><b>{t}</b><small>{d}</small></button>
          ))}
        </div>
        <div className="nw-brains">
          {(mode === "single" ? ["A"] : ["A", "B"]).map((w) => (
            <label key={w}>{mode === "single" ? "Model" : `World ${w}`}
              <select value={pick[w] ?? "instinct"} onChange={(e) => setPick({ ...pick, [w]: e.target.value })}>
                {models.map((b: any) => <option key={b.config.id} value={b.config.id}>{b.label}</option>)}
                <option value="instinct">Instinct (no model)</option>
              </select>
            </label>
          ))}
          <p className="nw-scan"><button disabled={scanning} onClick={findModels}>{scanning ? "Scanning…" : "🔍 Find my models"}</button> <span className="muted">{scanMsg}</span></p>
          {mode === "versus" && pick.A && pick.A === pick.B && pick.A !== "instinct" && <p className="muted">Same model on both sides: a good way to see how much is chance.</p>}
        </div>
        {mode !== "single" && mode !== "rivals" && (
          <label className="nw-strict"><input type="checkbox" checked={contact && !strict} disabled={strict} onChange={(e) => setContact(e.target.checked)} />
            <span><b>⛵ Allow contact between the islands</b> — a chit who builds a boat can sail to the other island and arrive as a stranger, with its own knowledge and mind. {strict ? "(Not in experiments.)" : ""}</span></label>
        )}
        <label className="nw-strict"><input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} />
          <span><b>🧪 Experiment (strict)</b> — every decision is the model's own: no instinct stand-in, settings locked, no meddling. Slower, but fair to compare.</span></label>
        <div className="nw-grid">
          <label>Island seed<input value={seed} placeholder="random" onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ""))} /></label>
          <label>Chits per world<input type="number" min={2} max={60} value={chits} onChange={(e) => setChits(Math.max(2, Math.min(60, +e.target.value || 2)))} /></label>
          <label>Map size
            <select value={size} onChange={(e) => setSize(+e.target.value)}>
              <option value={128}>Small · 128²</option>
              <option value={192}>Medium · 192²</option>
              <option value={256}>Large · 256²</option>
              <option value={384}>Huge · 384² (room for towns and roads)</option>
              <option value={512}>Giant · 512² (4× large)</option>
            </select>
          </label>
        </div>
        <div className="nw-pack">
          <b>📦 Content pack</b> <span className="muted">optional: a JSON file that adds items and recipes to this game
            (see docs/modding.md). Every world gets the same pack.</span>
          <p>
            {strict ? "An experiment runs without a pack."
              : packChoice === "none" ? "This game: no pack."
              : packChoice ? `This game: ${packLabel(packInfo)}.`
              : `This game: ${packLabel(packNow)}${packNow ? " (kept from the current game)" : ""}.`}
          </p>
          {!strict && (
            <p>
              <input type="file" accept=".json,application/json" onChange={(e) => pickPack(e.target.files?.[0])} />
              {(packChoice && packChoice !== "none" || (!packChoice && packNow)) &&
                <button onClick={() => { setPackChoice("none"); setPackInfo(null); setPackErr(""); }}>No pack</button>}
            </p>
          )}
          {packErr && <p className="err">{packErr}</p>}
        </div>
        <p className="warn">This permanently replaces the current worlds and their history.</p>
        {err && <p className="err">{err}</p>}
        <div className="row"><button className="primary" disabled={busy} onClick={go}>{busy ? "Creating…" : "Start"}</button><button onClick={() => set({ newWorldOpen: false })}>Cancel</button></div>
      </div>
    </div>
  );
}
