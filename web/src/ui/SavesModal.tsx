import { useShallow } from "zustand/react/shallow";
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../net/socket";
import { useUI } from "../state/store";
import { fetchSaveFile, importSaveFile, loadConfirm, saveFileName, saveFileProblem, saveLine, type SaveRow } from "./saves";

/** 💾 Saves: save now, load, delete, and one save as one file. The same save points as god mode's. */
export function SavesModal() {
  const { open, set } = useUI(useShallow((s) => ({ open: s.savesOpen, set: s.set })));
  const [saves, setSaves] = useState<SaveRow[]>([]);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const fail = (e: unknown) => setMsg(errorText(e));
  const load = () => api<{ saves: SaveRow[] }>("/api/saves").then((r) => setSaves(r.saves)).catch(fail);
  useEffect(() => { if (open) { setMsg(""); load(); } }, [open]);
  if (!open) return null;
  const now = Date.now() / 1000;
  const run = (work: () => Promise<string>) => {
    setBusy(true);
    work().then(setMsg).catch(fail).finally(() => { setBusy(false); load(); });
  };
  const saveNow = () => run(async () => {
    const s = await api<SaveRow>("/api/saves", { name });
    setName("");
    return `Saved “${s.name}”.`;
  });
  const loadSave = (s: SaveRow) => {
    if (!confirm(loadConfirm(s))) return;
    run(async () => {
      const r = await api<{ control: any }>(`/api/saves/${s.id}/load`, {});
      set({ control: r.control, selected: null, follow: false });
      return `Loaded “${s.name}”. A new timeline starts here.`;
    });
  };
  const remove = (s: SaveRow) => {
    if (!confirm(`Delete the save “${s.name}”? This can't be undone.`)) return;
    run(async () => { await api(`/api/saves/${s.id}`, undefined, "DELETE"); return `Deleted “${s.name}”.`; });
  };
  const exportSave = (s: SaveRow) => run(async () => {
    const url = URL.createObjectURL(await fetchSaveFile(s.id));
    const a = document.createElement("a");
    a.href = url;
    a.download = saveFileName(s.name);
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return `Exported “${s.name}” as ${a.download}.`;
  });
  const importFile = (f: File | undefined) => {
    if (file.current) file.current.value = "";
    if (!f) return;
    const problem = saveFileProblem(f);
    if (problem) { setMsg(problem); return; }
    run(async () => `Imported “${(await importSaveFile(f)).name}” as a new save. Load it when you want it.`);
  };
  return (
    <div className="modal-bg" onClick={() => set({ savesOpen: false })}>
      <div className="modal saves-modal" onClick={(e) => e.stopPropagation()}>
        <h2>💾 Saves</h2>
        <p className="muted small">A save keeps every world as it is now. Loading one takes every world back to it and
          starts a new timeline, and marks the game as modified.</p>
        <div className="saves">
          <div className="row">
            <input placeholder="name this save (e.g. before winter)" value={name} maxLength={60}
              onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !busy) saveNow(); }} />
            <button className="primary" disabled={busy} onClick={saveNow}>Save now</button>
            <button disabled={busy} title="Add a save from a file made with Export" onClick={() => file.current?.click()}>Import</button>
            <input ref={file} type="file" accept=".lcsave,.json,.gz" hidden onChange={(e) => importFile(e.target.files?.[0])} />
          </div>
          {saves.length === 0 && <small className="muted">No saves yet.</small>}
          {saves.map((s) => (
            <div key={s.id} className="save-row">
              <div className="save-what">
                <b>{s.name}</b>
                <small className="muted">{saveLine(s, now)}</small>
              </div>
              <span className="grow" />
              <button disabled={busy} onClick={() => loadSave(s)}>Load</button>
              <button disabled={busy} title="Download this save as one file" onClick={() => exportSave(s)}>Export</button>
              <button disabled={busy} onClick={() => remove(s)}>Delete</button>
            </div>
          ))}
        </div>
        {msg && <p className="god-msg">{msg}</p>}
      </div>
    </div>
  );
}
