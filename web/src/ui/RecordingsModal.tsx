import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api } from "../net/socket";
import { useUI } from "../state/store";
import { CAP_MAX_GB, CAP_MIN_GB, diskMeter, parseCapGb, type RecorderStorage } from "./diskMeter";

export type RecorderStatus = {
  enabled: boolean; recording: boolean; interval_ms: number; fps: number; aspect: string; world: string;
  frames_waiting: number; encoding: number; last_clip: string; last_error: string; run: string; missing: string[];
  moments: boolean; filming: string; moments_waiting: number; retention_gb?: number; storage?: RecorderStorage;
};
type Item = { day?: number; week?: number; story: string; clip: string | null };
/** a big event filmed close up at live speed (recorder.py Moments) */
type Moment = { name: string; clip: string; day: number; world: string; world_name?: string; kind: string; clock?: string;
  caption: string; seconds?: number };
type Run = { run: string; mode?: string; started?: number; current: boolean; worlds?: { name: string; brain: string }[];
  days: Item[]; weeks: Item[]; moments?: Moment[]; cuts?: { week: number; story: string; video: string | null }[] };

/** A small, safe markdown renderer for the recording stories: headings, bullets, bold, italics and links. */
function renderMarkdown(md: string, base: string): string {
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s: string) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>")
    .replace(/\(#(\d+)\)/g, '<small class="muted">(#$1)</small>')
    .replace(/\[([^\]]+)\]\(([A-Za-z0-9_.-]+)\)/g, (_m, t, href) => `<a href="${base}/${href}" target="_blank">${t}</a>`);
  const out: string[] = [];
  let list = false;
  for (const line of md.split("\n")) {
    const bullet = /^\s*[-*] (.*)$/.exec(line);
    if (bullet) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(bullet[1])}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    const h = /^(#{1,4}) (.*)$/.exec(line);
    if (h) out.push(`<h${h[1].length + 2}>${inline(h[2])}</h${h[1].length + 2}>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("\n");
}

/** 🎞 Auto-record: film every day of the game, with a story of what happened and how. */
export function RecordingsModal() {
  const { recordingsOpen, set } = useUI(useShallow((s) => ({ recordingsOpen: s.recordingsOpen, set: s.set })));
  const [st, setSt] = useState<RecorderStatus | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [open, setOpen] = useState<{ run: string; item: Item } | null>(null);
  const [moment, setMoment] = useState<{ run: string; m: Moment } | null>(null);
  const [story, setStory] = useState("");
  const [busy, setBusy] = useState(false);
  const [capText, setCapText] = useState<string | null>(null);  // the cap while it is being typed
  const load = () => {
    api<RecorderStatus>("/api/recorder").then(setSt).catch(() => {});
    api<Run[]>("/api/recordings").then(setRuns).catch(() => {});
  };
  useEffect(() => {
    if (!recordingsOpen) return;
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [recordingsOpen]);
  useEffect(() => {
    if (!open) return;
    fetch(`/recordings/${open.run}/${open.item.story}`).then((r) => r.text()).then(setStory).catch(() => setStory(""));
  }, [open]);
  if (!recordingsOpen) return null;

  const toggle = async (patch: Partial<RecorderStatus>) => {
    setBusy(true);
    try { setSt(await api<RecorderStatus>("/api/recorder", patch)); } finally { setBusy(false); }
  };
  const close = () => { set({ recordingsOpen: false }); setOpen(null); setMoment(null); };
  const meter = st?.storage ? diskMeter(st.storage) : null;
  const newCap = capText === null ? null : parseCapGb(capText);
  const saveCap = async () => {
    if (newCap !== null && meter && newCap !== meter.capGb) await toggle({ retention_gb: newCap });
    setCapText(null);
  };
  const label = (i: Item) => (i.week ? `Week ${i.week}` : `Day ${i.day}`);
  const pick = (run: string, item: Item) => { setMoment(null); setOpen({ run, item }); };
  const pickMoment = (run: string, m: Moment) => { setOpen(null); setMoment({ run, m }); };

  return (
    <div className="modal-bg" onClick={close}>
      <div className="modal recordings" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={close}>✕</button>
        <h2>🎞 Recordings</h2>
        <p className="muted">Auto-record films the game while it runs (both worlds side by side, or the one world, with the
          director camera) and turns every in-game day into a 15-20 second timelapse with its story: what happened, and how
          the chits pulled it off. Big moments (a discovery, an election, a new law, a first) are also filmed close up at
          live speed, captioned. Every 7 days the day clips are joined into a week reel under a minute long. It keeps
          recording after a restart.</p>
        {st && (
          <div className="rec-controls">
            <label className="rec-switch">
              <input type="checkbox" checked={st.enabled} disabled={busy} onChange={(e) => toggle({ enabled: e.target.checked })} />
              <b>Auto-record</b>
            </label>
            <label>Shape
              <select value={st.aspect} disabled={busy} onChange={(e) => toggle({ aspect: e.target.value })}>
                <option value="16:9">16:9 · YouTube / desktop</option>
                <option value="9:16">9:16 · phone / X / TikTok</option>
                <option value="1:1">1:1 · square</option>
              </select>
            </label>
            <label className="rec-switch" title="Film big moments close up, at live speed, with a caption">
              <input type="checkbox" checked={!!st.moments} disabled={busy} onChange={(e) => toggle({ moments: e.target.checked })} />
              Moments
            </label>
            <span className={`rec-state ${st.recording ? "on" : ""}`}>
              {st.recording ? `● recording ${st.world === "split" ? "both worlds" : `World ${st.world}`}` : st.enabled ? "starting…" : "off"}
              {st.frames_waiting > 0 && ` · ${st.frames_waiting} frames for today's clip`}
              {st.filming && ` · 🎬 filming: ${st.filming}`}
              {st.encoding > 0 && " · making a clip…"}
            </span>
          </div>
        )}
        {meter && (
          <div className="rec-disk">
            <div className={`rec-meter ${meter.over ? "over" : ""}`} role="meter" aria-label="Disk used by recordings"
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={meter.percent}>
              <div style={{ width: `${meter.percent}%` }} />
            </div>
            <span><b>{meter.used}</b> used of <b>{meter.cap}</b> · {meter.free} free on the disk</span>
            <label title="When recordings pass this size, the oldest clips are deleted. The written stories are kept.">
              Limit
              <input type="number" min={CAP_MIN_GB} max={CAP_MAX_GB} step={1} disabled={busy}
                className={capText !== null && newCap === null ? "bad" : ""}
                value={capText ?? String(meter.capGb)} onChange={(e) => setCapText(e.target.value)}
                onBlur={saveCap} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
              GB
            </label>
            <small className="muted">Past the limit, the oldest clips are deleted. Stories are kept.
              {capText !== null && newCap === null && ` Type a number from ${CAP_MIN_GB} to ${CAP_MAX_GB}.`}</small>
          </div>
        )}
        {st?.storage?.warning && <small className="err">{st.storage.warning}</small>}
        {st?.last_error && <small className="err">{st.last_error}</small>}

        {runs.length === 0 && <p className="muted">Nothing recorded yet. Switch on auto-record: the first clip appears when the current in-game day ends.</p>}
        {runs.map((r) => (
          <div key={r.run} className="rec-run">
            <h3>{r.current ? "This game" : `Earlier game · ${r.started ? new Date(r.started * 1000).toLocaleString() : r.run.slice(0, 8)}`}
              {r.worlds && <span className="muted"> · {r.worlds.map((w) => `${w.name}${w.brain ? ` (${w.brain})` : ""}`).join(" vs ")}</span>}</h3>
            <div className="rec-items">
              {[...r.weeks, ...r.days].map((i) => (
                <button key={label(i)} className={open?.run === r.run && open.item.story === i.story ? "on" : ""}
                  onClick={() => pick(r.run, i)}>
                  {i.clip ? "▶" : "📜"} {label(i)}
                </button>
              ))}
            </div>
            {!!r.moments?.length && (
              <>
                <h4 className="rec-sub">🎬 Moments <span className="muted">· filmed close up at live speed</span></h4>
                <div className="rec-items">
                  {[...new Set(r.moments.map((m) => Math.floor((m.day - 1) / 7) + 1))].map((wk) => {
                    const cut = r.cuts?.find((c) => c.week === wk);
                    return (
                      <span key={wk}>
                        <button title="The week's best moments, numbered in story order with captions, joined into one video"
                          onClick={() => api(`/api/recordings/${r.run}/cut/${wk}`, {}).then(load).catch(() => {})}>
                          🎬 {cut ? "Remake" : "Make"} week {wk}'s director's cut</button>
                        {cut && <> <a href={`/recordings/${r.run}/${cut.story}`} target="_blank">shot list</a>
                          {cut.video && <> · <a href={`/recordings/${r.run}/${cut.video}`} target="_blank">▶ watch</a></>}</>}
                      </span>
                    );
                  })}
                </div>
                <div className="rec-moments">
                  {[...r.moments].reverse().map((m) => (
                    <button key={m.name} className={moment?.run === r.run && moment.m.name === m.name ? "on" : ""}
                      title={m.caption} onClick={() => pickMoment(r.run, m)}>
                      <small className="muted">Day {m.day}{m.clock ? ` ${m.clock}` : ""} · {m.world_name || `World ${m.world}`}</small>
                      <span>▶ {m.caption}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        ))}
        {moment && (
          <div className="rec-view">
            <video key={moment.m.clip} controls autoPlay src={`/recordings/${moment.run}/${moment.m.clip}`} />
            <p className="rec-caption"><b>{moment.m.caption}</b><br />
              <small className="muted">{moment.m.world_name || `World ${moment.m.world}`} · Day {moment.m.day}
                {moment.m.clock ? `, ${moment.m.clock}` : ""} · {moment.m.kind}
                {moment.m.seconds ? ` · ${Math.round(moment.m.seconds)} s at live speed` : ""}</small></p>
            <a className="muted" href={`/recordings/${moment.run}/${moment.m.clip}`} download>⬇ download the clip</a>
          </div>
        )}
        {open && (
          <div className="rec-view">
            {open.item.clip
              ? <video key={open.item.clip} controls autoPlay src={`/recordings/${open.run}/${open.item.clip}`} />
              : <p className="muted">No video for this one (auto-record was off or had no frames), just the story.</p>}
            {open.item.clip && <a className="muted" href={`/recordings/${open.run}/${open.item.clip}`} download>⬇ download the clip</a>}
            <div className="rec-story" dangerouslySetInnerHTML={{ __html: renderMarkdown(story, `/recordings/${open.run}`) }} />
          </div>
        )}
      </div>
    </div>
  );
}
