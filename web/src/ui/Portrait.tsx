import { useEffect, useRef } from "react";
import * as A from "../render/art";
import { useUI } from "../state/store";
import { themeFor } from "../theme";

/** A large pixel portrait of one chit, painted from the same art as the world. */
export function Portrait({ hue, child, sleeping, tool, size = 72 }: { hue: number; child?: boolean; sleeping?: boolean; tool?: string | null; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const themeId = useUI((s) => s.theme);
  useEffect(() => {
    const t = themeFor(themeId).chit;
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, 24, 24);
    ctx.drawImage(A.shadowCanvas(), 5, 20);
    ctx.drawImage(A.chitFoot(), 7, 20); ctx.drawImage(A.chitFoot(), 13, 20);
    ctx.drawImage(t.outline(), 4, 6);
    ctx.drawImage(t.portrait(hue), 5, 7);
    ctx.drawImage(t.eyes(sleeping ? "sleep" : "open"), 7, t.portraitEyesY);
    if (tool) ctx.drawImage(A.iconCanvas(tool), 16, 12);
  }, [hue, sleeping, tool, themeId]);
  const s = child ? size * 0.8 : size;
  return <canvas ref={ref} width={24} height={24} style={{ width: s, height: s, imageRendering: "pixelated" }} />;
}
