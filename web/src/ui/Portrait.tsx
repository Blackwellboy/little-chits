import { useEffect, useRef } from "react";
import * as A from "../render/art";

function hslStr(h: number) { return `hsl(${h} 58% 64%)`; }

/** A large pixel portrait of one chit, painted from the same art as the world. */
export function Portrait({ hue, child, sleeping, tool, size = 72 }: { hue: number; child?: boolean; sleeping?: boolean; tool?: string | null; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, 24, 24);
    // tinted body: draw grayscale then multiply by colour inside the body's alpha
    const [bc, bctx] = A.canvas(14, 14);
    bctx.drawImage(A.chitBody(), 0, 0);
    bctx.globalCompositeOperation = "multiply";
    bctx.fillStyle = hslStr(hue);
    bctx.fillRect(0, 0, 14, 14);
    bctx.globalCompositeOperation = "destination-in";
    bctx.drawImage(A.chitBody(), 0, 0);
    ctx.drawImage(A.shadowCanvas(), 5, 20);
    ctx.drawImage(A.chitFoot(), 7, 20); ctx.drawImage(A.chitFoot(), 13, 20);
    ctx.drawImage(A.chitOutline(), 4, 6);
    ctx.drawImage(bc, 5, 7);
    ctx.drawImage(A.chitEyes(sleeping ? "sleep" : "open"), 7, 10);
    if (tool) ctx.drawImage(A.iconCanvas(tool), 16, 12);
  }, [hue, sleeping, tool]);
  const s = child ? size * 0.8 : size;
  return <canvas ref={ref} width={24} height={24} style={{ width: s, height: s, imageRendering: "pixelated" }} />;
}
