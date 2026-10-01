import { useEffect, useRef, useState } from "react";
import { Director, type DirectorAgent } from "../render/director";
import { WorldView } from "../render/WorldView";
import { api } from "../net/socket";
import { localStorageSet, useUI, worlds } from "../state/store";

export const views: Record<string, WorldView> = {};
export const cameras: Record<string, { x: number; y: number; zoom: number; w: number; h: number }> = {};
(window as any).__chits = { views, cameras, worlds };

export function WorldCanvas({ worldId, dayCard = true, controls = true }: { worldId: string; dayCard?: boolean; controls?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const selected = useUI((s) => s.selected);
  const follow = useUI((s) => s.follow);
  const focus = useUI((s) => s.focus);
  const nightMode = useUI((s) => s.nightMode);
  const meta = useUI((s) => s.worlds.find((w) => w.id === worldId));
  const director = useUI((s) => s.director);
  const godTool = useUI((s) => s.godTool);
  const [caption, setCaption] = useState("");
  useUI((s) => s.tick);
  const clock = worlds[worldId]?.clock;
  const day = clock?.day ?? 0;
  const [card, setCard] = useState("");
  const firstDay = useRef(0);
  useEffect(() => {
    if (!day || !clock || !dayCard) return;
    if (!firstDay.current) { firstDay.current = day; return; } // not on page load, only when a day turns
    setCard(`Day ${day} · ${clock.season[0].toUpperCase()}${clock.season.slice(1)}`);
    const t = setTimeout(() => setCard(""), 2500);
    return () => clearTimeout(t);
  }, [day, dayCard]);

  useEffect(() => {
    const v = new WorldView();
    views[worldId] = v;
    v.onSelect = (sel) => {
      useUI.getState().set({ selected: sel ? { world: worldId, id: sel.id } : null, follow: false });
    };
    v.onCamera = (c) => { cameras[worldId] = c; };
    v.onManual = () => {
      if (useUI.getState().director) { useUI.getState().set({ director: false }); localStorageSet("director", "0"); }
    };
    v.nightMode = useUI.getState().nightMode;
    v.setWorld(worlds[worldId]);
    v.mount(ref.current!);
    return () => { v.destroy(); delete views[worldId]; };
  }, [worldId]);

  useEffect(() => {
    const v = views[worldId];
    if (!v) return;
    if (selected && selected.world === worldId) {
      v.selection = { kind: selected.id.startsWith("a") ? "agent" : "structure", id: selected.id };
    } else v.selection = null;
    v.follow = follow && !!selected && selected.world === worldId;
  }, [selected, follow, worldId]);

  useEffect(() => {
    if (views[worldId]) views[worldId].nightMode = nightMode;
  }, [nightMode, worldId]);

  useEffect(() => {
    const v = views[worldId];
    if (!v || !focus || focus.world !== worldId) return;
    v.flyTo(focus.x, focus.y, 3);
    // flying somewhere shouldn't cancel an explicit follow of the selected chit
    v.follow = useUI.getState().follow && selected?.world === worldId;
  }, [focus, worldId]);

  // 🪄 god mode: an armed tool turns the next click on the map into a miracle
  useEffect(() => {
    const v = views[worldId];
    if (!v) return;
    v.onGodClick = godTool ? (x, y) => {
      const t = useUI.getState().godTool;
      if (!t) return;
      api(`/api/worlds/${worldId}/god`, { action: t.action, item: t.item, x, y, qty: t.action === "drop" ? 1 : undefined })
        .catch((e) => alert(String(e.message || e)));
      useUI.getState().set({ godTool: null });
    } : null;
  }, [godTool, worldId]);

  // 🎬 director: feed it this world's events and follow its shots
  useEffect(() => {
    if (!director) { setCaption(""); return; }
    const d = new Director();
    const wd = worlds[worldId];
    const off = wd.listen({
      events: (evs) => {
        const now = performance.now();
        for (const e of evs) d.offer({ seq: e.seq, tick: e.tick, kind: e.kind, importance: e.importance, x: e.x, y: e.y, text: e.text, world: worldId }, now);
      },
    });
    let last: any = null, raf = 0;
    const loop = () => {
      const now = performance.now();
      const agents: DirectorAgent[] = [...worlds[worldId].agents.values()].map((a: any) => ({ id: a.id, x: a.x, y: a.y, act: a.act || "" }));
      const shot = d.current(now, worldId, agents);
      if (shot && shot !== last) {
        last = shot;
        views[worldId]?.flyTo(shot.x, shot.y, shot.zoom);
        setCaption(shot.caption);
      } else if (!shot && last) { last = null; setCaption(""); }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { off(); cancelAnimationFrame(raf); setCaption(""); };
  }, [director, worldId]);

  return (
    <div className="world-canvas" ref={ref}>
      {director && caption && <div className="caption">{caption}</div>}
      {card && <div key={card} className="day-card short">{card}</div>}
      {meta && (
        <div className={`world-tag ${meta.culture}`}>
          <b>{meta.name}</b>
          <span>{meta.culture === "direct" ? "can talk, teach & write" : "learns only by watching"}</span>
        </div>
      )}
      {controls && (
        <div className="zoom-ctl">
          <button title="Zoom in" onClick={() => views[worldId]?.zoomBy(1.5)}>＋</button>
          <button title="Zoom out" onClick={() => views[worldId]?.zoomBy(1 / 1.5)}>－</button>
          <button title="Show the whole island" onClick={() => views[worldId]?.showAll()}>⤢</button>
        </div>
      )}
    </div>
  );
}
