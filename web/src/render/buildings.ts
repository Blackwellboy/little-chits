import { canvas, rng, shade, TS } from "./art";

/** Each painter returns a canvas whose bottom edge sits on the footprint's bottom edge. */
type Painter = (variant: number, state: number) => HTMLCanvasElement;

function px(ctx: CanvasRenderingContext2D, c: string, x: number, y: number, w = 1, h = 1) {
  ctx.fillStyle = c; ctx.fillRect(x, y, w, h);
}

function bricks(ctx: CanvasRenderingContext2D, x0: number, y0: number, w: number, h: number, base = "#b5523a") {
  px(ctx, shade(base, -0.35), x0, y0, w, h);
  for (let y = 0; y < h; y += 3) {
    const off = (y / 3) % 2 ? 2 : 0;
    for (let x = -off; x < w; x += 5) {
      const bx = Math.max(x0, x0 + x), bw = Math.min(4, x0 + w - bx, x + 4 - Math.max(0, x));
      if (bw > 0) px(ctx, (x + y) % 3 ? base : shade(base, 0.12), bx, y0 + y, bw, 2);
    }
  }
}

const campfire: Painter = (v, state) => {
  const [c, ctx] = canvas(16, 16);
  const stones = ["#8f929a", "#a6a9b1", "#767981"];
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    px(ctx, stones[i % 3], Math.round(8 + Math.cos(a) * 5) - 1, Math.round(10 + Math.sin(a) * 3) - 1, 3, 2);
  }
  px(ctx, "#5e3b1d", 4, 9, 8, 2);
  px(ctx, "#8a5a2e", 5, 8, 6, 1);
  if (!state) { px(ctx, "#3a3438", 6, 9, 4, 1); px(ctx, "#5a5458", 7, 8, 2, 1); }
  return c;
};

export function flameFrames(): HTMLCanvasElement[] {
  const out: HTMLCanvasElement[] = [];
  for (let f = 0; f < 4; f++) {
    const [c, ctx] = canvas(12, 14);
    const r = rng(f * 17 + 3);
    for (let y = 0; y < 14; y++) {
      const w = Math.max(0, Math.round((14 - y) * 0.45 + (r() - 0.5) * 2));
      const x0 = 6 - Math.floor(w / 2) + Math.round((r() - 0.5) * 1.5);
      const col = y > 9 ? "#ff5a1f" : y > 5 ? "#ff9a2e" : "#ffe06a";
      ctx.fillStyle = col;
      ctx.fillRect(x0, 13 - y, w, 1);
    }
    ctx.fillStyle = "#fff6c8";
    ctx.fillRect(5, 9, 2, 3);
    out.push(c);
  }
  return out;
}

const hut: Painter = (v) => {
  const [c, ctx] = canvas(32, 42);
  const r = rng(v + 11);
  // walls
  const wall = ["#9a6b3c", "#8c5f33", "#a8784a"][v % 3];
  px(ctx, "rgba(0,0,0,0.25)", 2, 39, 28, 3);
  for (let x = 4; x < 28; x += 3) px(ctx, (x / 3) % 2 ? wall : shade(wall, -0.12), x, 24, 3, 16);
  px(ctx, shade(wall, -0.4), 4, 38, 24, 2);
  // door
  px(ctx, "#3b2415", 13, 29, 6, 11);
  px(ctx, "#5a3822", 13, 29, 6, 1);
  // window
  px(ctx, "#2a1a10", 22, 29, 4, 4);
  // thatch roof (triangle)
  const thatch = ["#d8b35a", "#c9a24a", "#e2c06a"];
  for (let y = 0; y < 22; y++) {
    const w = Math.round(4 + y * 1.35);
    const x0 = 16 - Math.floor(w / 2);
    for (let x = 0; x < w; x++) px(ctx, thatch[Math.floor(r() * 3)], x0 + x, 4 + y, 1, 1);
    if (y % 4 === 3) px(ctx, "#a8843a", x0, 4 + y, w, 1);
  }
  px(ctx, "#8a6a2a", 1, 25, 30, 2);
  px(ctx, "#6b4f1e", 15, 2, 2, 3);
  return c;
};

const brickHouse: Painter = (v) => {
  const [c, ctx] = canvas(32, 44);
  px(ctx, "rgba(0,0,0,0.25)", 1, 41, 30, 3);
  bricks(ctx, 3, 22, 26, 20, ["#b5523a", "#a8583f", "#c0603f"][v % 3]);
  // roof
  const roof = "#6e2e2a";
  for (let y = 0; y < 14; y++) {
    const inset = 14 - y;
    px(ctx, y % 3 === 0 ? shade(roof, 0.15) : roof, 1 + Math.floor(inset * 0.9), 8 + y, 30 - Math.floor(inset * 1.8), 1);
  }
  px(ctx, "#4a1e1c", 0, 21, 32, 2);
  // chimney
  bricks(ctx, 22, 4, 4, 9, "#9a4a36");
  // door + windows
  px(ctx, "#3b2415", 13, 31, 6, 11); px(ctx, "#d9a55a", 17, 36, 1, 1);
  px(ctx, "#2a1a10", 6, 27, 5, 5); px(ctx, "#2a1a10", 21, 27, 5, 5);
  px(ctx, "#6e4a30", 8, 27, 1, 5); px(ctx, "#6e4a30", 23, 27, 1, 5);
  return c;
};

const stockpile: Painter = (v, fill) => {
  const [c, ctx] = canvas(16, 22);
  px(ctx, "rgba(0,0,0,0.22)", 1, 19, 14, 3);
  px(ctx, "#6b4526", 1, 17, 14, 3);
  px(ctx, "#8a5a2e", 1, 17, 14, 1);
  const crate = (x: number, y: number) => {
    px(ctx, "#a0703e", x, y, 6, 6); px(ctx, "#c08a50", x, y, 6, 1); px(ctx, "#6b4526", x, y + 5, 6, 1);
    px(ctx, "#6b4526", x + 2, y + 1, 1, 4);
  };
  const sack = (x: number, y: number) => {
    px(ctx, "#d8c08a", x + 1, y, 3, 1); px(ctx, "#cdb27a", x, y + 1, 5, 4); px(ctx, "#a88f5a", x, y + 4, 5, 1);
  };
  if (fill >= 1) crate(2, 11);
  if (fill >= 1) sack(9, 12);
  if (fill >= 2) crate(8, 6);
  if (fill >= 3) { sack(2, 6); crate(5, 1); }
  if (fill === 0) { px(ctx, "#8a5a2e", 3, 14, 10, 2); }
  return c;
};

/** An outpost camp by far ore, sand or clay: a canvas tent, a pennant, and its store's crates as they fill. */
const outpost: Painter = (v, fill) => {
  const [c, ctx] = canvas(32, 28);
  px(ctx, "rgba(0,0,0,0.22)", 2, 25, 28, 3);
  const cloth = ["#d8c9a0", "#cdbd92", "#e0d3ad"][v % 3];
  for (let y = 0; y < 16; y++) {   // the tent: a ridge on two poles
    const w = 2 + Math.round(y * 1.05);
    px(ctx, y % 4 === 3 ? shade(cloth, -0.12) : cloth, 11 - Math.floor(w / 2), 9 + y, w, 1);
  }
  px(ctx, "#3b2a1c", 9, 18, 4, 7);  // the way in
  px(ctx, "#6b4526", 10, 5, 1, 5); px(ctx, "#c0392b", 11, 5, 4, 2);  // a pennant
  const crate = (x: number, y: number) => {
    px(ctx, "#a0703e", x, y, 6, 6); px(ctx, "#c08a50", x, y, 6, 1); px(ctx, "#6b4526", x, y + 5, 6, 1);
    px(ctx, "#6b4526", x + 2, y + 1, 1, 4);
  };
  if (fill >= 1) crate(21, 19);
  if (fill >= 2) crate(26, 19);
  if (fill >= 3) crate(23, 13);
  if (fill === 0) px(ctx, "#8a5a2e", 21, 23, 10, 2);
  return c;
};

/** A mine dug into the rock: a timber-framed dark mouth in a stony mound, and a cart that fills as the seam does. */
const mine: Painter = (v, fill) => {
  const [c, ctx] = canvas(32, 30);
  px(ctx, "rgba(0,0,0,0.22)", 1, 27, 30, 3);
  const rock = ["#7d7a73", "#86827a", "#74716a"][v % 3];
  for (let y = 0; y < 20; y++) {   // the mound
    const w = 12 + Math.round(y * 0.95);
    px(ctx, y % 5 === 4 ? shade(rock, -0.14) : rock, 16 - Math.floor(w / 2), 7 + y, w, 1);
  }
  px(ctx, "#9b978d", 9, 9, 3, 2); px(ctx, "#5f5c56", 22, 14, 4, 2); px(ctx, "#9b978d", 25, 20, 2, 2);
  px(ctx, "#1c1712", 11, 15, 10, 12);  // the mouth
  px(ctx, "#6b4526", 10, 13, 12, 2); px(ctx, "#6b4526", 10, 15, 2, 12); px(ctx, "#6b4526", 20, 15, 2, 12);  // timbers
  px(ctx, "#8a5a2e", 10, 13, 12, 1);
  px(ctx, "#5a4a3a", 3, 25, 7, 1); px(ctx, "#5a4a3a", 23, 25, 7, 1);  // rails
  px(ctx, "#6b5a48", 23, 20, 7, 5); px(ctx, "#8a7560", 23, 20, 7, 1);  // the cart
  px(ctx, "#2a2520", 24, 25, 2, 2); px(ctx, "#2a2520", 28, 25, 2, 2);
  const ore = ["", "#c9772e", "#d9853a", "#e89a4c"];
  for (let i = 0; i < Math.min(3, fill); i++) px(ctx, ore[i + 1], 24 + i * 2, 18 - (i % 2), 2, 2);
  return c;
};

/** Great works. A great library: a columned hall under a dome, with banners. */
const greatLibrary: Painter = () => {
  const [c, ctx] = canvas(48, 60);
  px(ctx, "rgba(0,0,0,0.22)", 1, 56, 46, 4);
  px(ctx, "#cfc6b0", 2, 50, 44, 6); px(ctx, "#e4dcc6", 2, 50, 44, 1);  // steps
  px(ctx, "#ddd3bb", 5, 24, 38, 26);  // the hall
  for (let x = 7; x < 42; x += 6) { px(ctx, "#f2ead6", x, 26, 3, 24); px(ctx, "#b8ae96", x + 2, 26, 1, 24); }  // columns
  px(ctx, "#3b2a1c", 20, 38, 8, 12); px(ctx, "#5a4632", 21, 39, 6, 11);  // doors
  px(ctx, "#c9bfa6", 3, 20, 42, 4); px(ctx, "#e8dfc9", 3, 20, 42, 1);  // cornice
  for (let y = 0; y < 14; y++) { const w = 6 + Math.round(Math.sqrt(y) * 7); px(ctx, y % 3 === 2 ? "#6f8fb0" : "#7fa0c2", 24 - Math.floor(w / 2), 6 + y, w, 1); }  // dome
  px(ctx, "#e0b84a", 23, 2, 2, 4);
  px(ctx, "#b03a3a", 6, 28, 3, 9); px(ctx, "#b03a3a", 39, 28, 3, 9);  // banners
  return c;
};

/** A lighthouse: a tall striped tower on a rock, a lantern room at the top. */
const lighthouse: Painter = () => {
  const [c, ctx] = canvas(32, 64);
  px(ctx, "rgba(0,0,0,0.22)", 2, 60, 28, 4);
  px(ctx, "#7d7a73", 4, 54, 24, 7); px(ctx, "#9b978d", 4, 54, 24, 1);  // the rock
  for (let y = 16; y < 54; y++) {
    const w = 10 + Math.round((y - 16) * 0.22);
    px(ctx, Math.floor((y - 16) / 6) % 2 ? "#c0392b" : "#f2ead6", 16 - Math.floor(w / 2), y, w, 1);
  }
  px(ctx, "#3b2a1c", 14, 47, 4, 7);
  px(ctx, "#2f3640", 9, 14, 14, 2);  // gallery
  px(ctx, "#ffe59a", 11, 6, 10, 8); px(ctx, "#fff6d0", 13, 7, 4, 5);  // the lantern
  px(ctx, "#2f3640", 10, 4, 12, 2); px(ctx, "#2f3640", 15, 1, 2, 3);
  return c;
};

/** An aqueduct: stone arches carrying a channel of water. */
const aqueduct: Painter = () => {
  const [c, ctx] = canvas(48, 36);
  px(ctx, "rgba(0,0,0,0.22)", 1, 32, 46, 4);
  px(ctx, "#b8ae96", 0, 8, 48, 6); px(ctx, "#5aa0d8", 1, 8, 46, 2); px(ctx, "#8cc4ec", 1, 8, 46, 1);  // channel
  for (let x = 0; x < 48; x += 12) {
    px(ctx, "#cfc6b0", x, 14, 4, 20); px(ctx, "#a89e86", x + 3, 14, 1, 20);  // piers
    for (let y = 0; y < 6; y++) px(ctx, "#cfc6b0", x + 4, 14 + y, Math.max(0, 4 - y), 1), px(ctx, "#cfc6b0", x + 8 + y, 14 + y, Math.max(0, 4 - y), 1);
  }
  return c;
};

const farm: Painter = (v, stage) => {
  const [c, ctx] = canvas(32, 32);
  px(ctx, "#6b4a2e", 1, 1, 30, 30);
  for (let y = 3; y < 30; y += 4) { px(ctx, "#5a3c24", 2, y, 28, 2); px(ctx, "#7d5838", 2, y + 2, 28, 1); }
  // crops
  const r = rng(v * 3 + 1);
  if (stage > 0) {
    for (let y = 3; y < 30; y += 4) {
      for (let x = 3; x < 29; x += 3) {
        if (stage === 1) { px(ctx, "#8fd05a", x, y, 1, 1); }
        else if (stage === 2) { px(ctx, "#5aa845", x, y - 2, 1, 3); px(ctx, "#7cc55a", x + 1, y - 1, 1, 1); }
        else { px(ctx, "#b89a3a", x, y - 3, 1, 4); px(ctx, "#f2cf5a", x - (r() < 0.5 ? 1 : 0), y - 4, 2, 2); }
      }
    }
  }
  // fence
  px(ctx, "#a07a4a", 0, 0, 32, 1); px(ctx, "#a07a4a", 0, 31, 32, 1);
  px(ctx, "#a07a4a", 0, 0, 1, 32); px(ctx, "#a07a4a", 31, 0, 1, 32);
  for (let i = 0; i < 32; i += 6) { px(ctx, "#7a5a32", i, 0, 1, 2); px(ctx, "#7a5a32", i, 30, 1, 2); }
  return c;
};

const workshop: Painter = (v) => {
  const [c, ctx] = canvas(32, 40);
  px(ctx, "rgba(0,0,0,0.25)", 1, 37, 30, 3);
  px(ctx, "#8a8272", 2, 26, 28, 12);
  px(ctx, "#6b4526", 3, 14, 2, 24); px(ctx, "#6b4526", 27, 14, 2, 24);
  // plank roof
  for (let y = 0; y < 8; y++) px(ctx, y % 2 ? "#8a5a2e" : "#a0703e", 0, 8 + y, 32, 1);
  px(ctx, "#5e3b1d", 0, 16, 32, 1);
  // bench + tools
  px(ctx, "#a0703e", 7, 28, 18, 3); px(ctx, "#6b4526", 8, 31, 2, 6); px(ctx, "#6b4526", 22, 31, 2, 6);
  px(ctx, "#9ea1a9", 11, 26, 4, 2); px(ctx, "#8a5a2e", 17, 25, 1, 3); px(ctx, "#c2c5cc", 18, 25, 2, 1);
  px(ctx, "#9ea1a9", 9, 19, 1, 4); px(ctx, "#9ea1a9", 13, 19, 3, 1); px(ctx, "#8a5a2e", 14, 19, 1, 5);
  return c;
};

const kiln: Painter = (v) => {
  const [c, ctx] = canvas(16, 24);
  px(ctx, "rgba(0,0,0,0.25)", 1, 21, 14, 3);
  for (let y = 0; y < 16; y++) {
    const w = Math.round(Math.sqrt(Math.max(0, 1 - ((y - 16) / 16) ** 2)) * 14);
    px(ctx, y < 3 ? "#d69474" : y > 12 ? "#8a4a30" : "#b8704e", 8 - w / 2, 7 + y, w, 1);
  }
  px(ctx, "#8a4a30", 6, 4, 4, 4); px(ctx, "#5a3020", 6, 4, 4, 1);
  px(ctx, "#2a1410", 5, 15, 6, 7);
  px(ctx, "#ff8a2e", 6, 18, 4, 4); px(ctx, "#ffd06a", 7, 19, 2, 2);
  return c;
};

const furnace: Painter = (v) => {
  const [c, ctx] = canvas(16, 30);
  px(ctx, "rgba(0,0,0,0.25)", 0, 27, 16, 3);
  bricks(ctx, 1, 10, 14, 19, "#9a4a36");
  bricks(ctx, 5, 1, 6, 10, "#8a4030");
  px(ctx, "#1a0c08", 4, 19, 8, 8);
  px(ctx, "#ff6a1f", 5, 21, 6, 6); px(ctx, "#ffd06a", 6, 23, 4, 3); px(ctx, "#fff6c8", 7, 24, 2, 1);
  return c;
};

const library: Painter = (v) => {
  const [c, ctx] = canvas(32, 46);
  px(ctx, "rgba(0,0,0,0.25)", 0, 43, 32, 3);
  bricks(ctx, 2, 22, 28, 22, "#c9b48a");
  // columns
  for (const x of [4, 11, 19, 26]) { px(ctx, "#efe6d0", x, 22, 3, 21); px(ctx, "#bfb49a", x + 2, 22, 1, 21); }
  // pediment
  for (let y = 0; y < 10; y++) px(ctx, y % 3 ? "#d9cba8" : "#bfb49a", 16 - (y * 1.6 + 2), 11 + y, (y * 1.6 + 2) * 2, 1);
  px(ctx, "#a89a78", 0, 21, 32, 2);
  px(ctx, "#3b2415", 14, 33, 5, 10);
  px(ctx, "#6b4a30", 13, 14, 6, 4); px(ctx, "#e8d8b0", 14, 15, 4, 1);
  return c;
};

const monument: Painter = (v) => {
  const [c, ctx] = canvas(32, 54);
  px(ctx, "rgba(0,0,0,0.3)", 2, 50, 28, 4);
  px(ctx, "#8f929a", 3, 44, 26, 8); px(ctx, "#b9bcc4", 3, 44, 26, 1);
  px(ctx, "#a6a9b1", 7, 40, 18, 5);
  for (let y = 0; y < 34; y++) {
    const w = Math.round(10 - y * 0.18);
    px(ctx, y % 7 === 0 ? "#b9bcc4" : "#9ea1a9", 16 - w / 2, 40 - y, w, 1);
    px(ctx, "#7a7d85", 16 + w / 2 - 1, 40 - y, 1, 1);
  }
  px(ctx, "#e0883a", 13, 3, 6, 4); px(ctx, "#ffc07a", 14, 3, 3, 1); px(ctx, "#b8652a", 13, 6, 6, 1);
  px(ctx, "#e0883a", 12, 24, 8, 1);
  return c;
};

// ---------------------------------------------------------------- bigger homes, the bridge, useful buildings

/** A long timber hall (3x2) under a thatched roof, carved horns crossing at the gables. */
const longhouse: Painter = (v) => {
  const [c, ctx] = canvas(48, 40);
  const r = rng(v + 23);
  px(ctx, "rgba(0,0,0,0.25)", 2, 37, 44, 3);
  const wall = ["#8c5f33", "#9a6b3c", "#80552c"][v % 3];
  for (let x = 3; x < 45; x += 3) px(ctx, (x / 3) % 2 ? wall : shade(wall, -0.12), x, 22, 3, 16);
  for (const x of [3, 23, 43]) px(ctx, shade(wall, -0.3), x, 22, 2, 16);
  px(ctx, shade(wall, -0.4), 3, 36, 42, 2);
  px(ctx, "#3b2415", 20, 27, 8, 11); px(ctx, "#5a3822", 20, 27, 8, 1); px(ctx, "#6b4526", 23, 28, 2, 10);
  px(ctx, "#2a1a10", 8, 27, 5, 4); px(ctx, "#2a1a10", 35, 27, 5, 4);
  const thatch = ["#c9a24a", "#b8923e", "#d8b35a"];
  for (let y = 0; y < 16; y++) {
    const inset = Math.round((15 - y) * 0.7);
    for (let x = inset; x < 48 - inset; x++) px(ctx, thatch[Math.floor(r() * 3)], x, 7 + y, 1, 1);
    if (y % 4 === 3) px(ctx, "#9a7a32", inset, 7 + y, 48 - 2 * inset, 1);
  }
  px(ctx, "#7a5a22", 0, 22, 48, 2);
  px(ctx, "#6b4f1e", 11, 6, 26, 2);
  px(ctx, "#5e3b1d", 9, 3, 2, 4); px(ctx, "#5e3b1d", 7, 1, 2, 3); px(ctx, "#5e3b1d", 37, 3, 2, 4); px(ctx, "#5e3b1d", 39, 1, 2, 3);
  px(ctx, "#2a1a10", 22, 5, 4, 2);
  return c;
};

function pane(ctx: CanvasRenderingContext2D, x: number, y: number) {
  px(ctx, "#3a2a20", x - 1, y - 1, 7, 7); px(ctx, "#9fd4ee", x, y, 5, 5); px(ctx, "#dff4ff", x, y, 2, 2);
  px(ctx, "#3a2a20", x + 2, y, 1, 5); px(ctx, "#3a2a20", x, y + 2, 5, 1);
}

/** Two floors of brick with glass windows and a slate roof: the tallest home, on a 2x2 footprint. */
const twoStorey: Painter = (v) => {
  const [c, ctx] = canvas(32, 62);
  px(ctx, "rgba(0,0,0,0.25)", 1, 59, 30, 3);
  const base = ["#b5523a", "#a8583f", "#c0603f"][v % 3];
  bricks(ctx, 3, 22, 26, 38, base);
  px(ctx, shade(base, -0.45), 3, 40, 26, 2);
  pane(ctx, 6, 27); pane(ctx, 21, 27); pane(ctx, 6, 46);
  px(ctx, "#6b4526", 5, 33, 7, 1); px(ctx, "#e05a7a", 6, 32, 1, 1); px(ctx, "#ffd06a", 8, 32, 1, 1); px(ctx, "#e05a7a", 10, 32, 1, 1);
  px(ctx, "#3b2415", 18, 48, 7, 12); px(ctx, "#5a3822", 18, 48, 7, 1); px(ctx, "#d9a55a", 23, 54, 1, 1);
  const roof = "#4a5566";
  for (let y = 0; y < 16; y++) {
    const inset = 15 - y;
    px(ctx, y % 3 === 0 ? shade(roof, 0.15) : roof, 1 + Math.floor(inset * 0.9), 6 + y, 30 - Math.floor(inset * 1.8), 1);
  }
  px(ctx, "#2e3644", 0, 21, 32, 2);
  bricks(ctx, 23, 2, 4, 10, "#9a4a36");
  return c;
};

/** Planks over the water with a rail on each side. state = length, +10 when it runs north-south. */
const bridge: Painter = (v, st) => {
  const n = Math.max(1, st % 10);
  if (st < 10) {
    const W = n * TS + 8;
    const [c, ctx] = canvas(W, 20);
    for (let x = 6; x < W - 4; x += 12) px(ctx, "#3f2a17", x, 16, 2, 4); // piles in the water
    for (let x = 0; x < W; x += 2) px(ctx, (x / 2) % 2 ? "#a0703e" : "#8a5a2e", x, 6, 2, 10);
    px(ctx, "#c08a50", 0, 6, W, 1); px(ctx, "#5e3b1d", 0, 15, W, 1);
    px(ctx, "#6b4526", 0, 2, W, 1); px(ctx, "#6b4526", 0, 13, W, 1);
    for (let x = 1; x < W; x += 7) { px(ctx, "#4a3018", x, 1, 2, 6); px(ctx, "#4a3018", x, 12, 2, 5); }
    return c;
  }
  const H = n * TS + 4;
  const [c, ctx] = canvas(20, H);
  for (let y = 0; y < H; y += 2) px(ctx, (y / 2) % 2 ? "#a0703e" : "#8a5a2e", 4, y, 12, 2);
  px(ctx, "#c08a50", 4, 0, 1, H); px(ctx, "#5e3b1d", 15, 0, 1, H);
  px(ctx, "#6b4526", 2, 0, 1, H); px(ctx, "#6b4526", 17, 0, 1, H);
  for (let y = 1; y < H; y += 7) { px(ctx, "#4a3018", 1, y, 3, 2); px(ctx, "#4a3018", 16, y, 3, 2); }
  return c;
};

/** A stone well under a little roof, with a rope and bucket. */
const well: Painter = () => {
  const [c, ctx] = canvas(16, 26);
  px(ctx, "rgba(0,0,0,0.25)", 1, 23, 14, 3);
  for (let y = 0; y < 7; y++) px(ctx, ["#b9bcc4", "#9ea1a9", "#8f929a"][y % 3], 2, 16 + y, 12, 1);
  for (let x = 4; x < 14; x += 4) px(ctx, "#767981", x, 17, 1, 5);
  px(ctx, "#a6a9b1", 2, 14, 12, 2); px(ctx, "#1c4a82", 4, 14, 8, 1);
  px(ctx, "#6b4526", 2, 5, 1, 10); px(ctx, "#6b4526", 13, 5, 1, 10);
  px(ctx, "#8a5a2e", 3, 7, 10, 1);
  px(ctx, "#d8c08a", 8, 8, 1, 4); px(ctx, "#8a5a2e", 7, 11, 3, 2); px(ctx, "#6b4526", 7, 12, 3, 1);
  for (let y = 0; y < 5; y++) { const w = 4 + y * 3; px(ctx, y % 2 ? "#8a3a2a" : "#a0463a", 8 - Math.floor(w / 2), 1 + y, w, 1); }
  return c;
};

/** A store-house raised on mushroom stones, out of reach of damp and mice. */
const granary: Painter = (v) => {
  const [c, ctx] = canvas(32, 42);
  const r = rng(v + 31);
  px(ctx, "rgba(0,0,0,0.25)", 2, 39, 28, 3);
  for (const x of [4, 14, 24]) { px(ctx, "#8f929a", x + 1, 33, 3, 7); px(ctx, "#b9bcc4", x, 32, 5, 2); }
  const wall = "#a8784a";
  for (let x = 3; x < 29; x += 3) px(ctx, (x / 3) % 2 ? wall : shade(wall, -0.12), x, 18, 3, 13);
  px(ctx, "#6b4526", 3, 30, 26, 2); px(ctx, "#6b4526", 3, 18, 26, 1);
  px(ctx, "#3b2415", 13, 22, 6, 8); px(ctx, "#d8c08a", 14, 26, 4, 4); px(ctx, "#b89a5a", 14, 26, 4, 1);
  px(ctx, "#8a5a2e", 13, 32, 1, 8); px(ctx, "#8a5a2e", 18, 32, 1, 8);
  for (let y = 33; y < 40; y += 2) px(ctx, "#8a5a2e", 13, y, 6, 1);
  const thatch = ["#d8b35a", "#c9a24a", "#e2c06a"];
  for (let y = 0; y < 16; y++) {
    const w = Math.round(6 + y * 1.7), x0 = 16 - Math.floor(w / 2);
    for (let x = 0; x < w; x++) px(ctx, thatch[Math.floor(r() * 3)], x0 + x, 2 + y, 1, 1);
    if (y % 4 === 3) px(ctx, "#a8843a", x0, 2 + y, w, 1);
  }
  px(ctx, "#6b4f1e", 15, 0, 2, 3);
  return c;
};

/** A warehouse: a long timber store under a shingled roof, its wide doors open on stacked crates as it fills. */
const warehouse: Painter = (v, fill) => {
  const [c, ctx] = canvas(32, 36);
  px(ctx, "rgba(0,0,0,0.25)", 1, 33, 30, 3);
  const wall = ["#9a6a3c", "#8f6238", "#a4733f"][v % 3];
  for (let x = 2; x < 30; x += 2) px(ctx, (x / 2) % 2 ? wall : shade(wall, -0.1), x, 14, 2, 19);
  px(ctx, "#5e3b20", 2, 31, 28, 2); px(ctx, "#5e3b20", 2, 14, 28, 1);
  px(ctx, "#2e1d10", 10, 19, 12, 12);  // the open doors
  px(ctx, "#6b4526", 9, 19, 1, 12); px(ctx, "#6b4526", 22, 19, 1, 12);
  const crate = (x: number, y: number) => { px(ctx, "#a0703e", x, y, 4, 4); px(ctx, "#c08a50", x, y, 4, 1); };
  if (fill >= 1) { crate(11, 27); crate(17, 27); }
  if (fill >= 2) { crate(14, 23); }
  if (fill >= 3) { crate(11, 23); crate(17, 23); crate(14, 19); }
  const roof = ["#6a4a3a", "#5c4032", "#76523f"];
  for (let y = 0; y < 13; y++) {
    const w = Math.round(12 + y * 1.5), x0 = 16 - Math.floor(w / 2);
    for (let x = 0; x < w; x++) px(ctx, roof[(x + y + v) % 3], x0 + x, 1 + y, 1, 1);
    if (y % 3 === 2) px(ctx, "#3f2a1f", x0, 1 + y, w, 1);
  }
  return c;
};

/** A windmill: a tapering stone tower, a red cap and four lattice sails. */
const mill: Painter = () => {
  const [c, ctx] = canvas(40, 58);
  px(ctx, "rgba(0,0,0,0.25)", 6, 55, 28, 3);
  for (let y = 0; y < 34; y++) {
    const w = Math.round(14 + y * 0.35), x0 = 20 - Math.floor(w / 2);
    px(ctx, y % 5 === 0 ? "#b9bcc4" : "#a6a9b1", x0, 22 + y, w, 1);
    px(ctx, "#8f929a", x0 + w - 2, 22 + y, 2, 1);
  }
  px(ctx, "#3b2415", 17, 46, 6, 10); px(ctx, "#5a3822", 17, 46, 6, 1); px(ctx, "#2a1a10", 18, 32, 4, 4);
  for (let y = 0; y < 7; y++) { const w = 6 + y * 2; px(ctx, y % 2 ? "#6e2e2a" : "#7e3a32", 20 - w / 2, 15 + y, w, 1); }
  const hx = 20, hy = 19;
  for (const [dx, dy] of [[1, -1], [-1, -1], [1, 1], [-1, 1]]) {
    for (let i = 3; i < 17; i++) {
      const x = hx + dx * Math.round(i * 0.72), y = hy + dy * Math.round(i * 0.72);
      px(ctx, "#5e3b1d", x, y, 1, 1);
      px(ctx, i % 3 === 0 ? "#bfb49a" : "#efe6d0", x + dy, y - dx, 1, 1);
      px(ctx, i % 3 === 0 ? "#bfb49a" : "#e2d8bc", x + 2 * dy, y - 2 * dx, 1, 1);
    }
  }
  px(ctx, "#3f2a17", hx - 1, hy - 1, 3, 3);
  return c;
};

/** An open-fronted forge: a glowing hearth inside, an anvil at the door, a smoking chimney. */
const smithy: Painter = () => {
  const [c, ctx] = canvas(32, 42);
  px(ctx, "rgba(0,0,0,0.25)", 1, 39, 30, 3);
  bricks(ctx, 2, 18, 28, 22, "#8f8a80");
  px(ctx, "#1a120c", 5, 23, 15, 17);
  px(ctx, "#5a3020", 6, 33, 11, 7); px(ctx, "#ff6a1f", 8, 32, 7, 3); px(ctx, "#ffd06a", 10, 32, 3, 2);
  px(ctx, "#9ea1a9", 16, 25, 1, 4); px(ctx, "#9ea1a9", 15, 25, 3, 1); px(ctx, "#c2c5cc", 8, 25, 2, 3);
  px(ctx, "#6a6a78", 22, 33, 8, 1); px(ctx, "#3a3a44", 22, 34, 8, 2); px(ctx, "#3a3a44", 24, 36, 4, 2);
  px(ctx, "#2a2a30", 23, 38, 6, 2); px(ctx, "#6a6a78", 21, 33, 2, 1);
  for (let y = 0; y < 8; y++) px(ctx, y % 2 ? "#4a4a55" : "#5a5a66", 0, 10 + y, 32, 1);
  px(ctx, "#33333b", 0, 18, 32, 1);
  bricks(ctx, 5, 1, 5, 10, "#7a3a2a");
  return c;
};

/** A lookout on splayed legs, with a roofed platform and a pennant. */
const watchtower: Painter = () => {
  const [c, ctx] = canvas(20, 60);
  px(ctx, "rgba(0,0,0,0.25)", 1, 57, 18, 3);
  for (let y = 0; y < 34; y++) {
    const s = Math.round(y * 0.1);
    px(ctx, "#6b4526", 4 - s, 24 + y, 2, 1); px(ctx, "#6b4526", 14 + s, 24 + y, 2, 1);
  }
  for (const y0 of [28, 41]) for (let i = 0; i < 10; i++) { px(ctx, "#8a5a2e", 5 + i, y0 + i, 1, 1); px(ctx, "#8a5a2e", 14 - i, y0 + i, 1, 1); }
  px(ctx, "#8a5a2e", 1, 22, 18, 3); px(ctx, "#a0703e", 1, 22, 18, 1);
  px(ctx, "#9a6b3c", 3, 13, 14, 9); px(ctx, "#2a1a10", 5, 15, 10, 3); px(ctx, "#6b4526", 3, 13, 14, 1);
  for (let y = 0; y < 6; y++) { const w = 2 + y * 3; px(ctx, y % 2 ? "#6e2e2a" : "#7e3a32", 10 - Math.floor(w / 2), 7 + y, w, 1); }
  px(ctx, "#5e3b1d", 9, 0, 1, 8); px(ctx, "#e0883a", 10, 1, 6, 3); px(ctx, "#e0883a", 10, 4, 3, 1);
  return c;
};

/** A timber-framed schoolhouse: big windows, a slate board by the door, a pennant on the ridge. */
const school: Painter = () => {
  const [c, ctx] = canvas(32, 46);
  px(ctx, "rgba(0,0,0,0.25)", 1, 43, 30, 3);
  px(ctx, "#e8dcc0", 3, 24, 26, 20); px(ctx, "#b8a888", 3, 42, 26, 2);
  for (const x of [3, 16, 28]) px(ctx, "#6b4526", x, 24, 1, 19);
  px(ctx, "#6b4526", 3, 33, 26, 1);
  for (const x of [6, 20]) {
    px(ctx, "#3a2a20", x, 25, 6, 7); px(ctx, "#9fd4ee", x + 1, 26, 4, 5);
    px(ctx, "#3a2a20", x + 3, 26, 1, 5); px(ctx, "#3a2a20", x + 1, 28, 4, 1);
  }
  px(ctx, "#3b2415", 18, 35, 6, 9); px(ctx, "#5a3822", 18, 35, 6, 1);
  px(ctx, "#2f3a36", 5, 35, 9, 6); px(ctx, "#6b4526", 5, 41, 9, 1);
  px(ctx, "#e8f0e8", 6, 36, 3, 1); px(ctx, "#e8f0e8", 7, 38, 5, 1); px(ctx, "#e8f0e8", 10, 36, 2, 1);
  for (let y = 0; y < 14; y++) {
    const inset = 13 - y;
    px(ctx, y % 3 === 0 ? "#c04a3a" : "#a83c30", 1 + inset, 10 + y, 30 - 2 * inset, 1);
  }
  px(ctx, "#7a2a22", 0, 23, 32, 1);
  px(ctx, "#5e3b1d", 15, 1, 1, 10); px(ctx, "#4a8ad8", 16, 2, 5, 2); px(ctx, "#4a8ad8", 16, 4, 3, 1);
  return c;
};

/** A slim brick tower, an open belfry with a copper bell, a pointed slate roof. */
const bellTower: Painter = () => {
  const [c, ctx] = canvas(18, 66);
  px(ctx, "rgba(0,0,0,0.25)", 1, 63, 16, 3);
  bricks(ctx, 3, 26, 12, 38, "#b5523a");
  px(ctx, "#3b2415", 7, 56, 4, 8); px(ctx, "#2a1a10", 8, 40, 2, 4);
  px(ctx, "#c9b48a", 2, 12, 14, 14); px(ctx, "#1a120c", 5, 15, 8, 10); px(ctx, "#1a120c", 6, 14, 6, 1);
  px(ctx, "#e0883a", 7, 17, 4, 5); px(ctx, "#e0883a", 6, 21, 6, 2); px(ctx, "#ffc07a", 8, 17, 1, 4);
  px(ctx, "#b8652a", 6, 22, 6, 1); px(ctx, "#b8652a", 9, 23, 1, 1);
  px(ctx, "#a89a78", 2, 25, 14, 1);
  for (let y = 0; y < 11; y++) { const w = 2 + Math.round(y * 1.4); px(ctx, y % 2 ? "#4a5566" : "#5a6576", 9 - Math.floor(w / 2), 1 + y, w, 1); }
  px(ctx, "#e0883a", 8, 0, 2, 2);
  return c;
};

// ---------------------------------------------------------------- the later ages (issue #12)
// The forge, factory, market, shrine, pen and launch pad had no painter: finished, they were drawn as nothing.

function smoke(ctx: CanvasRenderingContext2D, x: number, y: number, n = 3) {
  for (let i = 0; i < n; i++) px(ctx, i % 2 ? "rgba(200,200,205,0.55)" : "rgba(170,170,178,0.5)", x + i, y - i * 3, 3, 2);
}

function gearAt(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, col = "#8a8f99") {
  for (let a = 0; a < 8; a++) {
    const t = (a / 8) * Math.PI * 2;
    px(ctx, col, Math.round(cx + Math.cos(t) * r) - 1, Math.round(cy + Math.sin(t) * r) - 1, 2, 2);
  }
  px(ctx, shade(col, 0.15), cx - r + 1, cy - r + 1, 2 * r - 1, 2 * r - 1);
  px(ctx, "#2a2a30", cx - 1, cy - 1, 2, 2);
}

/** A blast forge: a squat brick hearth roaring white-hot, a tall chimney, an anvil and a quench trough. */
const forge: Painter = () => {
  const [c, ctx] = canvas(32, 48);
  px(ctx, "rgba(0,0,0,0.25)", 1, 45, 30, 3);
  bricks(ctx, 2, 22, 22, 24, "#7e3a2c");
  bricks(ctx, 19, 2, 6, 22, "#6e3226");
  smoke(ctx, 20, 2);
  px(ctx, "#140806", 5, 28, 13, 12);
  px(ctx, "#ff5a1f", 6, 31, 11, 9); px(ctx, "#ffb04a", 8, 33, 7, 6); px(ctx, "#fff6c8", 10, 35, 3, 3);
  px(ctx, "#3a3a44", 25, 38, 6, 2); px(ctx, "#2a2a30", 26, 40, 4, 5); px(ctx, "#6a6a78", 25, 38, 6, 1);
  px(ctx, "#4a6a8a", 3, 42, 6, 3); px(ctx, "#6a8aaa", 3, 42, 6, 1);
  return c;
};

/** A factory: a long brick hall with saw-tooth roof lights, two smoking stacks and a great gear by the door. */
const factory: Painter = () => {
  const [c, ctx] = canvas(48, 62);
  px(ctx, "rgba(0,0,0,0.28)", 1, 59, 46, 3);
  bricks(ctx, 2, 30, 44, 30, "#9a4a36");
  for (let i = 0; i < 4; i++) {
    const x0 = 3 + i * 11;
    for (let y = 0; y < 8; y++) px(ctx, "#4a4f5a", x0 + y, 22 + y, 11 - y, 1);
    px(ctx, "#a8d0f0", x0, 23, 1, 7); px(ctx, "#cfe6f8", x0 + 1, 24, 1, 6);
  }
  bricks(ctx, 8, 4, 5, 20, "#7a3a2a"); bricks(ctx, 34, 0, 5, 24, "#7a3a2a");
  px(ctx, "#2a2a30", 8, 4, 5, 1); px(ctx, "#2a2a30", 34, 0, 5, 1);
  smoke(ctx, 9, 3); smoke(ctx, 35, 0, 2);
  for (const x of [5, 15, 29, 39]) { px(ctx, "#f2c86a", x, 38, 4, 5); px(ctx, "#5a3020", x, 38, 4, 1); }
  px(ctx, "#2e1d10", 20, 46, 8, 13); px(ctx, "#4a3020", 20, 46, 8, 1);
  gearAt(ctx, 41, 51, 4);
  return c;
};

/** A market: striped awnings over stalls of fruit, cloth and pots. */
const market: Painter = (v) => {
  const [c, ctx] = canvas(32, 34);
  px(ctx, "rgba(0,0,0,0.22)", 1, 31, 30, 3);
  const awn = [["#c84a3a", "#f2e2b8"], ["#3a7ac8", "#f2e2b8"], ["#3a9a5a", "#f2e2b8"]][v % 3];
  for (const x0 of [1, 17]) {
    px(ctx, "#6b4526", x0 + 1, 14, 1, 17); px(ctx, "#6b4526", x0 + 13, 14, 1, 17);
    for (let x = 0; x < 15; x++) px(ctx, awn[Math.floor(x / 3) % 2], x0 + x, 10, 1, 5);
    for (let x = 0; x < 15; x += 3) px(ctx, awn[0], x0 + x, 15, 2, 1);
    px(ctx, "#a0703e", x0 + 1, 24, 13, 3); px(ctx, "#c08a50", x0 + 1, 24, 13, 1);
  }
  for (const [x, col] of [[3, "#d84a4a"], [6, "#e8a43a"], [9, "#8ac84a"]] as [number, string][]) px(ctx, col, x, 22, 2, 2);
  px(ctx, "#b8704e", 20, 20, 3, 4); px(ctx, "#8a4a30", 20, 20, 3, 1); px(ctx, "#6a8ad8", 25, 21, 5, 3);
  return c;
};

/** A shrine: a small stone house with a pitched roof and a candle burning at its open door. */
const shrine: Painter = () => {
  const [c, ctx] = canvas(16, 28);
  px(ctx, "rgba(0,0,0,0.22)", 1, 25, 14, 3);
  px(ctx, "#8f929a", 1, 24, 14, 2); px(ctx, "#b9bcc4", 1, 24, 14, 1);
  px(ctx, "#a6a9b1", 3, 12, 10, 12); px(ctx, "#8f929a", 12, 12, 1, 12);
  for (let y = 0; y < 7; y++) { const w = 2 + y * 2; px(ctx, y % 2 ? "#6e2e2a" : "#7e3a32", 8 - w / 2, 5 + y, w, 1); }
  px(ctx, "#1a120c", 6, 16, 4, 8); px(ctx, "#f2e2b8", 7, 20, 2, 3); px(ctx, "#ffd06a", 7, 18, 2, 2);
  px(ctx, "#e0b04a", 7, 2, 2, 4); px(ctx, "#e0b04a", 6, 3, 4, 1);
  return c;
};

/** A pen: a split-rail fence round a patch of trodden grass, its gate ajar. */
const pen: Painter = () => {
  const [c, ctx] = canvas(32, 32);
  px(ctx, "#7aa04a", 2, 12, 28, 18); px(ctx, "#8ab05a", 4, 14, 24, 2);
  for (const y of [12, 29]) for (let x = 1; x < 31; x += 6) px(ctx, "#5e3b1d", x, y - 4, 2, 6);
  for (const x of [1, 29]) for (let y = 12; y < 30; y += 6) px(ctx, "#5e3b1d", x, y - 4, 2, 6);
  for (const y of [9, 26]) { px(ctx, "#8a5a2e", 1, y, 30, 1); px(ctx, "#8a5a2e", 1, y + 2, 30, 1); }
  for (const x of [1, 29]) { px(ctx, "#8a5a2e", x, 9, 1, 20); px(ctx, "#8a5a2e", x + 1, 9, 1, 20); }
  px(ctx, "#7aa04a", 13, 26, 7, 3);
  px(ctx, "#a07a4a", 19, 25, 1, 5);
  return c;
};

/** The launch pad: a lattice gantry beside a white rocket on a scorched concrete apron. */
const launchPad: Painter = () => {
  const [c, ctx] = canvas(48, 96);
  px(ctx, "rgba(0,0,0,0.3)", 1, 93, 46, 3);
  px(ctx, "#8a8a8a", 2, 84, 44, 10); px(ctx, "#a8a8a8", 2, 84, 44, 1); px(ctx, "#3a3a3a", 16, 86, 16, 6);
  for (let y = 6; y < 84; y++) {
    px(ctx, "#b84a2a", 4, y, 1, 1); px(ctx, "#b84a2a", 12, y, 1, 1);
    if (y % 6 === 0) { px(ctx, "#b84a2a", 4, y, 9, 1); for (let i = 0; i < 8; i++) px(ctx, "#a8402a", 4 + i, y + Math.round(i * 0.7), 1, 1); }
  }
  px(ctx, "#8a3a20", 12, 30, 12, 2);
  for (let y = 0; y < 76; y++) {
    const w = y < 14 ? Math.round(2 + y * 0.6) : 10;
    px(ctx, y % 9 === 0 ? "#d8d8de" : "#f2f2f6", 30 - Math.floor(w / 2), 8 + y, w, 1);
    px(ctx, "#c2c2c8", 30 + Math.ceil(w / 2) - 1, 8 + y, 1, 1);
  }
  px(ctx, "#c84a3a", 25, 40, 10, 3); px(ctx, "#3a5ac8", 28, 58, 4, 4);
  for (const dx of [-1, 1]) for (let i = 0; i < 6; i++) px(ctx, "#c84a3a", 30 + dx * (5 + i), 74 + i, 1, 10 - i);
  return c;
};

/** A steam pump: a brick engine house, a rocking beam over the well shaft and a pipe running off to the fields. */
const steamPump: Painter = () => {
  const [c, ctx] = canvas(32, 46);
  px(ctx, "rgba(0,0,0,0.25)", 1, 43, 30, 3);
  bricks(ctx, 2, 22, 18, 22, "#a8503a");
  for (let y = 0; y < 6; y++) px(ctx, y % 2 ? "#4a4f5a" : "#5a606c", 1, 16 + y, 20, 1);
  bricks(ctx, 15, 2, 4, 16, "#7a3a2a"); smoke(ctx, 15, 2);
  px(ctx, "#2e1d10", 8, 34, 6, 10);
  px(ctx, "#3a3a44", 12, 12, 18, 2); px(ctx, "#6a6a78", 12, 12, 18, 1);
  px(ctx, "#2a2a30", 20, 13, 2, 9);
  px(ctx, "#3a3a44", 28, 14, 1, 16); px(ctx, "#8f929a", 25, 30, 6, 14); px(ctx, "#b9bcc4", 25, 30, 6, 1);
  px(ctx, "#4a6a8a", 20, 40, 12, 2); px(ctx, "#6a8aaa", 20, 40, 12, 1);
  return c;
};

/** A sawmill: an open timber shed, a spinning blade on its bench, a log on the carriage and a stack of planks. */
const sawmill: Painter = () => {
  const [c, ctx] = canvas(32, 40);
  px(ctx, "rgba(0,0,0,0.25)", 1, 37, 30, 3);
  for (const x of [2, 15, 28]) px(ctx, "#6b4526", x, 14, 2, 24);
  for (let y = 0; y < 7; y++) px(ctx, y % 2 ? "#5a606c" : "#4a4f5a", 0, 8 + y, 32, 1);
  px(ctx, "#33333b", 0, 15, 32, 1);
  bricks(ctx, 24, 1, 4, 8, "#7a3a2a"); smoke(ctx, 24, 1, 2);
  px(ctx, "#a0703e", 3, 28, 24, 3); px(ctx, "#6b4526", 4, 31, 2, 6); px(ctx, "#6b4526", 24, 31, 2, 6);
  px(ctx, "#8a5a2e", 4, 25, 12, 3); px(ctx, "#c08a50", 4, 25, 1, 3); px(ctx, "#c08a50", 15, 25, 1, 3);
  gearAt(ctx, 20, 25, 4, "#c2c5cc");
  for (let i = 0; i < 4; i++) { px(ctx, "#d8b070", 21, 33 - i * 2, 10, 1); px(ctx, "#b88a50", 21, 34 - i * 2, 10, 1); }
  return c;
};

/** A printing press: a timber workshop with a great screw press in its window and sheets drying on a line. */
const printingPress: Painter = () => {
  const [c, ctx] = canvas(32, 44);
  px(ctx, "rgba(0,0,0,0.25)", 1, 41, 30, 3);
  px(ctx, "#a8784a", 2, 20, 28, 22);
  for (let x = 2; x < 30; x += 4) px(ctx, "#6b4526", x, 20, 1, 22);
  px(ctx, "#6b4526", 2, 30, 28, 1);
  for (let y = 0; y < 12; y++) { const w = 6 + y * 2; px(ctx, y % 2 ? "#5a6576" : "#4a5566", 16 - w / 2, 8 + y, w, 1); }
  px(ctx, "#1a120c", 5, 23, 12, 10);
  px(ctx, "#3a3a44", 7, 24, 8, 2); px(ctx, "#8f929a", 10, 26, 2, 4); px(ctx, "#3a3a44", 7, 30, 8, 2);
  px(ctx, "#5e3b1d", 18, 23, 10, 1);
  for (const x of [19, 23]) { px(ctx, "#f6f0e0", x, 24, 3, 5); px(ctx, "#9a9aa2", x, 25, 3, 1); px(ctx, "#9a9aa2", x, 27, 2, 1); }
  px(ctx, "#2e1d10", 20, 33, 6, 9);
  return c;
};

/** A power station: a brick turbine hall, a tall stack, and lightning-bright windows over a humming dynamo. */
const powerStation: Painter = () => {
  const [c, ctx] = canvas(32, 56);
  px(ctx, "rgba(0,0,0,0.28)", 1, 53, 30, 3);
  bricks(ctx, 1, 26, 30, 28, "#8a4030");
  px(ctx, "#4a4f5a", 0, 22, 32, 4); px(ctx, "#5a606c", 0, 22, 32, 1);
  bricks(ctx, 23, 0, 6, 24, "#6e3226"); px(ctx, "#e8e8ee", 23, 6, 6, 1); px(ctx, "#e8e8ee", 23, 12, 6, 1);
  for (const x of [4, 12]) { px(ctx, "#fff2a0", x, 30, 5, 8); px(ctx, "#ffd84a", x, 34, 5, 4); px(ctx, "#5a3020", x, 30, 5, 1); }
  px(ctx, "#2a2a30", 19, 40, 9, 14); px(ctx, "#3a3a44", 19, 40, 9, 1);
  px(ctx, "#ffe86a", 22, 43, 2, 3); px(ctx, "#ffe86a", 21, 45, 2, 1); px(ctx, "#ffe86a", 23, 46, 2, 3);
  for (const x of [2, 30]) { px(ctx, "#3a3a44", x, 4, 1, 22); px(ctx, "#3a3a44", x - 2, 6, 5, 1); }
  px(ctx, "#2a2a30", 0, 6, 32, 1);
  return c;
};

/** A street lamp: a slim iron post with a glowing glass head. */
const streetLamp: Painter = () => {
  const [c, ctx] = canvas(16, 40);
  px(ctx, "rgba(0,0,0,0.22)", 4, 37, 8, 3);
  px(ctx, "#2a2a30", 6, 34, 4, 4); px(ctx, "#3a3a44", 7, 10, 2, 25);
  px(ctx, "#2a2a30", 4, 8, 8, 2); px(ctx, "#2a2a30", 5, 2, 6, 1);
  px(ctx, "rgba(255,240,160,0.35)", 1, 1, 14, 12);
  px(ctx, "#fff6c8", 5, 3, 6, 5); px(ctx, "#ffe86a", 6, 4, 4, 3);
  return c;
};


// ---------------------------------------------------------------- towns

/** A town hall: a broad brick hall with columns, tall glass windows, a clock in its pediment and a flag on top. */
const townHall: Painter = () => {
  const [c, ctx] = canvas(48, 60);
  px(ctx, "rgba(0,0,0,0.28)", 1, 57, 46, 3);
  px(ctx, "#a89a78", 1, 54, 46, 3); px(ctx, "#c9bc98", 1, 54, 46, 1);
  bricks(ctx, 3, 28, 42, 26, "#b5523a");
  for (const x of [5, 13, 32, 40]) { px(ctx, "#efe6d0", x, 28, 3, 26); px(ctx, "#bfb49a", x + 2, 28, 1, 26); }
  for (const x of [9, 36]) { px(ctx, "#a8d0f0", x, 33, 3, 12); px(ctx, "#cfe6f8", x, 33, 1, 12); px(ctx, "#5e3b1d", x, 39, 3, 1); }
  px(ctx, "#3b2415", 20, 40, 8, 14); px(ctx, "#5a3822", 20, 40, 8, 1); px(ctx, "#e0b04a", 26, 47, 1, 2);
  px(ctx, "#d9cba8", 1, 25, 46, 3); px(ctx, "#a89a78", 1, 27, 46, 1);
  for (let y = 0; y < 12; y++) { const w = 4 + Math.round(y * 3.6); px(ctx, y % 3 ? "#d9cba8" : "#bfb49a", 24 - Math.floor(w / 2), 13 + y, w, 1); }
  px(ctx, "#f6f0e0", 21, 17, 6, 6); px(ctx, "#3a3a44", 23, 18, 1, 3); px(ctx, "#3a3a44", 24, 20, 2, 1);
  px(ctx, "#5e3b1d", 23, 1, 1, 13); px(ctx, "#c84a3a", 24, 2, 7, 4); px(ctx, "#e8d070", 26, 3, 2, 2);
  return c;
};

/** A plaza: a square of paving stones with a stone fountain at its middle, flat on the ground. */
const plaza: Painter = (v) => {
  const [c, ctx] = canvas(48, 48);
  const r = rng(v + 51);
  const slab = ["#b9b4a8", "#aaa59a", "#c4bfb2", "#a09b90"];
  for (let y = 1; y < 47; y += 4) for (let x = 1 + ((y / 4) % 2 ? 2 : 0); x < 47; x += 5) {
    px(ctx, slab[Math.floor(r() * slab.length)], x, y, 4, 3);
  }
  px(ctx, "#8f8a80", 0, 0, 48, 1); px(ctx, "#8f8a80", 0, 47, 48, 1); px(ctx, "#8f8a80", 0, 0, 1, 48); px(ctx, "#8f8a80", 47, 0, 1, 48);
  // the fountain
  px(ctx, "#8f929a", 16, 18, 16, 14); px(ctx, "#b9bcc4", 16, 18, 16, 1);
  px(ctx, "#4a8ad8", 18, 20, 12, 10); px(ctx, "#6aa8f0", 19, 21, 6, 2);
  px(ctx, "#a6a9b1", 22, 13, 4, 9); px(ctx, "#c4c7cf", 22, 13, 4, 1);
  px(ctx, "#9ad0ff", 21, 11, 6, 2); px(ctx, "#cfeaff", 23, 10, 2, 1);
  return c;
};

/** A sand pit: a dug hollow of pale sand by the water, a heap beside it and a spade stuck in. */
const sandPit: Painter = (v, fill) => {
  const [c, ctx] = canvas(32, 32);
  px(ctx, "#d8c48a", 2, 14, 28, 16); px(ctx, "#c8b07a", 4, 16, 24, 12); px(ctx, "#b89a62", 7, 19, 18, 7);
  px(ctx, "#a8865a", 10, 21, 12, 3);
  const heap = fill >= 1 ? 7 : 3;
  for (let y = 0; y < heap; y++) { const w = 4 + y * 2; px(ctx, y % 2 ? "#e8d49a" : "#dcc68c", 25 - w / 2, 14 - heap + y, w, 1); }
  px(ctx, "#6b4526", 8, 6, 1, 9); px(ctx, "#9ea1a9", 7, 14, 3, 3);
  px(ctx, "#8a5a2e", 3, 13, 26, 1);
  return c;
};

/** A tavern: a timber-framed inn with warm-lit windows, a hanging sign with a tankard, and barrels by the door. */
const tavern: Painter = () => {
  const [c, ctx] = canvas(32, 46);
  px(ctx, "rgba(0,0,0,0.25)", 1, 43, 30, 3);
  px(ctx, "#e8dcc0", 3, 22, 26, 21);
  for (const x of [3, 11, 20, 28]) px(ctx, "#5e3b1d", x, 22, 2, 21);
  px(ctx, "#5e3b1d", 3, 22, 26, 2); px(ctx, "#5e3b1d", 3, 31, 26, 1);
  for (const x of [6, 22]) { px(ctx, "#ffd06a", x, 25, 4, 5); px(ctx, "#ffb04a", x, 28, 4, 2); px(ctx, "#5e3b1d", x + 1, 25, 1, 5); }
  px(ctx, "#3b2415", 13, 33, 6, 10); px(ctx, "#5a3822", 13, 33, 6, 1);
  for (let y = 0; y < 12; y++) { const w = 6 + y * 2; px(ctx, y % 2 ? "#6e2e2a" : "#7e3a32", 16 - w / 2, 10 + y, w, 1); }
  bricks(ctx, 23, 4, 4, 10, "#8a4030");
  px(ctx, "#5e3b1d", 0, 26, 4, 1); px(ctx, "#5e3b1d", 1, 27, 1, 2);
  px(ctx, "#a07a4a", 0, 29, 4, 5); px(ctx, "#e8c050", 1, 30, 2, 3);
  for (const x of [24, 28]) { px(ctx, "#8a5a2e", x, 38, 4, 5); px(ctx, "#5e3b1d", x, 39, 4, 1); px(ctx, "#5e3b1d", x, 41, 4, 1); }
  return c;
};

/** A bakery: a brick shop with a striped awning, a domed oven glowing at the side, and loaves in the window. */
const bakery: Painter = () => {
  const [c, ctx] = canvas(32, 42);
  px(ctx, "rgba(0,0,0,0.25)", 1, 39, 30, 3);
  bricks(ctx, 2, 20, 20, 20, "#c98a5a");
  for (let x = 0; x < 22; x++) px(ctx, Math.floor(x / 3) % 2 ? "#f2e2b8" : "#c84a3a", 1 + x, 18, 1, 4);
  px(ctx, "#f2d8a0", 4, 25, 9, 6); px(ctx, "#c08a40", 5, 28, 3, 2); px(ctx, "#a8702a", 9, 27, 3, 3);
  px(ctx, "#3b2415", 15, 28, 5, 12);
  for (let y = 0; y < 8; y++) { const w = 6 + y * 2; px(ctx, y % 2 ? "#6e2e2a" : "#7e3a32", 12 - w / 2, 10 + y, w, 1); }
  for (let y = 0; y < 12; y++) { const w = Math.round(Math.sqrt(Math.max(0, 1 - ((y - 12) / 12) ** 2)) * 10); px(ctx, "#b8704e", 27 - w / 2, 27 + y, w, 1); }
  px(ctx, "#2a1410", 24, 33, 6, 6); px(ctx, "#ff8a2e", 25, 35, 4, 4); px(ctx, "#ffd06a", 26, 36, 2, 2);
  smoke(ctx, 26, 24, 2);
  return c;
};

/** A healer's house: a whitewashed cottage with a green cross over the door and herbs drying under the eaves. */
const healer: Painter = () => {
  const [c, ctx] = canvas(32, 42);
  px(ctx, "rgba(0,0,0,0.25)", 1, 39, 30, 3);
  px(ctx, "#f2efe6", 3, 20, 26, 20); px(ctx, "#d8d4c8", 27, 20, 2, 20);
  for (let y = 0; y < 10; y++) { const w = 8 + Math.round(y * 2.4); px(ctx, y % 2 ? "#4a5566" : "#5a6576", 16 - Math.floor(w / 2), 10 + y, w, 1); }
  px(ctx, "#3a9a5a", 14, 22, 4, 10); px(ctx, "#3a9a5a", 11, 25, 10, 4);
  px(ctx, "#3b2415", 13, 32, 6, 8);
  for (const x of [5, 22]) { px(ctx, "#a8d0f0", x, 25, 5, 5); px(ctx, "#5e3b1d", x + 2, 25, 1, 5); }
  for (let x = 4; x < 28; x += 4) { px(ctx, "#6a9a3a", x, 20, 2, 3); px(ctx, "#8ab05a", x, 21, 1, 1); }
  return c;
};

/** A tailor's: a narrow shop with a bolt-of-cloth sign, a loom in the window and a coat on a stand outside. */
const tailor: Painter = () => {
  const [c, ctx] = canvas(32, 42);
  px(ctx, "rgba(0,0,0,0.25)", 1, 39, 30, 3);
  px(ctx, "#a8784a", 3, 20, 24, 20);
  for (let x = 3; x < 27; x += 4) px(ctx, "#8a5a2e", x, 20, 1, 20);
  for (let y = 0; y < 10; y++) { const w = 6 + Math.round(y * 2.4); px(ctx, y % 2 ? "#3a5a8a" : "#4a6a9a", 15 - Math.floor(w / 2), 10 + y, w, 1); }
  px(ctx, "#f2e2b8", 5, 24, 11, 9); px(ctx, "#6b4526", 6, 25, 1, 7); px(ctx, "#6b4526", 14, 25, 1, 7);
  for (let x = 7; x < 14; x += 2) px(ctx, "#c84a3a", x, 26, 1, 5);
  px(ctx, "#3b2415", 18, 30, 6, 10);
  px(ctx, "#5e3b1d", 28, 30, 1, 10); px(ctx, "#3a6aa8", 26, 27, 5, 9); px(ctx, "#2a4a80", 27, 27, 3, 2);
  px(ctx, "#5e3b1d", 9, 16, 1, 3); px(ctx, "#c84a3a", 6, 17, 7, 3); px(ctx, "#e86a5a", 6, 17, 7, 1);
  return c;
};

/** A park: grass, two round trees, a flower bed and a bench, flat on the ground. */
const park: Painter = () => {
  const [c, ctx] = canvas(32, 40);
  px(ctx, "#6a9a3a", 1, 18, 30, 21); px(ctx, "#7aaa4a", 2, 19, 28, 2);
  for (const [x, y] of [[4, 2], [18, 6]] as [number, number][]) {
    px(ctx, "#5e3b1d", x + 5, y + 12, 2, 12);
    for (let r = 0; r < 7; r++) { const w = 12 - Math.abs(r - 3) * 2; px(ctx, r % 2 ? "#3a7a3a" : "#4a8a3a", x + 6 - w / 2, y + r * 2, w, 2); }
  }
  for (let x = 4; x < 16; x += 2) px(ctx, ["#e84a6a", "#f2d04a", "#e88ad8"][x % 3], x, 33, 1, 1);
  px(ctx, "#8a5a2e", 20, 31, 9, 2); px(ctx, "#6b4526", 20, 33, 1, 3); px(ctx, "#6b4526", 28, 33, 1, 3); px(ctx, "#8a5a2e", 20, 28, 9, 1);
  return c;
};

/** An apartment block: a tall brick building, rows of glass windows, a flat roof with a water tank. */
const apartment: Painter = (v) => {
  const [c, ctx] = canvas(32, 72);
  px(ctx, "rgba(0,0,0,0.28)", 1, 69, 30, 3);
  const base = ["#a8503a", "#9a4a36", "#b5603e"][v % 3];
  bricks(ctx, 2, 10, 28, 60, base);
  px(ctx, "#5a5a66", 1, 8, 30, 3); px(ctx, "#3a3a44", 1, 10, 30, 1);
  px(ctx, "#8f929a", 21, 1, 7, 7); px(ctx, "#6a6a78", 22, 2, 1, 5);
  for (let row = 0; row < 5; row++) for (const x of [5, 13, 21]) {
    const y = 14 + row * 10;
    px(ctx, (row + x) % 3 ? "#a8d0f0" : "#ffd06a", x, y, 6, 6); px(ctx, "#efe6d0", x, y + 6, 6, 1);
  }
  px(ctx, "#3b2415", 13, 62, 6, 8); px(ctx, "#efe6d0", 12, 61, 8, 1);
  return c;
};

/** A university: a grand stone hall with a dome, rows of arched windows and broad steps. */
const university: Painter = () => {
  const [c, ctx] = canvas(48, 66);
  px(ctx, "rgba(0,0,0,0.28)", 1, 63, 46, 3);
  px(ctx, "#a89a78", 2, 59, 44, 4); px(ctx, "#c9bc98", 2, 59, 44, 1); px(ctx, "#bfb49a", 6, 56, 36, 3);
  bricks(ctx, 3, 28, 42, 28, "#c9b48a");
  for (let i = 0; i < 6; i++) { const x = 6 + i * 6; px(ctx, "#a8d0f0", x, 33, 3, 9); px(ctx, "#a8d0f0", x + 1, 32, 1, 1); px(ctx, "#efe6d0", x, 42, 3, 1); }
  for (let i = 0; i < 6; i++) { const x = 6 + i * 6; px(ctx, "#a8d0f0", x, 46, 3, 7); }
  px(ctx, "#3b2415", 21, 44, 6, 12); px(ctx, "#efe6d0", 20, 43, 8, 1);
  px(ctx, "#d9cba8", 1, 25, 46, 3);
  for (let y = 0; y < 14; y++) { const w = Math.round(Math.sqrt(Math.max(0, 1 - ((y - 14) / 14) ** 2)) * 22); px(ctx, y % 4 === 0 ? "#6a8a7a" : "#7a9a8a", 24 - w / 2, 11 + y, w, 1); }
  px(ctx, "#e0b04a", 23, 6, 2, 5); px(ctx, "#e0b04a", 22, 7, 4, 1);
  return c;
};

/** A theatre: a red-and-gold facade with a curtained arch, columns and lanterns either side. */
const theatre: Painter = () => {
  const [c, ctx] = canvas(48, 54);
  px(ctx, "rgba(0,0,0,0.28)", 1, 51, 46, 3);
  bricks(ctx, 2, 18, 44, 33, "#8a3a3a");
  for (const x of [4, 12, 33, 41]) { px(ctx, "#e8d8b0", x, 20, 3, 31); px(ctx, "#c8b890", x + 2, 20, 1, 31); }
  px(ctx, "#2a1010", 16, 24, 16, 27);
  for (let y = 0; y < 6; y++) px(ctx, "#2a1010", 16 + y, 24 - y, 16 - y * 2, 1);
  px(ctx, "#c83a3a", 16, 24, 6, 27); px(ctx, "#c83a3a", 26, 24, 6, 27); px(ctx, "#e85a5a", 17, 25, 1, 25); px(ctx, "#e85a5a", 30, 25, 1, 25);
  px(ctx, "#e0b04a", 2, 15, 44, 3); px(ctx, "#a8802a", 2, 17, 44, 1);
  for (let y = 0; y < 9; y++) { const w = 6 + y * 4; px(ctx, y % 2 ? "#e0b04a" : "#d0a03a", 24 - w / 2, 6 + y, w, 1); }
  for (const x of [8, 37]) { px(ctx, "#3a3a44", x, 30, 1, 6); px(ctx, "#ffd06a", x - 1, 28, 3, 3); }
  return c;
};

/** A harbour: a timber quay on posts, a moored fishing boat and stacked crates and nets. */
const harbour: Painter = () => {
  const [c, ctx] = canvas(32, 34);
  px(ctx, "#3a6aa8", 0, 24, 32, 10); px(ctx, "#5a8ac8", 2, 26, 8, 1); px(ctx, "#5a8ac8", 18, 30, 10, 1);
  px(ctx, "#8a5a2e", 0, 16, 32, 5); px(ctx, "#a0703e", 0, 16, 32, 1);
  for (let x = 1; x < 32; x += 5) px(ctx, "#5e3b1d", x, 21, 2, 10);
  px(ctx, "#a0703e", 20, 10, 5, 6); px(ctx, "#c08a50", 20, 10, 5, 1); px(ctx, "#a0703e", 25, 12, 5, 4);
  px(ctx, "#6a8a6a", 3, 12, 8, 4); px(ctx, "#4a6a4a", 4, 13, 6, 1);
  for (let x = 0; x < 14; x++) px(ctx, "#7a4a2a", 9 + x, 27 + Math.round(Math.abs(x - 7) / 4), 1, 2);
  px(ctx, "#5e3b1d", 15, 18, 1, 9); px(ctx, "#f2e2b8", 16, 19, 5, 6);
  return c;
};

/** A palisade gate: sharpened timber stakes either side of a gate under a lookout walk, a stretch of wall each way. */
const palisade: Painter = () => {
  const [c, ctx] = canvas(32, 40);
  px(ctx, "rgba(0,0,0,0.25)", 0, 37, 32, 3);
  for (let x = 0; x < 32; x += 3) {
    if (x >= 11 && x <= 19) continue;
    const h = 20 + ((x * 7) % 4);
    px(ctx, x % 2 ? "#8a5a2e" : "#7a4a24", x, 38 - h, 3, h);
    px(ctx, "#a0703e", x + 1, 38 - h - 2, 1, 2);
  }
  px(ctx, "#5e3b1d", 0, 26, 32, 2);
  px(ctx, "#6b4526", 10, 8, 2, 30); px(ctx, "#6b4526", 20, 8, 2, 30);
  px(ctx, "#8a5a2e", 8, 8, 16, 3); px(ctx, "#a0703e", 8, 8, 16, 1);
  px(ctx, "#3b2415", 12, 16, 8, 22);
  for (let y = 18; y < 38; y += 4) px(ctx, "#5e3b1d", 12, y, 8, 1);
  px(ctx, "#5e3b1d", 15, 0, 1, 8); px(ctx, "#c84a3a", 16, 1, 5, 3);
  return c;
};

export const PAINTERS: Record<string, Painter> = {
  palisade,
  town_hall: townHall, plaza, sand_pit: sandPit, tavern, bakery, healer, tailor, park, apartment, university, theatre, harbour,
  campfire, hut, brick_house: brickHouse, stockpile, warehouse, outpost, mine, farm, great_library: greatLibrary, lighthouse, aqueduct, workshop, kiln, furnace, library, monument,
  longhouse, two_storey_house: twoStorey, bridge, well, granary, mill, smithy, watchtower, school, bell_tower: bellTower,
  forge, factory, market, shrine, pen, launch_pad: launchPad,
  steam_pump: steamPump, sawmill, printing_press: printingPress, power_station: powerStation, street_lamp: streetLamp,
};

/** Great works are seen going up: their site shows the building rising with the work. */
export const GREAT_WORKS = new Set(["monument", "great_library", "lighthouse", "aqueduct"]);

/** Height (px) a building sprite extends above its footprint: used for depth sorting and labels. */
export function spriteSize(design: string): [number, number] {
  const c = PAINTERS[design]?.(0, 1);
  return c ? [c.width, c.height] : [TS, TS];
}
