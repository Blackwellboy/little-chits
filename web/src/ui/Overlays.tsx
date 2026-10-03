import { useEffect, useRef, useState } from "react";
import { pixelCanvas } from "../render/art";
import { milestoneOf } from "../state/milestones";
import { useUI, worlds } from "../state/store";
import { theme } from "../theme";
import { cameras, views } from "./WorldCanvas";
import { bannerDriver, type Shown } from "./banner";

const ICON: Record<string, string> = { error: "⚠", discovery: "✦", first: "★", built: "🏠", birth: "🍼", death: "🕯", legacy: "📜", learned: "💡" };
const worldLabel = (id: string) => (id === "A" ? "World A" : "World B");

export function Toasts() {
  const toasts = useUI((s) => s.toasts);
  const set = useUI((s) => s.set);
  useEffect(() => {
    if (!toasts.length) return;
    const t = setTimeout(() => set({ toasts: useUI.getState().toasts.slice(1) }), 6500);
    return () => clearTimeout(t);
  }, [toasts]);
  return (
    <div className="toasts">
      {toasts.map((t) => {
        const ms = milestoneOf(t);
        return (
          <div key={t.key} className={`toast k-${t.kind}${ms ? " milestone" : ""}`} onClick={() => {
            if (t.x != null) set({ focus: { world: t.world, x: t.x + 0.5, y: (t.y ?? 0) + 0.5, t: Date.now() } });
            if (t.actor && worlds[t.world]?.agents.has(t.actor)) set({ selected: { world: t.world, id: t.actor } });
          }}>
            <span className="ico">{ms?.icon ?? ICON[t.kind] ?? "✦"}</span>
            <div><small>{t.kind === "error" ? "That didn't work" : `${worldLabel(t.world)} · day ${Math.floor(t.tick / 240) + 1}${ms ? ` · ${ms.label}` : ""}`}</small><p>{t.text}</p></div>
          </div>
        );
      })}
    </div>
  );
}

/** A new era, a village becoming a town or city, or the storyteller's news fills the screen for a few seconds: the
 *  moments a viewer (and the recorder) should not miss. An era toast used to slip by in the corner. */
export function Banner() {
  const toasts = useUI((s) => s.toasts);
  const [shown, setShown] = useState<Shown | null>(null);
  const driver = useRef<ReturnType<typeof bannerDriver> | null>(null);
  if (!driver.current) driver.current = bannerDriver(setShown);
  useEffect(() => { driver.current!.update(toasts); }, [toasts]);  // (no cleanup: the banner's timer is its own)
  useEffect(() => () => { driver.current!.stop(); setShown(null); }, []);  // (never left up with no timer)
  if (!shown) return null;
  return (
    <div key={shown.key} className={`banner k-${shown.kind}`} onClick={() => setShown(null)}>
      <small>{worldLabel(shown.world)} · {shown.label}</small>
      <h1>{shown.icon} {shown.text}</h1>
    </div>
  );
}

export function Minimap({ worldId }: { worldId: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const base = useRef<HTMLCanvasElement | null>(null);
  const baseFor = useRef<string>("");
  useEffect(() => {
    let raf = 0;
    let last = 0;
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      if (t - last < 150) return;
      last = t;
      const w = worlds[worldId];
      const cv = ref.current;
      if (!w?.ready || !cv) return;
      const n = w.size;
      const look = theme();
      const key = `${worldId}:${w.meta.seed}:${n}:${look.id}`;
      if (baseFor.current !== key) {
        base.current = pixelCanvas(w.tiles, n, look.terrain.minimap); // (one fillRect per tile was ~150 ms on a 512 island)
        baseFor.current = key;
      }
      const ctx = cv.getContext("2d")!;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(base.current!, 0, 0, cv.width, cv.height);
      const k = cv.width / n;
      for (const s of w.structures.values()) {
        ctx.fillStyle = s.complete ? "#ffe8b0" : "#c9a06a";
        ctx.fillRect(s.x * k, s.y * k, Math.max(2, s.w * k), Math.max(2, s.h * k));
      }
      for (const a of w.agents.values()) {
        ctx.fillStyle = look.chit.dot(a.hue);
        ctx.fillRect(a.x * k - 1, a.y * k - 1, 3, 3);
      }
      const c = cameras[worldId];
      if (c) {
        ctx.strokeStyle = "rgba(255,255,255,0.9)";
        ctx.lineWidth = 1;
        ctx.strokeRect((c.x - c.w / 2) * k, (c.y - c.h / 2) * k, c.w * k, c.h * k);
      }
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [worldId]);
  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const w = worlds[worldId];
    const r = (e.target as HTMLCanvasElement).getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * w.size, y = ((e.clientY - r.top) / r.height) * w.size;
    views[worldId]?.flyTo(x, y);
  };
  return <canvas className="minimap" ref={ref} width={160} height={160} onClick={onClick} />;
}
