import { useEffect, useState } from "react";
import { api } from "../net/socket";
import { useUI } from "../state/store";

/** First visit (T29): what this is, what was found on this machine, and where to go next. */
export function Welcome() {
  const [show, setShow] = useState(() => { try { return !localStorage.getItem("chits:welcomed"); } catch { return false; } });
  const [h, setH] = useState<any>(null);
  const [story, setStory] = useState<any>(null);
  const set = useUI((s) => s.set);
  const view = useUI((s) => s.view);
  // the story of the world in view (it was always World A's)
  const wid = view === "B" ? "B" : view === "split" ? (() => { try { return localStorage.getItem("chits:panelWorld") || "A"; } catch { return "A"; } })() : "A";
  useEffect(() => { if (show) api("/api/health").then(setH).catch(() => {}); }, [show]);
  useEffect(() => { if (show) api(`/api/worlds/${wid}/recap`).then(setStory).catch(() => {}); }, [show, wid]);
  if (!show || new URLSearchParams(location.search).get("record")) return null;
  const close = () => { try { localStorage.setItem("chits:welcomed", "1"); } catch { /* private mode */ } setShow(false); };
  const found: any[] = h?.autodetected || [];
  const port = (u: string) => { try { return ":" + new URL(u).port; } catch { return u; } };
  const name = (f: any) => f.model || f.label || f.id || "a model";
  // models chosen earlier (in ⚙ Brains or a preset) rather than found by the first-run scan
  const inUse = Object.entries((h?.brains || {}) as Record<string, string>).filter(([, label]) => label && !label.startsWith("Instinct"));
  return (
    <div className="modal-bg" onClick={close}>
      <div className="modal welcome" onClick={(e) => e.stopPropagation()}>
        <h2>Welcome to Little Chits</h2>
        <p>Tiny creatures wake up on an island knowing almost nothing. They get hungry and cold, experiment with what
          they find, build, teach each other and grow old. An AI model is the mind inside each chit: put different
          models in two identical worlds and watch how differently their civilisations grow.</p>
        <p className="found">
          {found.length >= 2 ? <>Found <b>{name(found[0])}</b> on {port(found[0].base_url)} and <b>{name(found[1])}</b> on {port(found[1].base_url)}: model vs model on the same island.</>
            : found.length === 1 ? <>Found <b>{name(found[0])}</b> on {port(found[0].base_url)}: a single-model world.</>
            : inUse.length ? <>{inUse.map(([wid, label], i) => <span key={wid}>{i ? " and " : ""}World {wid} thinks with <b>{label}</b></span>)}.</>
            : h ?<>No model found. Start llama-server, Ollama or LM Studio, then press 🔍 Scan in ⚙ Brains. Until then the chits run on instinct.</>
            : <>Looking at what's running…</>}
        </p>
        {story && story.day > 3 && (
          <div className="so-far">
            <h3>📜 {story.title}</h3>
            <ul className="recap">{story.lines.slice(0, 6).map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
          </div>
        )}
        <div className="row">
          <button className="primary" onClick={close}>Watch</button>
          <button onClick={() => { close(); set({ brainsOpen: true }); }}>Open Brains</button>
          <button onClick={() => { close(); set({ newWorldOpen: true }); }}>New game</button>
        </div>
      </div>
    </div>
  );
}
