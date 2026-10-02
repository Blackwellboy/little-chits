/**
 * The Norse theme's art (Fjordfolk): cool fjord water, mossy uplands, pine and birch, wool-clad villagers and
 * timber halls under turf roofs. Same canvas sizes as the default art, so footprints, depth and labels line up.
 * Nothing here is used unless the server runs with CHITS_THEME=norse (see ../theme.ts).
 */
import { canvas, DEEP, SHALLOW, SAND, GRASS, MEADOW, FOREST, HILLS, ROCK, CLAY, rng, shade, type TerrainPalette } from "./art";
import { bricks, PAINTERS, px, type Painter } from "./buildings";

// ----------------------------------------------------------------- ground

/** Shared by the overview and the minimap, so neither flashes the default palette. */
export const TERRAIN_COLORS: Record<number, string> = {
  [DEEP]: "#254b64", [SHALLOW]: "#4d8697", [SAND]: "#c7c3a9", [GRASS]: "#789477", [MEADOW]: "#96aa7d",
  [FOREST]: "#4d7160", [HILLS]: "#929981", [ROCK]: "#8797a0", [CLAY]: "#a88169",
};

// Keep enough luminance in the ground for people, timber and the night-light pass to read.
export const NORSE_TERRAIN: TerrainPalette = {
  tiles: {
    [DEEP]: ["#254b64", "#203f58"],
    [SHALLOW]: ["#4d8697", "#427889"],
    [SAND]: ["#c7c3a9", "#b9b59c"],
    [GRASS]: ["#789477", "#6a866a"],
    [MEADOW]: ["#96aa7d", "#879c70"],
    [FOREST]: ["#4d7160", "#446553"],
    [HILLS]: ["#929981", "#828c74"],
    [ROCK]: ["#8797a0", "#778791"],
    [CLAY]: ["#a88169", "#96715c"],
  },
  preview: TERRAIN_COLORS,
  minimap: TERRAIN_COLORS,
  flowers: ["#eee9d1", "#b5b4cd", "#c5ad76", "#dce7e4"],
};

// ----------------------------------------------------------------- trees and bushes

/** Spruce and pine, with the occasional silver birch. */
export function treeCanvas(variant: number, size: number): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 24);
  const r = rng(variant * 31 + 5);
  const pine = variant % 4 !== 1;
  const s = 0.55 + 0.45 * size; // grows with amount
  ctx.fillStyle = "rgba(0,0,0,0.22)";
  ctx.fillRect(3, 21, 10, 2);
  ctx.fillStyle = pine ? "#746046" : "#d6d8ce";
  ctx.fillRect(7, 16, 2, 6);
  ctx.fillStyle = "#4e311a";
  ctx.fillRect(8, 16, 1, 6);
  if (pine) {
    const cols = ["#315d51", "#294e46", "#427565"];
    for (let i = 0; i < 4; i++) {
      const w = Math.round((10 - i * 2) * s) + 2;
      const y = 16 - i * 4 * s - 3;
      ctx.fillStyle = cols[i % 3];
      ctx.fillRect(8 - w / 2, y, w, 4);
      ctx.fillStyle = "#6b9680";
      ctx.fillRect(8 - w / 2, y, Math.max(1, w / 3), 1);
    }
  } else {
    const base = ["#769478", "#87a382", "#658569"][variant % 3];
    const rad = 5.5 * s + 1;
    const cy = 11 - (1 - s) * 2;
    for (let y = -7; y <= 7; y++) {
      for (let x = -7; x <= 7; x++) {
        const d = Math.hypot(x * 0.95, y * 1.05);
        if (d <= rad + (r() - 0.5) * 1.2) {
          const light = (-x - y) / 14;
          ctx.fillStyle = light > 0.2 ? shade(base, 0.25) : light < -0.25 ? shade(base, -0.3) : base;
          ctx.fillRect(8 + x, cy + y, 1, 1);
        }
      }
    }
    if (variant % 4 === 1) {
      ctx.fillStyle = "#e05a4a";
      for (let i = 0; i < 3; i++) ctx.fillRect(4 + Math.floor(r() * 8), 7 + Math.floor(r() * 7), 1, 1);
    }
  }
  return c;
}

export function bushCanvas(berries: number, variant: number, winter = false): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  const r = rng(variant * 13 + 1);
  ctx.fillStyle = "rgba(0,0,0,0.2)"; ctx.fillRect(3, 13, 10, 2);
  const base = winter ? "#738376" : "#567b64";
  for (let y = -4; y <= 4; y++) for (let x = -6; x <= 6; x++) {
    if (Math.hypot(x * 0.8, y * 1.2) < 5 + (r() - 0.5)) {
      ctx.fillStyle = (x + y) < -3 ? shade(base, 0.22) : (x + y) > 4 ? shade(base, -0.3) : base;
      ctx.fillRect(8 + x, 9 + y, 1, 1);
    }
  }
  const colors = variant % 2 ? ["#d6334a", "#ff5a6e"] : ["#4b5bd6", "#7f8cff"];
  for (let i = 0; i < berries * 2; i++) {
    const bx = 4 + Math.floor(r() * 9), by = 6 + Math.floor(r() * 6);
    ctx.fillStyle = colors[0]; ctx.fillRect(bx, by, 2, 2);
    ctx.fillStyle = colors[1]; ctx.fillRect(bx, by, 1, 1);
  }
  return c;
}

// ----------------------------------------------------------------- villagers

/** A chit's hue (its stable identity from the server) picks one of eight wool colours. */
export const FOLK_CLOTH = ["#668fa1", "#b59a6c", "#719278", "#a77563", "#7c849e", "#a9b7aa", "#ac8752", "#699b94"];
export function folkVariant(hue: number): number {
  return Math.floor((((hue % 360) + 360) % 360) / 45);
}
export function folkCloth(hue: number): string { return FOLK_CLOTH[folkVariant(hue)]; }

/** Wool tunic, shoulder cloak, leather belt and amber brooch, painted in colour (not tinted). 14×14, like the
 * default body. Some beards, some braids, some wool caps; never horned helmets. */
export function chitBody(hue = 0): HTMLCanvasElement {
  const [c, ctx] = canvas(14, 14);
  const v = folkVariant(hue), cloth = folkCloth(hue);
  const skin = ["#edc7a0", "#dab18c", "#c69a78", "#ebc3a3"][v % 4];
  const hair = ["#c9ac71", "#795641", "#b07a4c", "#d4c5a0"][v % 4];
  const p = (col: string, x: number, y: number, w: number, h = 1) => px(ctx, col, x, y, w, h);
  // a head above a broad, clothed silhouette
  p("#273b3b", 3, 0, 8, 6);
  p(hair, 4, 0, 6, 2); p(hair, 3, 2, 2, 3); p(shade(hair, -0.22), 9, 1, 2, 4);
  p(skin, 5, 2, 4, 4); p(skin, 4, 3, 6, 2);
  p("#273b3b", 2, 6, 10, 8);
  p(cloth, 3, 6, 8, 7); p(shade(cloth, 0.18), 4, 7, 2, 5);
  p(shade(cloth, -0.3), 9, 7, 2, 6);
  // a pine cloak over one shoulder; a linen collar and a brooch part it from the tunic
  p("#3c584f", 1, 6, 3, 6); p("#789180", 2, 6, 3, 2);
  p("#e1dbc0", 5, 6, 4); p("#bd904f", 4, 7, 2, 2); p("#f0cc80", 4, 7, 1);
  p(skin, 11, 9, 2, 2);
  p("#574333", 3, 10, 8, 2); p("#d5b572", 7, 10, 1, 2);
  p("#c2b99e", 4, 13, 2); p("#a59e89", 8, 13, 2);
  if (v % 3 === 1) p(shade(hair, -0.15), 5, 5, 4); // a beard
  if (v % 3 === 2) { // a long side braid bound with wool
    p(hair, 10, 4, 2, 5); p("#e0d4ae", 10, 7, 2); p(shade(hair, -0.2), 11, 5, 1, 4);
  }
  if (v % 4 === 3) { // a low wool cap
    p(shade(cloth, -0.15), 3, 0, 8, 2); p("#e1dbc0", 3, 2, 8);
  }
  return c;
}

export function chitOutline(): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  ctx.fillStyle = "#213336";
  ctx.fillRect(3, 1, 10, 6); ctx.fillRect(1, 7, 13, 7); ctx.fillRect(3, 13, 10, 2);
  return c;
}

export function chitEyes(kind: "open" | "blink" | "sleep" | "happy"): HTMLCanvasElement {
  const [c, ctx] = canvas(10, 4);
  if (kind === "open") {
    ctx.fillStyle = "#f8ecda"; ctx.fillRect(2, 1, 2, 2); ctx.fillRect(6, 1, 2, 2);
    ctx.fillStyle = "#233137"; ctx.fillRect(3, 1, 1, 2); ctx.fillRect(6, 1, 1, 2);
  } else if (kind === "happy") {
    ctx.fillStyle = "#233137"; ctx.fillRect(2, 2, 1, 1); ctx.fillRect(3, 1, 1, 1);
    ctx.fillRect(6, 1, 1, 1); ctx.fillRect(7, 2, 1, 1);
  } else {
    ctx.fillStyle = "#233137"; ctx.fillRect(2, 2, 2, 1); ctx.fillRect(6, 2, 2, 1);
  }
  return c;
}

// ----------------------------------------------------------------- buildings

/** A turf (or thatch) roof: a thick turf lip, timber bargeboards and carved ridge ends. */
function nordicRoof(ctx: CanvasRenderingContext2D, w: number, top: number, bottom: number, v: number, turf = true, ridgeSpan?: number) {
  const r = rng(v + w * 13);
  const cols = turf ? ["#6b8054", "#829669", "#596d49"] : ["#b7a16a", "#c6b780", "#9d8856"];
  const ridge = ridgeSpan ?? (w > 40 ? Math.round(w * 0.38) : 4);
  for (let y = top; y <= bottom; y++) {
    const rw = Math.min(w, ridge + Math.round((w - ridge) * (y - top) / (bottom - top)));
    const x0 = Math.floor((w - rw) / 2);
    for (let x = x0; x < x0 + rw; x++) px(ctx, cols[Math.floor(r() * 3)], x, y);
    if ((y - top) % 4 === 3) px(ctx, turf ? "#50613e" : "#8c794c", x0, y, rw);
    // heavy bargeboards frame both slopes; their light edge reads from far out
    px(ctx, "#4c3d2f", x0, y, 2); px(ctx, "#4c3d2f", x0 + rw - 2, y, 2);
    px(ctx, "#c0a377", x0, y); px(ctx, "#947950", x0 + rw - 1, y);
  }
  px(ctx, "#403c2c", 0, bottom + 1, w, 2);
  px(ctx, turf ? "#9aaa70" : "#d0bd85", 2, bottom, w - 4);
  const left = Math.floor((w - ridge) / 2), right = left + ridge - 1;
  px(ctx, "#64503a", left, top - 1, ridge, 2);
  for (const x of [left, right]) {
    px(ctx, "#473b30", x, top - 3, 1, 3);
    px(ctx, "#bda075", x - (x === left ? 1 : 0), top - 3, 2);
  }
  if (turf) {
    for (let x = left + 2; x < right; x += 3) px(ctx, "#9aaa70", x, top - 2, 1, 2);
  }
}

/** A log-walled hall: a home, a lore hall (with a porch) or a two-floor loft house. */
function nordicHall(w: number, h: number, v: number, style: "home" | "lore" | "loft" = "home"): HTMLCanvasElement {
  const [c, ctx] = canvas(w, h);
  const wallTop = style === "loft" ? 23 : Math.round(h * 0.55);
  const floor = h - 3, center = Math.floor(w / 2);
  const wall = ["#92714f", "#846447", "#9e7b55"][v % 3];
  px(ctx, "rgba(0,0,0,0.25)", 1, h - 4, w - 2, 4);
  px(ctx, "#68757b", 3, floor - 2, w - 6, 3);
  px(ctx, "#a2aaa0", 3, floor - 2, w - 6);
  for (let y = wallTop; y < floor - 2; y += 3) {
    px(ctx, wall, 3, y, w - 6, 2); px(ctx, "#594735", 3, y + 2, w - 6);
    px(ctx, "#b09166", 3, y, w - 7);
  }
  for (const x of [3, w - 5]) { px(ctx, "#463c30", x, wallTop, 2, floor - wallTop); px(ctx, "#aa8b61", x, wallTop, 1, floor - wallTop); }
  if (style === "loft") px(ctx, "#51432f", 3, 40, w - 6, 3);
  // a framed door, an amber latch and a plank step
  px(ctx, "#b5996b", center - 5, floor - 14, 10, 12);
  px(ctx, "#2d302a", center - 4, floor - 13, 8, 11);
  px(ctx, "#71573c", center - 3, floor - 12, 3, 10);
  px(ctx, "#b68c49", center + 2, floor - 8, 1, 2);
  px(ctx, "#b0a68b", center - 6, floor - 2, 12, 2);
  const window = (x: number, y: number) => {
    px(ctx, "#403a2f", x - 1, y - 1, 6, 6);
    px(ctx, "#d7b778", x, y, 4, 4); px(ctx, "#f0db9e", x, y, 2, 2);
    px(ctx, "#645039", x + 2, y, 1, 4); px(ctx, "#645039", x, y + 2, 4, 1);
  };
  window(6, wallTop + 4); window(w - 10, wallTop + 4);
  if (style === "loft") window(6, 45);
  nordicRoof(ctx, w, style === "loft" ? 7 : Math.max(5, wallTop - (style === "lore" ? 12 : 17)), wallTop - 1, v,
    v % 3 !== 2 || style === "lore", style === "lore" ? Math.round(w * 0.38) : undefined);
  if (style === "lore") {
    // a projecting porch tells a lore hall from a home
    for (const x of [center - 9, center + 8]) { px(ctx, "#4b4031", x, floor - 18, 2, 16); px(ctx, "#b49a6c", x, floor - 18, 1, 16); }
    px(ctx, "#516347", center - 10, floor - 18, 20, 3);
    px(ctx, "#a7b27c", center - 11, floor - 19, 22);
    px(ctx, "#4b4031", center - 11, floor - 16, 22);
    // abstract interlace on a board, not lettering
    px(ctx, "#4e4935", center - 5, wallTop + 2, 10, 6);
    for (let i = 0; i < 6; i++) { px(ctx, "#dac28b", center - 3 + i, wallTop + 3 + (i % 3)); px(ctx, "#dac28b", center - 3 + i, wallTop + 6 - (i % 3)); }
  }
  return c;
}

/** A lighthouse in slate and lichen stripes. */
const lighthouse: Painter = () => {
  const [c, ctx] = canvas(32, 64);
  px(ctx, "rgba(0,0,0,0.22)", 2, 60, 28, 4);
  px(ctx, "#7d7a73", 4, 54, 24, 7); px(ctx, "#9b978d", 4, 54, 24, 1);
  for (let y = 16; y < 54; y++) {
    const w = 10 + Math.round((y - 16) * 0.22);
    px(ctx, Math.floor((y - 16) / 6) % 2 ? "#526773" : "#a9b7b5", 16 - Math.floor(w / 2), y, w, 1);
  }
  px(ctx, "#3b2a1c", 14, 47, 4, 7);
  px(ctx, "#2f3640", 9, 14, 14, 2);
  px(ctx, "#ffe59a", 11, 6, 10, 8); px(ctx, "#fff6d0", 13, 7, 4, 5);
  px(ctx, "#2f3640", 10, 4, 12, 2); px(ctx, "#2f3640", 15, 1, 2, 3);
  return c;
};

/** A turf gable over an open timber work porch. */
const workshop: Painter = (v) => {
  const [c, ctx] = canvas(32, 40);
  px(ctx, "rgba(0,0,0,0.25)", 1, 37, 30, 3);
  px(ctx, "#8a8272", 2, 26, 28, 12);
  px(ctx, "#6b4526", 3, 14, 2, 24); px(ctx, "#6b4526", 27, 14, 2, 24);
  nordicRoof(ctx, 32, 5, 16, v);
  px(ctx, "#a0703e", 7, 28, 18, 3); px(ctx, "#6b4526", 8, 31, 2, 6); px(ctx, "#6b4526", 22, 31, 2, 6);
  px(ctx, "#9ea1a9", 11, 26, 4, 2); px(ctx, "#8a5a2e", 17, 25, 1, 3); px(ctx, "#c2c5cc", 18, 25, 2, 1);
  px(ctx, "#9ea1a9", 9, 19, 1, 4); px(ctx, "#9ea1a9", 13, 19, 3, 1); px(ctx, "#8a5a2e", 14, 19, 1, 5);
  return c;
};

const well: Painter = () => {
  const [c, ctx] = canvas(16, 26);
  px(ctx, "rgba(0,0,0,0.25)", 1, 23, 14, 3);
  for (let y = 0; y < 7; y++) px(ctx, ["#b9bcc4", "#9ea1a9", "#8f929a"][y % 3], 2, 16 + y, 12, 1);
  for (let x = 4; x < 14; x += 4) px(ctx, "#767981", x, 17, 1, 5);
  px(ctx, "#a6a9b1", 2, 14, 12, 2); px(ctx, "#1c4a82", 4, 14, 8, 1);
  px(ctx, "#6b4526", 2, 5, 1, 10); px(ctx, "#6b4526", 13, 5, 1, 10);
  px(ctx, "#8a5a2e", 3, 7, 10, 1);
  px(ctx, "#d8c08a", 8, 8, 1, 4); px(ctx, "#8a5a2e", 7, 11, 3, 2); px(ctx, "#6b4526", 7, 12, 3, 1);
  nordicRoof(ctx, 16, 4, 7, 0);
  return c;
};

/** A store-house on mushroom stones, under thatch. */
const granary: Painter = (v) => {
  const [c, ctx] = canvas(32, 42);
  px(ctx, "rgba(0,0,0,0.25)", 2, 39, 28, 3);
  for (const x of [4, 14, 24]) { px(ctx, "#8f929a", x + 1, 33, 3, 7); px(ctx, "#b9bcc4", x, 32, 5, 2); }
  const wall = "#a8784a";
  for (let x = 3; x < 29; x += 3) px(ctx, (x / 3) % 2 ? wall : shade(wall, -0.12), x, 18, 3, 13);
  px(ctx, "#6b4526", 3, 30, 26, 2); px(ctx, "#6b4526", 3, 18, 26, 1);
  px(ctx, "#3b2415", 13, 22, 6, 8); px(ctx, "#d8c08a", 14, 26, 4, 4); px(ctx, "#b89a5a", 14, 26, 4, 1);
  px(ctx, "#8a5a2e", 13, 32, 1, 8); px(ctx, "#8a5a2e", 18, 32, 1, 8);
  for (let y = 33; y < 40; y += 2) px(ctx, "#8a5a2e", 13, y, 6, 1);
  nordicRoof(ctx, 32, 4, 17, v, false);
  return c;
};

const warehouse: Painter = (v, fill) => {
  const [c, ctx] = canvas(32, 36);
  px(ctx, "rgba(0,0,0,0.25)", 1, 33, 30, 3);
  const wall = ["#9a6a3c", "#8f6238", "#a4733f"][v % 3];
  for (let x = 2; x < 30; x += 2) px(ctx, (x / 2) % 2 ? wall : shade(wall, -0.1), x, 14, 2, 19);
  px(ctx, "#5e3b20", 2, 31, 28, 2); px(ctx, "#5e3b20", 2, 14, 28, 1);
  px(ctx, "#2e1d10", 10, 19, 12, 12);
  px(ctx, "#6b4526", 9, 19, 1, 12); px(ctx, "#6b4526", 22, 19, 1, 12);
  const crate = (x: number, y: number) => { px(ctx, "#a0703e", x, y, 4, 4); px(ctx, "#c08a50", x, y, 4, 1); };
  if (fill >= 1) { crate(11, 27); crate(17, 27); }
  if (fill >= 2) { crate(14, 23); }
  if (fill >= 3) { crate(11, 23); crate(17, 23); crate(14, 19); }
  nordicRoof(ctx, 32, 4, 13, v);
  return c;
};

const smithy: Painter = () => {
  const [c, ctx] = canvas(32, 42);
  px(ctx, "rgba(0,0,0,0.25)", 1, 39, 30, 3);
  bricks(ctx, 2, 18, 28, 22, "#8f8a80");
  px(ctx, "#1a120c", 5, 23, 15, 17);
  px(ctx, "#5a3020", 6, 33, 11, 7); px(ctx, "#ff6a1f", 8, 32, 7, 3); px(ctx, "#ffd06a", 10, 32, 3, 2);
  px(ctx, "#9ea1a9", 16, 25, 1, 4); px(ctx, "#9ea1a9", 15, 25, 3, 1); px(ctx, "#c2c5cc", 8, 25, 2, 3);
  px(ctx, "#6a6a78", 22, 33, 8, 1); px(ctx, "#3a3a44", 22, 34, 8, 2); px(ctx, "#3a3a44", 24, 36, 4, 2);
  px(ctx, "#2a2a30", 23, 38, 6, 2); px(ctx, "#6a6a78", 21, 33, 2, 1);
  nordicRoof(ctx, 32, 5, 17, 0);
  px(ctx, "#33333b", 0, 18, 32, 1);
  bricks(ctx, 5, 1, 5, 10, "#7a3a2a");
  return c;
};

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
  for (let y = 0; y < 6; y++) { const w = 2 + y * 3; px(ctx, y % 2 ? "#586a47" : "#8a996c", 10 - Math.floor(w / 2), 7 + y, w, 1); }
  px(ctx, "#5e3b1d", 9, 0, 1, 8); px(ctx, "#e0883a", 10, 1, 6, 3); px(ctx, "#e0883a", 10, 4, 3, 1);
  return c;
};

/** A hall with a teaching board by the door. */
const school: Painter = (v) => {
  const c = nordicHall(32, 46, v);
  const ctx = c.getContext("2d")!;
  px(ctx, "#6f583b", 4, 32, 8, 8); px(ctx, "#2d4a48", 5, 33, 6, 6);
  px(ctx, "#e0ddc5", 6, 34, 4); px(ctx, "#e0ddc5", 6, 36, 2); px(ctx, "#e0ddc5", 9, 37, 1);
  return c;
};

/** The default painters, with the Nordic ones in place of those they restyle. */
export const NORSE_PAINTERS: Record<string, Painter> = {
  ...PAINTERS,
  hut: (v) => nordicHall(32, 42, v, "home"),
  brick_house: (v) => nordicHall(32, 44, v, "home"),
  longhouse: (v) => nordicHall(48, 40, v, "home"),
  two_storey_house: (v) => nordicHall(32, 62, v, "loft"),
  library: (v) => nordicHall(32, 46, v, "lore"),
  great_library: (v) => nordicHall(48, 60, v, "lore"),
  school, lighthouse, workshop, well, granary, warehouse, smithy, watchtower,
};
