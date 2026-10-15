import { useShallow } from "zustand/react/shallow";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAnchor } from "./popover";
import { api, errorText } from "../net/socket";
import { localStorageSet, notifyError, useUI, worlds } from "../state/store";
import { lookButton } from "./look";
import { themeFor } from "../theme";
import { BrandMark } from "./BrandMark";
import { SkipControl } from "./SkipControl";
import { topBarChips, type Thinking } from "./watch";
import { mindDown, mindLabel } from "./mindState";

const SEASON_ICON: Record<string, string> = { spring: "🌱", summer: "☀️", autumn: "🍂", winter: "❄️" };
const WEATHER_ICON: Record<string, string> = { rain: "🌧", storm: "⛈", drought: "🔥", snow: "❄" };
const SPEED_LABEL: Record<number, string> = { 1: "1×", 2: "2×", 5: "5×", 10: "10×", 25: "25×", 100: "MAX" };

/** ⋯ The bar's less-used buttons, below 1560px: a menu of them with their labels (it hangs from the button, outside
 *  the bar, which scrolls sideways and would clip it). Closes on a choice, a click elsewhere or Escape. */
function MoreMenu({ children, dot }: { children: React.ReactNode; dot: boolean }) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const r = useAnchor(open, () => setOpen(false), btn, menu);
  return (<>
    <button ref={btn} className={`icon-btn tb-more ${open ? "on" : ""}`} title="More: night, look, director, replay, god mode, recordings, restart" onClick={() => setOpen(!open)}>
      ⋯{dot && <span className="rec-dot" title="recording" />}
    </button>
    {r && createPortal(<div ref={menu} className="tb-menu" style={{ top: r.bottom + 8, right: Math.max(8, window.innerWidth - r.right) }}
      onClick={(e) => { if ((e.target as HTMLElement).closest("button")) setOpen(false); }}>{children}</div>, document.body)}
  </>);
}

export function TopBar() {
  const theme = useUI((s) => s.theme);
  const { view, control, brains, conn, worlds: metas, set, nightMode, director, recording } = useUI(useShallow((s) => ({ view: s.view, control: s.control, brains: s.brains, conn: s.conn, worlds: s.worlds, set: s.set, nightMode: s.nightMode, director: s.director, recording: s.recording })));
  useEffect(() => {  // 🎞 shows a red dot while auto-record is filming
    const poll = () => api<{ recording: boolean }>("/api/recorder").then((r) => set({ recording: r.recording })).catch(() => {});
    poll();
    const t = setInterval(poll, 15000);
    return () => clearInterval(t);
  }, []);
  const [thinking, setThinking] = useState<Record<string, Thinking>>({});
  useEffect(() => {  // ⚙ who is thinking for each world: the bar says so when one runs on instinct
    const poll = () => api<{ who_thinks?: Record<string, Thinking> }>("/api/health").then((h) => setThinking(h.who_thinks ?? {})).catch(() => {});
    poll();
    const t = setInterval(poll, 10000);
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
  const look = lookButton(theme, control?.contract);
  const shownIds = view === "split" ? metas.map((w) => w.id) : [primary];
  const nameOf = (id: string) => metas.find((m) => m.id === id)?.name ?? id;
  const onInstinct = topBarChips(shownIds, thinking, brains);  // (none for an outage the 🧠 chip already tells)
  const restart = async () => {
    const m = worlds[metas[0]?.id]?.meta;
    if (!m || !confirm("Restart this game from day 1? Same island, same mode, same models. The current history is erased.")) return;
    await api("/api/reset", { seed: m.seed, size: m.size });
    set({ selected: null, follow: false });
  };
  const extras = (cls: string) => (<>
    <button className={cls} title={`Night: ${nightMode} (click to change)`}
      onClick={() => { const n = nextNight[nightMode]; set({ nightMode: n }); localStorageSet("night", n); }}>
      {nightMode === "normal" ? "🌙" : nightMode === "soft" ? "🌗" : "☀️"}<small>{nightMode}</small>
    </button>
    <button className={`${cls} ${theme === "norse" ? "on" : ""}`} title={look.title} disabled={look.disabled}
      onClick={() => api("/api/theme", { theme: look.next }).catch((e) => notifyError(errorText(e)))}>
      {look.glyph}<small>{look.label}</small>
    </button>
    <button className={`${cls} ${director ? "on" : ""}`} title="Director: the camera cuts to discoveries, births, storms and builds by itself (drag or click to take over)"
      onClick={() => { set({ director: !director }); localStorageSet("director", director ? "0" : "1"); }}>🎬<small>director</small></button>
    <button className={cls} title="Replay: scrub back through the last week (opens the replay viewer)"
      onClick={() => window.open(`/replay.html?src=${encodeURIComponent("/api/replay/export?days=7")}`, "_blank")}>▶<small>replay</small></button>
    {control?.contract !== "experiment" && (
      <button className={cls} title="God mode: drop anything, meddle, save and rewind" onClick={() => set({ godOpen: true })}>🪄<small>god</small></button>
    )}
    <button className={`${cls} ${recording ? "rec-on" : ""}`} title="Recordings: auto-record every day of the game as a clip with its story"
      onClick={() => set({ recordingsOpen: true })}>🎞<small>{recording ? "● rec" : "record"}</small></button>
    <button className={cls} title="Restart this game from day 1 (same island, mode and models)" onClick={restart}>↺<small>restart</small></button>
  </>);

  return (
    <header className="topbar">
      <div className="brand">
        <BrandMark />
        <span className="brand-text">{themeFor(theme).brand}</span>
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
      {onInstinct.length > 0 && (
        <span className="instinct-chip" title={onInstinct.map((x) => (shownIds.length > 1 ? `${nameOf(x.id)}: ` : "") + x.title).join("\n")}>
          {onInstinct.length === shownIds.length
            ? <>⚙ <span className="ic-long">running on </span>instinct</>  /* (short below 1440px) */
            : `⚙ ${onInstinct.map((x) => nameOf(x.id)).join(", ")} on instinct`}
        </span>
      )}

      <div className="seg speed">
        <button className={control?.paused ? "on" : ""} onClick={() => setSpeed(0)} title="Pause">❚❚</button>
        {[1, 2, 5, 10, 25, 100].map((s) => (
          <button key={s} className={!control?.paused && control?.speed === s ? "on" : ""} onClick={() => setSpeed(s)}>{SPEED_LABEL[s]}</button>
        ))}
      </div>
      {control?.contract !== "experiment" && <SkipControl />}
      {brainsInUse && control?.contract !== "experiment" && (
        <button className={`pace-btn ${control?.pace_to_brain ? "on" : ""}`}
          title={control?.pace_to_brain
            ? "Wait for models: ON. The world slows down while the models think, so every decision is theirs (fair model tests). Click to let instinct fill gaps instead."
            : "Wait for models: OFF. The world runs at full speed and instinct covers while the models think. Click to make the world wait for them."}
          onClick={() => api("/api/control", { pace_to_brain: !control?.pace_to_brain }).then((c) => set({ control: c }))}>
          {control?.pace_to_brain ? (control?.waiting_on_brain ? "⏳ waiting for models" : "⏳ wait for models") : "🏃 full speed"}
        </button>
      )}

      {control?.contract === "experiment" && (
        <button className="badge exp" title="Experiment run: every decision is the model's own, settings are locked. Click to end the experiment and keep playing these worlds."
          onClick={() => {
            if (window.confirm("End the experiment and keep playing these worlds? Models can be swapped again and instinct covers a slow model. It can't be made an experiment again (that starts with a new game)."))
              api("/api/experiment/end", {}).then((c) => set({ control: c }));
          }}>🧪 experiment</button>
      )}
      {control?.sandbox_modified && <span className="badge mod" title="Someone reached into this world (god mode or a rewind). Great for stories, not for comparisons.">🪄<span className="mod-text"> modified</span></span>}
      <div className="spacer" />

      {/* the less-used buttons: in the bar on a wide screen, behind ⋯ below 1560px (styles.css) */}
      {extras("icon-btn tb-extra")}
      <MoreMenu dot={recording}>{extras("icon-btn")}</MoreMenu>
      {control?.contract !== "experiment" && (
        <button className="icon-btn tb-main" title="Saves: save this game now, load a save, or move one to another computer as a file"
          onClick={() => set({ savesOpen: true })}>💾<small>saves</small></button>
      )}
      <button className="icon-btn tb-main" title="Start a new game: choose the mode, island and models" onClick={() => set({ newWorldOpen: true })}>⟲<small>new</small></button>

      <button className="brain-pill" onClick={() => set({ brainsOpen: true })} title="Choose the brains that drive each world">
        {metas.map((w) => {
          const b = brains[w.id];
          return (
            <span key={w.id} className={`bp ${b && (!b.healthy || mindDown(b)) ? "bad" : ""}`}>
              <i className={`dot ${w.culture}`} />
              <b>{mindLabel(b)}</b>
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
