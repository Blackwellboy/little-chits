import { useShallow } from "zustand/react/shallow";
import { useEffect } from "react";
import { api } from "../net/socket";
import { localStorageSet, useUI, worlds } from "../state/store";

const SEASON_ICON: Record<string, string> = { spring: "🌱", summer: "☀️", autumn: "🍂", winter: "❄️" };
const WEATHER_ICON: Record<string, string> = { rain: "🌧", storm: "⛈", drought: "🔥", snow: "❄" };
const SPEED_LABEL: Record<number, string> = { 1: "1×", 2: "2×", 5: "5×", 10: "10×", 25: "25×", 100: "MAX" };

export function TopBar() {
  const { view, control, brains, conn, worlds: metas, set, nightMode, director, recording } = useUI(useShallow((s) => ({ view: s.view, control: s.control, brains: s.brains, conn: s.conn, worlds: s.worlds, set: s.set, nightMode: s.nightMode, director: s.director, recording: s.recording })));
  useEffect(() => {  // 🎞 shows a red dot while auto-record is filming
    const poll = () => api<{ recording: boolean }>("/api/recorder").then((r) => set({ recording: r.recording })).catch(() => {});
    poll();
    const t = setInterval(poll, 15000);
    return () => clearInterval(t);
  }, []);
  const nextNight = { normal: "soft", soft: "off", off: "normal" } as const;
  useUI((s) => s.tick);
  const primary = view === "B" ? "B" : "A";
  const clock = worlds[primary]?.clock;
  const hh = clock ? Math.floor(clock.hour) : 0;
  const mm = clock ? Math.floor((clock.hour - hh) * 60) : 0;
  const isNight = clock?.night;
  const setSpeed = (speed: number) => api("/api/control", { speed }).then((c) => set({ control: c }));
  const setView = (v: "A" | "B" | "split") => { set({ view: v }); localStorageSet("view", v); };
  const brainsInUse = metas.some((w) => brains[w.id] && brains[w.id].id !== "instinct");
  const restart = async () => {
    const m = worlds[metas[0]?.id]?.meta;
    if (!m || !confirm("Restart this game from day 1? Same island, same mode, same models. The current history is erased.")) return;
    await api("/api/reset", { seed: m.seed, size: m.size });
    set({ selected: null, follow: false });
  };

  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo">●</span>
        <span className="brand-text">LITTLE CHITS</span>
      </div>

      {metas.length > 1 && (
        <div className="seg">
          {metas.map((w) => (
            <button key={w.id} className={view === w.id ? "on" : ""} onClick={() => setView(w.id as any)} title={w.label}>
              <span className={`dot ${w.culture}`} />{w.name}
            </button>
          ))}
          <button className={view === "split" ? "on" : ""} onClick={() => setView("split")} title="Side by side">◧ Split</button>
        </div>
      )}

      <div className="clock" title={`Year ${clock?.year ?? 1}`}>
        <span className="sky">{isNight ? "🌙" : "☀️"}</span>
        <b>Day {clock?.day ?? "–"}</b>
        <span className="muted">{SEASON_ICON[clock?.season ?? "spring"]} {clock?.season}</span>
        <span className="time">{String(hh).padStart(2, "0")}:{String(mm).padStart(2, "0")}</span>
        {clock?.weather && clock.weather !== "clear" && <span className="wx" title={clock.weather}>{WEATHER_ICON[clock.weather] ?? ""}</span>}
        {clock?.era && <span className="era" title="How far this world has come">{clock.era}</span>}
        <div className="daybar"><i style={{ width: `${((clock?.hour ?? 0) / 24) * 100}%` }} /></div>
      </div>

      <div className="seg speed">
        <button className={control?.paused ? "on" : ""} onClick={() => setSpeed(0)} title="Pause">❚❚</button>
        {[1, 2, 5, 10, 25, 100].map((s) => (
          <button key={s} className={!control?.paused && control?.speed === s ? "on" : ""} onClick={() => setSpeed(s)}>{SPEED_LABEL[s]}</button>
        ))}
      </div>
      {brainsInUse && control?.contract !== "experiment" && (
        <button className={`pace-btn ${control?.pace_to_brain ? "on" : ""}`}
          title={control?.pace_to_brain
            ? "Wait for models: ON. The world slows down while the models think, so every decision is theirs (fair model tests). Click to let instinct fill gaps instead."
            : "Wait for models: OFF. The world runs at full speed and instinct covers while the models think. Click to make the world wait for them."}
          onClick={() => api("/api/control", { pace_to_brain: !control?.pace_to_brain }).then((c) => set({ control: c }))}>
          {control?.pace_to_brain ? (control?.waiting_on_brain ? "⏳ waiting for models" : "⏳ wait for models") : "🏃 full speed"}
        </button>
      )}

      {control?.contract === "experiment" && <span className="badge exp" title="Experiment run: every decision is the model's own, settings are locked">🧪 experiment</span>}
      {control?.sandbox_modified && <span className="badge mod" title="Someone reached into this world (god mode or a rewind). Great for stories, not for comparisons.">🪄<span className="mod-text"> modified</span></span>}
      <div className="spacer" />

      <button className="icon-btn" title={`Night: ${nightMode} (click to change)`}
        onClick={() => { const n = nextNight[nightMode]; set({ nightMode: n }); localStorageSet("night", n); }}>
        {nightMode === "normal" ? "🌙" : nightMode === "soft" ? "🌗" : "☀️"}<small>{nightMode}</small>
      </button>
      <button className={`icon-btn ${director ? "on" : ""}`} title="Director: the camera cuts to discoveries, births, storms and builds by itself (drag or click to take over)"
        onClick={() => { set({ director: !director }); localStorageSet("director", director ? "0" : "1"); }}>🎬<small>director</small></button>
      <button className="icon-btn" title="Replay: scrub back through the last week (opens the replay viewer)"
        onClick={() => window.open(`/replay.html?src=${encodeURIComponent("/api/replay/export?days=7")}`, "_blank")}>▶<small>replay</small></button>
      {control?.contract !== "experiment" && (
        <button className="icon-btn" title="God mode: drop anything, meddle, save and rewind" onClick={() => set({ godOpen: true })}>🪄<small>god</small></button>
      )}
      <button className={`icon-btn ${recording ? "rec-on" : ""}`} title="Recordings: auto-record every day of the game as a clip with its story"
        onClick={() => set({ recordingsOpen: true })}>🎞<small>{recording ? "● rec" : "record"}</small></button>
      <button className="icon-btn" title="Restart this game from day 1 (same island, mode and models)" onClick={restart}>↺<small>restart</small></button>
      <button className="icon-btn" title="Start a new game: choose the mode, island and models" onClick={() => set({ newWorldOpen: true })}>⟲<small>new</small></button>

      <button className="brain-pill" onClick={() => set({ brainsOpen: true })} title="Choose the brains that drive each world">
        {metas.map((w) => {
          const b = brains[w.id];
          return (
            <span key={w.id} className={`bp ${b && !b.healthy ? "bad" : ""}`}>
              <i className={`dot ${w.culture}`} />
              <b>{b?.label ?? "…"}</b>
              {b && b.id !== "instinct" && <em>{b.thinking > 0 ? `💭${b.thinking}` : ""} {b.tok_s ? `${Math.round(b.tok_s)} t/s` : ""}</em>}
            </span>
          );
        })}
        <span className="gear">⚙</span>
      </button>
      <span className={`conn ${conn}`} title={conn}>{conn === "live" ? "LIVE" : conn === "connecting" ? "…" : conn.toUpperCase()}</span>
    </header>
  );
}
