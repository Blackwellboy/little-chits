import { useEffect, useState } from "react";
import { api } from "./net/socket";
import { useUI, worlds } from "./state/store";
import { parseMomentParams, parseRecordParams, stageSize, type MomentParams } from "./ui/recordLayout";
import { BrainsModal } from "./ui/BrainsModal";
import { GodBanner, GodModal } from "./ui/GodModal";
import { RecordingsModal } from "./ui/RecordingsModal";
import { Welcome } from "./ui/Welcome";
import { NewWorldModal } from "./ui/NewWorldModal";
import { Inspector } from "./ui/Inspector";
import { Minimap, Toasts, Banner } from "./ui/Overlays";
import { SidePanel } from "./ui/SidePanel";
import { TopBar } from "./ui/TopBar";
import { views, WorldCanvas } from "./ui/WorldCanvas";

const REC = parseRecordParams(window.location.search);
// a moment close-up films one world where something big happened: the camera holds still, no director
const MOMENT = REC.record && REC.world !== "split" ? parseMomentParams(window.location.search) : null;
if (REC.record) {
  useUI.getState().set({ view: REC.world, director: MOMENT ? false : REC.director });
  if (REC.speed) api("/api/control", { speed: REC.speed }).catch(() => {});
  (window as any).__chits.moment = MOMENT; // the recorder checks this build can aim the camera itself
}

function useViewport() {
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const on = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vp;
}

/** Record mode: watermark and a title card at every new in-game day. */
function RecordOverlay({ cards = true }: { cards?: boolean }) {
  useUI((s) => s.tick);
  const view = useUI((s) => s.view);
  const brains = useUI((s) => s.brains);
  const wid = view === "split" ? "A" : view;
  const clock = worlds[wid]?.clock;
  const day = clock?.day ?? 0;
  const [card, setCard] = useState<{ day: number; season: string } | null>(null);
  useEffect(() => {
    if (!day || !clock || !cards) return;
    setCard({ day, season: clock.season });
    const t = setTimeout(() => setCard(null), 3000);
    return () => clearTimeout(t);
  }, [day]);
  const label = view === "split" ? "Worlds A & B" : `World ${wid} · ${brains[wid]?.label || "Instinct"}`;
  return (
    <>
      <div className="watermark">LITTLE CHITS · {label}{day ? ` · Day ${day}` : ""}</div>
      {card && <div className="day-card">Day {card.day} · {card.season[0].toUpperCase() + card.season.slice(1)}</div>}
    </>
  );
}

/** Moment close-up: hold the camera on the spot (the first build of the island recenters it, so keep
 * re-aiming), and caption the shot with the event, flagged as live speed. */
function MomentOverlay({ m, worldId }: { m: MomentParams; worldId: string }) {
  useEffect(() => {
    const aim = () => views[worldId]?.jumpTo(m.x, m.y, m.zoom);
    aim();
    const t = setInterval(aim, 250);
    return () => clearInterval(t);
  }, [m, worldId]);
  return (
    <>
      <div className="moment-live">● LIVE · real time</div>
      {m.caption && (
        <div className="moment-caption">
          {m.label && <small>🎬 {m.label}</small>}
          <span>{m.caption}</span>
        </div>
      )}
    </>
  );
}

export default function App() {
  const vp = useViewport();
  const view = useUI((s) => s.view);
  const metas = useUI((s) => s.worlds);
  const conn = useUI((s) => s.conn);
  const ids = view === "split" ? metas.map((m) => m.id) : [view];
  if (REC.record) {
    const box = stageSize(REC.aspect, vp.w, vp.h);
    return (
      <div className={`app record ${REC.captions ? "" : "no-captions"}`}>
        <div className="record-box" style={{ width: box.width, height: box.height, left: box.left, top: box.top }}>
          <div className={`stage ${view === "split" ? "split" : ""}`}>
            {ids.map((id) => (
              <div key={id} className="pane"><WorldCanvas worldId={id} dayCard={false} controls={false} /></div>
            ))}
          </div>
          <div className="vignette soft" />
          <RecordOverlay cards={!MOMENT} />
          {MOMENT &&<MomentOverlay m={MOMENT} worldId={REC.world} />}
        </div>
      </div>
    );
  }
  return (
    <div className="app">
      <div className={`stage ${view === "split" ? "split" : ""}`}>
        {ids.map((id) => (
          <div key={id} className="pane">
            <WorldCanvas worldId={id} />
            <Minimap worldId={id} />
          </div>
        ))}
      </div>
      <div className="vignette" />
      <TopBar />
      <SidePanel />
      <Inspector />
      <Toasts />
      <Banner />
      <BrainsModal />
      <NewWorldModal />
      <GodModal />
      <GodBanner />
      <RecordingsModal />
      <Welcome />
      {!metas.length && (
        <div className="boot">
          <div className="boot-card">
            <div className="boot-chit">●</div>
            <h1>LITTLE CHITS</h1>
            <p>{conn === "offline" ? "Can't reach the world server. Is it running?" : "Waking the world…"}</p>
          </div>
        </div>
      )}
    </div>
  );
}
