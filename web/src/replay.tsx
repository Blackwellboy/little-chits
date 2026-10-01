// The standalone replay viewer (T33): open a bundle exported from /api/replay/export and scrub through it.
// It needs no server API: ?src=<url of a bundle>, or drag and drop the file onto the page.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { WorldView } from "./render/WorldView";
import { WorldData } from "./state/world";
import type { Clock } from "./types";
import "./styles.css";

type Keyframe = { t: number; a: [string, number, number, string][]; s: any[] | null };
type BundleWorld = {
  meta: any; brain: string; terrain: { size: number; seed: number; tiles: string; res_kind?: string; res_amt?: string };
  keyframes: Keyframe[]; events: any[]; names: Record<string, string>; hues?: Record<string, number>;
};
type Bundle = { version: number; exported: string; mode: string; worlds: Record<string, BundleWorld> };

const TPD = 240;
const SEASONS = ["spring", "summer", "autumn", "winter"] as const;
const SPEEDS = [1, 2, 4, 8, 16, 32];

export function clockAt(t: number): Clock {
  const day = Math.floor(t / TPD);
  const hour = ((t % TPD) / TPD) * 24;
  const daylight = Math.max(0, Math.min(1, 0.5 + 0.75 * Math.cos(((hour - 13) / 24) * 2 * Math.PI)));
  return {
    tick: Math.floor(t), day: day + 1, year: Math.floor(day / 12) + 1, season: SEASONS[Math.floor(day / 3) % 4],
    hour, daylight, night: hour < 5.5 || hour >= 20.5, day_of_season: (day % 3) + 1, weather: "clear",
  };
}

function zeros(n: number): string {
  let s = "";
  const chunk = String.fromCharCode(...new Array(Math.min(n, 4096)).fill(0));
  for (let i = 0; i < n; i += 4096) s += i + 4096 <= n ? chunk : chunk.slice(0, n - i);
  return btoa(s);
}

/** Drives one world's WorldData from the bundle, keyframe by keyframe. */
class Track {
  data: WorldData;
  private lastI = -2;
  private lastS = -2;
  constructor(public id: string, public w: BundleWorld) { this.data = new WorldData(id); }

  private brief(row: [string, number, number, string]) {
    const [id, x, y, act] = row;
    return { id, name: this.w.names[id] || id, x, y, hue: this.w.hues?.[id] ?? 30, act, emote: "", say: "", think: false,
      carry: null, tool: null, child: false, basket: false, hp: 100, hunger: 80, brain: "", src: "instinct" as const };
  }

  seek(t: number) {
    const kf = this.w.keyframes;
    if (!kf.length) return;
    let i = 0;
    while (i + 1 < kf.length && kf[i + 1].t <= t) i++;
    let j = i;
    while (j > 0 && !kf[j].s) j--;
    if (!this.data.ready) {
      const n = this.w.terrain.size * this.w.terrain.size;
      this.data.snapshot({
        world: { ...this.w.meta, size: this.w.terrain.size, seed: this.w.terrain.seed },
        tiles: this.w.terrain.tiles, res_kind: this.w.terrain.res_kind || zeros(n), res_amt: this.w.terrain.res_amt || zeros(n),
        trails: [], roads: [], structures: kf[j].s || [], agents: kf[i].a.map((r) => this.brief(r)), tablets: [],
        events: [], clock: clockAt(kf[i].t), stats: null, history: [], signs: [], ground: [], animals: [],
      });
      this.lastS = j;
      this.lastI = i;
    }
    if (i !== this.lastI || j !== this.lastS) {
      // a new replay day only changes the buildings: send them as a frame instead of rebuilding the island
      // (a full snapshot rebuilt every chunk and sprite each replay day)
      const s = j !== this.lastS ? kf[j].s || [] : [];
      const ids = new Set(s.map((x: any) => x.id));
      const removed = j !== this.lastS ? [...this.data.structures.keys()].filter((id) => !ids.has(id)) : [];
      const from = this.lastI >= 0 ? kf[this.lastI].t : -1;
      const evs = i > this.lastI ? this.w.events.filter((e) => e.tick > from && e.tick <= kf[i].t) : [];
      this.data.frame({ world: this.id, clock: clockAt(kf[i].t), agents: kf[i].a.map((r) => this.brief(r)), res: [],
        structures: s, removed, paths: [], events: evs.slice(-20), tablets: null, stats: null });
      this.lastI = i;
      this.lastS = j;
    }
    this.data.clock = clockAt(t);
  }
}

function Pane({ track }: { track: Track }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const v = new WorldView();
    v.setWorld(track.data, { villages: false }); // the live game's village names don't belong here
    v.mount(ref.current!);
    return () => v.destroy();
  }, [track]);
  return (
    <div className="pane">
      <div className="world-canvas" ref={ref} />
      <div className="rp-tag"><b>{track.w.meta.name}</b> · {track.w.brain}</div>
    </div>
  );
}

function Viewer({ bundle }: { bundle: Bundle }) {
  const tracks = useMemo(() => Object.entries(bundle.worlds).map(([id, w]) => new Track(id, w)), [bundle]);
  const all = tracks.flatMap((t) => t.w.keyframes.map((k) => k.t));
  const t0 = Math.min(...all), t1 = Math.max(...all);
  const [t, setT] = useState(t0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(4);
  const [view, setView] = useState<string>(tracks.length > 1 ? "split" : tracks[0]?.id);
  const tRef = useRef(t0);
  tRef.current = t;
  useEffect(() => { for (const tr of tracks) tr.seek(t); }, [t, tracks]);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now(), raf = 0;
    const loop = () => {
      const now = performance.now();
      const next = Math.min(t1, tRef.current + ((now - last) / 1000) * 12 * speed);
      last = now;
      setT(next);
      if (next >= t1) setPlaying(false);
      else raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, t1]);
  const shown = view === "split" ? tracks : tracks.filter((x) => x.id === view);
  const marks = tracks.flatMap((tr) => tr.w.events.filter((e) => e.importance >= 4).map((e) => ({ ...e, world: tr.id })));
  const recent = marks.filter((e) => e.tick <= t).slice(-4).reverse();
  const c = clockAt(t);
  return (
    <div className="app rp">
      <div className={`stage ${shown.length > 1 ? "split" : ""}`}>{shown.map((tr) => <Pane key={tr.id} track={tr} />)}</div>
      <div className="rp-top">
        <b className="rp-title">LITTLE CHITS · replay</b>
        <span>Day {c.day} · {c.season} · {String(Math.floor(c.hour)).padStart(2, "0")}:00</span>
        {tracks.length > 1 && (
          <span className="seg">
            {tracks.map((tr) => <button key={tr.id} className={view === tr.id ? "on" : ""} onClick={() => setView(tr.id)}>World {tr.id}</button>)}
            <button className={view === "split" ? "on" : ""} onClick={() => setView("split")}>◧ Split</button>
          </span>
        )}
      </div>
      <div className="rp-events">{recent.map((e) => <div key={`${e.world}-${e.seq}`}><small>World {e.world} · day {Math.floor(e.tick / TPD) + 1}</small> {e.text}</div>)}</div>
      <div className="rp-bar">
        <button onClick={() => { if (t >= t1) setT(t0); setPlaying(!playing); }}>{playing ? "❚❚" : "▶"}</button>
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>{SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}</select>
        <div className="rp-track">
          {marks.map((e) => (
            <i key={`${e.world}-${e.seq}`} title={e.text} className={`w${e.world}`} style={{ left: `${((e.tick - t0) / Math.max(1, t1 - t0)) * 100}%` }}
              onClick={() => setT(e.tick)} />
          ))}
          <input type="range" min={t0} max={t1} step={1} value={t} onChange={(e) => { setPlaying(false); setT(Number(e.target.value)); }} />
        </div>
      </div>
    </div>
  );
}

function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    const src = new URLSearchParams(location.search).get("src");
    if (src) fetch(src).then((r) => r.json()).then(setBundle).catch((e) => setErr(`Couldn't load ${src}: ${e}`));
  }, []);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) f.text().then((s) => setBundle(JSON.parse(s))).catch((x) => setErr(String(x)));
  };
  if (bundle) return <Viewer bundle={bundle} />;
  return (
    <div className="rp-drop" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
      <div className="boot-card">
        <h1>LITTLE CHITS · replay</h1>
        <p>{err || "Drop a replay file here (from ⬇ in the Stats tab), or open this page with ?src=<url>."}</p>
        <input type="file" accept=".json,application/json" onChange={(e) => e.target.files?.[0]?.text().then((s) => setBundle(JSON.parse(s)))} />
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
