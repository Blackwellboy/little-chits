import { useEffect, useRef, useState } from "react";
import { pixelCanvas } from "../render/art";
import { useUI, worlds } from "../state/store";
import { cameras, views } from "./WorldCanvas";

const ICON: Record<string, string> = { discovery: "✦", first: "★", built: "🏠", birth: "🍼", death: "🕯", legacy: "📜", learned: "💡" };

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
      {toasts.map((t) => (
        <div key={t.key} className={`toast k-${t.kind}`} onClick={() => {
          if (t.x != null) set({ focus: { world: t.world, x: t.x + 0.5, y: (t.y ?? 0) + 0.5, t: Date.now() } });
          if (t.actor && worlds[t.world]?.agents.has(t.actor)) set({ selected: { world: t.world, id: t.actor } });
        }}>
          <span className="ico">{ICON[t.kind] ?? "✦"}</span>
          <div><small>{t.world === "A" ? "World A" : "World B"} · day {Math.floor(t.tick / 240) + 1}</small><p>{t.text}</p></div>
        </div>
      ))}
    </div>
  );
}

/** A new era or the storyteller's news fills the screen for a few seconds: the moments a viewer (and the recorder)
 *  should not miss. An era toast used to slip by in the corner. */
export function Banner() {
  const toasts = useUI((s) => s.toasts);
  const [shown, setShown] = useState<{ key: string; kind: string; text: string; world: string } | null>(null);
  const seen = useRef(new Set<string>());
  useEffect(() => {
    const t = toasts.find((x) => (x.kind === "era" || x.kind === "storyteller") && !seen.current.has(x.key));
    if (!t) return;
    seen.current.add(t.key);
    setShown({ key: t.key, kind: t.kind, text: t.text, world: t.world });
    const h = setTimeout(() => setShown(null), t.kind === "era" ? 6500 : 5500);
    return () => clearTimeout(h);
  }, [toasts]);
  if (!shown) return null;
  return (
    <div key={shown.key} className={`banner k-${shown.kind}`} onClick={() => setShown(null)}>
      <small>{shown.world === "A" ? "World A" : "World B"}{shown.kind === "storyteller" ? " · news" : " · a new age"}</small>
      <h1>{shown.kind === "era" ? "🏛 " : "📣 "}{shown.text}</h1>
    </div>
  );
}

const MM_COLORS: Record<number, string> = {
  0: "#1c4a82", 1: "#2f86bd", 2: "#e0cc92", 3: "#6fae4f", 4: "#8cc053", 5: "#3f7a31", 6: "#98a95f", 7: "#7f8189", 8: "#b8704e",
};

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
      const key = `${worldId}:${w.meta.seed}:${n}`;
      if (baseFor.current !== key) {
        base.current = pixelCanvas(w.tiles, n, MM_COLORS); // (one fillRect per tile was ~150 ms on a 512 island)
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
        ctx.fillStyle = `hsl(${a.hue} 70% 65%)`;
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
