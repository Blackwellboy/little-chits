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

export const PAINTERS: Record<string, Painter> = {
  campfire, hut, brick_house: brickHouse, stockpile, warehouse, outpost, mine, farm, great_library: greatLibrary, lighthouse, aqueduct, workshop, kiln, furnace, library, monument,
  longhouse, two_storey_house: twoStorey, bridge, well, granary, mill, smithy, watchtower, school, bell_tower: bellTower,
};

/** Great works are seen going up: their site shows the building rising with the work. */
export const GREAT_WORKS = new Set(["monument", "great_library", "lighthouse", "aqueduct"]);

/** Height (px) a building sprite extends above its footprint: used for depth sorting and labels. */
export function spriteSize(design: string): [number, number] {
  const c = PAINTERS[design]?.(0, 1);
  return c ? [c.width, c.height] : [TS, TS];
}
