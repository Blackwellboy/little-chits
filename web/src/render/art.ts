/**
 * Procedural pixel art. Everything is painted onto canvases at boot: no asset
 * downloads, and every chit, tree and building gets its own small variations.
 */

export const TS = 16; // pixels per world tile

// Tile ids (match server terrain.py)
export const DEEP = 0, SHALLOW = 1, SAND = 2, GRASS = 3, MEADOW = 4, FOREST = 5, HILLS = 6, ROCK = 7, CLAY = 8;
// Resource ids
export const R_WOOD = 1, R_STONE = 2, R_FIBER = 3, R_BERRIES = 4, R_CLAY = 5, R_SAND = 6, R_ORE = 7, R_FISH = 8;

export function rng(seed: number) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0;
    return (s >>> 0) / 4294967296;
  };
}

export function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d")!;
  ctx.imageSmoothingEnabled = false;
  return [c, ctx];
}

function hex(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function mix(a: string, b: string, t: number): string {
  const A = hex(a), B = hex(b);
  const r = (i: number) => Math.round(A[i] + (B[i] - A[i]) * t);
  return `rgb(${r(0)},${r(1)},${r(2)})`;
}
function shade(c: string, k: number): string {
  const [r, g, b] = hex(c);
  const f = (v: number) => Math.max(0, Math.min(255, Math.round(k > 0 ? v + (255 - v) * k : v * (1 + k))));
  return `rgb(${f(r)},${f(g)},${f(b)})`;
}

const TILE_BASE: Record<number, [string, string]> = {
  [DEEP]: ["#1c4a82", "#173f72"],
  [SHALLOW]: ["#2f86bd", "#2a78ab"],
  [SAND]: ["#e8d49a", "#dcc486"],
  [GRASS]: ["#6fae4f", "#63a046"],
  [MEADOW]: ["#8cc053", "#7fb34a"],
  [FOREST]: ["#4a8a3a", "#3f7a31"],
  [HILLS]: ["#98a95f", "#8a9b54"],
  [ROCK]: ["#7f8189", "#6f7179"],
  [CLAY]: ["#b8704e", "#a86244"],
};

const PREVIEW: Record<number, string> = {
  [DEEP]: "#1b4880", [SHALLOW]: "#2e82b8", [SAND]: "#e2cc92", [GRASS]: "#6aa84c", [MEADOW]: "#86ba50",
  [FOREST]: "#467f37", [HILLS]: "#93a45c", [ROCK]: "#7b7d85", [CLAY]: "#b06a4a",
};

/** The ground's colours: a theme (see ../theme.ts) can bring its own. */
export type TerrainPalette = {
  tiles: Record<number, [string, string]>; // two shades per tile, blended by noise
  preview: Record<number, string>; // one pixel per tile, while chunks bake
  minimap: Record<number, string>;
  flowers: string[]; // meadow specks
};

export const DEFAULT_TERRAIN: TerrainPalette = {
  tiles: TILE_BASE,
  preview: PREVIEW,
  minimap: {
    0: "#1c4a82", 1: "#2f86bd", 2: "#e0cc92", 3: "#6fae4f", 4: "#8cc053", 5: "#3f7a31", 6: "#98a95f", 7: "#7f8189", 8: "#b8704e",
  },
  flowers: ["#fff6c2", "#ffd3e8", "#f7e26b", "#ffffff"],
};

/** One pixel per tile: a cheap stand-in shown while the detailed chunks bake. */
export function previewCanvas(tiles: Uint8Array, size: number, pal: TerrainPalette = DEFAULT_TERRAIN): HTMLCanvasElement {
  return pixelCanvas(tiles, size, pal.preview);
}

/** One pixel per tile, written straight into the image (fillRect per tile took ~150 ms on a 512 island). */
export function pixelCanvas(tiles: Uint8Array, size: number, colors: Record<number, string>): HTMLCanvasElement {
  const [c, ctx] = canvas(size, size);
  const img = ctx.createImageData(size, size);
  const px = img.data;
  const lut: number[][] = [];
  const fallback = colors[Number(Object.keys(colors)[0])];
  for (let t = 0; t < 256; t++) {
    const hexs = (colors[t] || fallback).replace("#", "");
    lut[t] = [parseInt(hexs.slice(0, 2), 16), parseInt(hexs.slice(2, 4), 16), parseInt(hexs.slice(4, 6), 16)];
  }
  for (let i = 0; i < size * size; i++) {
    const [r, g, b] = lut[tiles[i]];
    px[i * 4] = r; px[i * 4 + 1] = g; px[i * 4 + 2] = b; px[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

/** A region of the map, in tiles. Baking works per region so big maps load in small chunks. */
export type Region = { x0: number; y0: number; w: number; h: number };

const tileRng = (seed: number, i: number) => rng((seed * 2654435761 + i * 40503 + 12345) >>> 0);

/** Bake terrain for a region: noise shading, soft edges, shore foam, rock relief. */
export function bakeTerrain(tiles: Uint8Array, size: number, seed: number, reg: Region = { x0: 0, y0: 0, w: size, h: size },
  pal: TerrainPalette = DEFAULT_TERRAIN): HTMLCanvasElement {
  const [c, ctx] = canvas(reg.w * TS, reg.h * TS);
  const img = ctx.createImageData(reg.w * TS, reg.h * TS);
  const d = img.data;
  const at = (x: number, y: number) => (x < 0 || y < 0 || x >= size || y >= size ? DEEP : tiles[y * size + x]);
  const baseRGB: Record<number, [number, number, number][]> = {};
  for (const k in pal.tiles) baseRGB[k] = pal.tiles[k].map(hex);
  // low-frequency brightness field for large-scale variation
  const lf = (x: number, y: number) =>
    Math.sin(x * 0.045 + seed) * Math.cos(y * 0.05 - seed * 0.3) * 0.06 + Math.sin((x + y) * 0.013) * 0.04;
  const W = reg.w * TS;
  for (let ty = reg.y0; ty < reg.y0 + reg.h; ty++) {
    for (let tx = reg.x0; tx < reg.x0 + reg.w; tx++) {
      const t = at(tx, ty);
      const r = tileRng(seed, ty * size + tx);
      for (let py = 0; py < TS; py++) {
        for (let px = 0; px < TS; px++) {
          // blend towards neighbour tile near edges (dithered)
          let tt = t;
          const ex = px < 3 ? -1 : px > TS - 4 ? 1 : 0;
          const ey = py < 3 ? -1 : py > TS - 4 ? 1 : 0;
          if ((ex || ey) && r() < 0.35) {
            const nt = at(tx + (r() < 0.5 ? ex : 0), ty + (r() < 0.5 ? ey : 0));
            if (nt !== t && !(t <= SHALLOW) && !(nt <= SHALLOW) && nt !== ROCK && t !== ROCK) tt = nt;
          }
          const [a, b] = baseRGB[tt];
          const k = r();
          let R = a[0] + (b[0] - a[0]) * k, G = a[1] + (b[1] - a[1]) * k, B = a[2] + (b[2] - a[2]) * k;
          const L = 1 + lf(tx + px / TS, ty + py / TS);
          R *= L; G *= L; B *= L;
          const i = (((ty - reg.y0) * TS + py) * W + (tx - reg.x0) * TS + px) * 4;
          d[i] = R; d[i + 1] = G; d[i + 2] = B; d[i + 3] = 255;
        }
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  // details pass
  for (let ty = reg.y0; ty < reg.y0 + reg.h; ty++) {
    for (let tx = reg.x0; tx < reg.x0 + reg.w; tx++) {
      const t = at(tx, ty);
      const r = tileRng(seed + 1, ty * size + tx);
      const X = (tx - reg.x0) * TS, Y = (ty - reg.y0) * TS;
      if (t === GRASS || t === MEADOW || t === FOREST || t === HILLS) {
        const blades = t === FOREST ? 3 : 5;
        for (let i = 0; i < blades; i++) {
          ctx.fillStyle = shade(pal.tiles[t][0], r() < 0.5 ? 0.18 : -0.18);
          const bx = X + Math.floor(r() * 15), by = Y + Math.floor(r() * 14);
          ctx.fillRect(bx, by, 1, 2);
        }
        if (t === MEADOW && r() < 0.6) {
          ctx.fillStyle = pal.flowers[Math.floor(r() * 4)];
          ctx.fillRect(X + Math.floor(r() * 14) + 1, Y + Math.floor(r() * 14) + 1, 1, 1);
        }
        if (t === HILLS && r() < 0.5) {
          ctx.fillStyle = "#7a7a6e";
          ctx.fillRect(X + Math.floor(r() * 13) + 1, Y + Math.floor(r() * 13) + 2, 2, 1);
        }
      }
      if (t === SAND && r() < 0.8) {
        ctx.fillStyle = "#c9b077";
        ctx.fillRect(X + Math.floor(r() * 15), Y + Math.floor(r() * 15), 1, 1);
      }
      if (t === ROCK) {
        // relief: light top edge where the tile above is not rock, dark bottom edge
        if (at(tx, ty - 1) !== ROCK) { ctx.fillStyle = "#a3a5ad"; ctx.fillRect(X, Y, TS, 3); ctx.fillStyle = "#b6b8bf"; ctx.fillRect(X, Y, TS, 1); }
        if (at(tx, ty + 1) !== ROCK) { ctx.fillStyle = "#4e5057"; ctx.fillRect(X, Y + TS - 4, TS, 4); ctx.fillStyle = "#3d3f45"; ctx.fillRect(X, Y + TS - 1, TS, 1); }
        if (at(tx - 1, ty) !== ROCK) { ctx.fillStyle = "#8f9199"; ctx.fillRect(X, Y, 2, TS); }
        if (at(tx + 1, ty) !== ROCK) { ctx.fillStyle = "#5e6068"; ctx.fillRect(X + TS - 2, Y, 2, TS); }
        ctx.fillStyle = "#5c5e66";
        for (let i = 0; i < 3; i++) ctx.fillRect(X + 2 + Math.floor(r() * 11), Y + 3 + Math.floor(r() * 9), 1 + Math.floor(r() * 3), 1);
      }
      if (t === CLAY) {
        ctx.fillStyle = "#cf8a66";
        for (let i = 0; i < 3; i++) ctx.fillRect(X + Math.floor(r() * 13), Y + Math.floor(r() * 13), 3, 1);
      }
      if (t <= SHALLOW) {
        // depth ripples
        ctx.fillStyle = t === DEEP ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.08)";
        if (r() < 0.5) ctx.fillRect(X + Math.floor(r() * 10), Y + Math.floor(r() * 15), 4 + Math.floor(r() * 4), 1);
        // shoreline foam & lighter edge next to land
        for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
          const nt = at(tx + dx, ty + dy);
          if (nt > SHALLOW) {
            for (let i = 0; i < TS; i++) {
              const fx = dx === 0 ? X + i : dx < 0 ? X : X + TS - 1;
              const fy = dy === 0 ? Y + i : dy < 0 ? Y : Y + TS - 1;
              ctx.fillStyle = r() < 0.55 ? "rgba(235,248,255,0.85)" : "rgba(160,215,240,0.6)";
              ctx.fillRect(fx, fy, 1, 1);
              if (r() < 0.4) {
                ctx.fillStyle = "rgba(200,235,250,0.45)";
                ctx.fillRect(fx - dx * 1, fy - dy * 1, 1, 1);
              }
            }
          } else if (t === DEEP && nt === SHALLOW) {
            ctx.fillStyle = "rgba(60,140,190,0.35)";
            if (dx === 0) ctx.fillRect(X, dy < 0 ? Y : Y + TS - 3, TS, 3);
            else ctx.fillRect(dx < 0 ? X : X + TS - 3, Y, 3, TS);
          }
        }
      }
    }
  }
  return c;
}

/** Snow cover for winter: white over land. */
export function bakeSnow(tiles: Uint8Array, size: number, seed: number, reg: Region = { x0: 0, y0: 0, w: size, h: size }): HTMLCanvasElement {
  const [c, ctx] = canvas(reg.w * TS, reg.h * TS);
  for (let ty = reg.y0; ty < reg.y0 + reg.h; ty++) {
    for (let tx = reg.x0; tx < reg.x0 + reg.w; tx++) {
      const t = tiles[ty * size + tx];
      if (t <= SHALLOW) continue;
      const r = tileRng(seed + 99, ty * size + tx);
      const X = (tx - reg.x0) * TS, Y = (ty - reg.y0) * TS;
      ctx.fillStyle = t === ROCK ? "rgba(240,246,255,0.55)" : "rgba(236,243,252,0.78)";
      ctx.fillRect(X, Y, TS, TS);
      for (let i = 0; i < 6; i++) {
        ctx.fillStyle = r() < 0.5 ? "rgba(255,255,255,0.9)" : "rgba(190,205,230,0.6)";
        ctx.fillRect(X + Math.floor(r() * 15), Y + Math.floor(r() * 15), 2, 1);
      }
    }
  }
  return c;
}

/** Autumn tint: warm the vegetation. */
export function bakeAutumn(tiles: Uint8Array, size: number, seed: number, reg: Region = { x0: 0, y0: 0, w: size, h: size }): HTMLCanvasElement {
  const [c, ctx] = canvas(reg.w * TS, reg.h * TS);
  for (let ty = reg.y0; ty < reg.y0 + reg.h; ty++) {
    for (let tx = reg.x0; tx < reg.x0 + reg.w; tx++) {
      const t = tiles[ty * size + tx];
      if (t !== GRASS && t !== MEADOW && t !== FOREST && t !== HILLS) continue;
      const r = tileRng(seed + 7, ty * size + tx);
      const X = (tx - reg.x0) * TS, Y = (ty - reg.y0) * TS;
      ctx.fillStyle = "rgba(214,140,50,0.13)";
      ctx.fillRect(X, Y, TS, TS);
      for (let i = 0; i < 3; i++) {
        ctx.fillStyle = ["#d9822b", "#c2452d", "#e8b04a"][Math.floor(r() * 3)];
        ctx.fillRect(X + Math.floor(r() * 15), Y + Math.floor(r() * 15), 1, 1);
      }
    }
  }
  return c;
}

/** Paths: worn trails and paved roads. Drawn per tile onto an overlay canvas. */
export function drawPath(ctx: CanvasRenderingContext2D, x: number, y: number, level: number, paths: Uint8Array, size: number, ox = 0, oy = 0,
  style: 0 | 1 | 2 = 0) {
  const X = (x - ox) * TS, Y = (y - oy) * TS;
  ctx.clearRect(X, Y, TS, TS);
  if (!level) return;
  const r = rng(x * 928371 + y * 1237 + level);
  const n = (dx: number, dy: number) => {
    const nx = x + dx, ny = y + dy;
    return nx >= 0 && ny >= 0 && nx < size && ny < size && paths[ny * size + nx] > 0;
  };
  if (level === 1) {
    ctx.fillStyle = "rgba(150,118,78,0.55)";
    ctx.fillRect(X + 4, Y + 4, 8, 8);
    if (n(-1, 0)) ctx.fillRect(X, Y + 5, 5, 6);
    if (n(1, 0)) ctx.fillRect(X + 11, Y + 5, 5, 6);
    if (n(0, -1)) ctx.fillRect(X + 5, Y, 6, 5);
    if (n(0, 1)) ctx.fillRect(X + 5, Y + 11, 6, 5);
    ctx.fillStyle = "rgba(120,92,60,0.5)";
    for (let i = 0; i < 4; i++) ctx.fillRect(X + 4 + Math.floor(r() * 8), Y + 4 + Math.floor(r() * 8), 1, 1);
  } else if (style === 2) {  // asphalt, with a dashed line along the road's run (eras.roadStyle)
    ctx.fillStyle = "#3d3f44";
    ctx.fillRect(X, Y, TS, TS);
    ctx.fillStyle = "rgba(255,255,255,0.05)";
    for (let i = 0; i < 6; i++) ctx.fillRect(X + Math.floor(r() * 15), Y + Math.floor(r() * 15), 1, 1);
    const ew = n(-1, 0) || n(1, 0), ns = n(0, -1) || n(0, 1);
    ctx.fillStyle = "#e8d870";
    if (ew && !ns && (x % 2 === 0)) ctx.fillRect(X + 3, Y + 7, 8, 2);
    if (ns && !ew && (y % 2 === 0)) ctx.fillRect(X + 7, Y + 3, 2, 8);
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    if (!n(0, 1)) ctx.fillRect(X, Y + TS - 1, TS, 1);
  } else if (style === 1) {  // macadam: packed crushed stone
    ctx.fillStyle = "#7a7770";
    ctx.fillRect(X, Y, TS, TS);
    for (let i = 0; i < 26; i++) {
      ctx.fillStyle = ["#8e8a80", "#6c6962", "#9a968b"][Math.floor(r() * 3)];
      ctx.fillRect(X + Math.floor(r() * 16), Y + Math.floor(r() * 16), 1, 1);
    }
    ctx.fillStyle = "rgba(0,0,0,0.2)";
    if (!n(0, 1)) ctx.fillRect(X, Y + TS - 1, TS, 1);
  } else {
    ctx.fillStyle = "#8d8a82";
    ctx.fillRect(X, Y, TS, TS);
    for (let py = 0; py < 4; py++) {
      for (let px = 0; px < 4; px++) {
        const off = py % 2 ? 2 : 0;
        ctx.fillStyle = ["#b3afa5", "#a7a398", "#bcb8ae"][Math.floor(r() * 3)];
        ctx.fillRect(X + px * 4 + off, Y + py * 4, 3, 3);
      }
    }
    ctx.fillStyle = "rgba(0,0,0,0.18)";
    if (!n(0, 1)) ctx.fillRect(X, Y + TS - 1, TS, 1);
  }
}

// ----------------------------------------------------------------- resources

export function treeCanvas(variant: number, size: number): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 24);
  const r = rng(variant * 31 + 5);
  const pine = variant % 3 === 0;
  const s = 0.55 + 0.45 * size; // grows with amount
  // shadow
  ctx.fillStyle = "rgba(0,0,0,0.22)";
  ctx.fillRect(3, 21, 10, 2);
  ctx.fillStyle = "#6b4526";
  ctx.fillRect(7, 16, 2, 6);
  ctx.fillStyle = "#4e311a";
  ctx.fillRect(8, 16, 1, 6);
  if (pine) {
    const cols = ["#2f6b3a", "#285e33", "#3d7f46"];
    for (let i = 0; i < 4; i++) {
      const w = Math.round((10 - i * 2) * s) + 2;
      const y = 16 - i * 4 * s - 3;
      ctx.fillStyle = cols[i % 3];
      ctx.fillRect(8 - w / 2, y, w, 4);
      ctx.fillStyle = "#4f9656";
      ctx.fillRect(8 - w / 2, y, Math.max(1, w / 3), 1);
    }
  } else {
    const base = ["#3f8a3e", "#4b9a45", "#36793a"][variant % 3];
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

export function stumpCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 24);
  ctx.fillStyle = "rgba(0,0,0,0.2)"; ctx.fillRect(4, 21, 8, 2);
  ctx.fillStyle = "#6b4526"; ctx.fillRect(6, 18, 4, 4);
  ctx.fillStyle = "#b08a5a"; ctx.fillRect(6, 18, 4, 1);
  return c;
}

export function bushCanvas(berries: number, variant: number, winter = false): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  const r = rng(variant * 13 + 1);
  ctx.fillStyle = "rgba(0,0,0,0.2)"; ctx.fillRect(3, 13, 10, 2);
  const base = winter ? "#6b7a58" : "#3f8f45";
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

export function tuftCanvas(variant: number): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  const r = rng(variant * 7 + 2);
  for (let i = 0; i < 9; i++) {
    const x = 3 + Math.floor(r() * 10);
    const h = 3 + Math.floor(r() * 5);
    ctx.fillStyle = r() < 0.5 ? "#a9c46a" : "#88a84e";
    ctx.fillRect(x, 14 - h, 1, h);
    if (r() < 0.3) { ctx.fillStyle = "#e6d78a"; ctx.fillRect(x, 13 - h, 1, 1); }
  }
  return c;
}

export function boulderCanvas(variant: number): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  const r = rng(variant + 77);
  ctx.fillStyle = "rgba(0,0,0,0.25)"; ctx.fillRect(3, 13, 10, 2);
  for (let y = -4; y <= 3; y++) for (let x = -5; x <= 5; x++) {
    if (Math.hypot(x * 0.9, y * 1.2) < 4.6 + (r() - 0.5)) {
      ctx.fillStyle = y < -2 ? "#b9bcc4" : y > 1 ? "#6b6e76" : "#94979f";
      ctx.fillRect(8 + x, 10 + y, 1, 1);
    }
  }
  return c;
}

export function oreCanvas(variant: number): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  const r = rng(variant + 5);
  for (let i = 0; i < 6; i++) {
    const x = 2 + Math.floor(r() * 11), y = 3 + Math.floor(r() * 10);
    ctx.fillStyle = "#e0883a"; ctx.fillRect(x, y, 2, 1);
    ctx.fillStyle = "#ffbf6a"; ctx.fillRect(x, y, 1, 1);
  }
  return c;
}

export function fishCanvas(frame: number): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  ctx.strokeStyle = `rgba(220,245,255,${0.55 - frame * 0.12})`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.ellipse(8, 8, 2 + frame * 2, 1 + frame, 0, 0, Math.PI * 2);
  ctx.stroke();
  return c;
}

export function sparkleCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(5, 5);
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.fillRect(2, 0, 1, 5); ctx.fillRect(0, 2, 5, 1);
  return c;
}

// ----------------------------------------------------------------- chits

/** HSL to a 0xRRGGBB number, for tinting sprites. */
export function hsl(h: number, s: number, l: number): number {
  s /= 100; l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return (Math.round(f(0) * 255) << 16) | (Math.round(f(8) * 255) << 8) | Math.round(f(4) * 255);
}

/** Grayscale body so it can be tinted per individual. 14x14. */
export function chitBody(): HTMLCanvasElement {
  const [c, ctx] = canvas(14, 14);
  for (let y = 0; y < 14; y++) for (let x = 0; x < 14; x++) {
    const dx = (x - 6.5) / 6.5, dy = (y - 7.2) / 6.3;
    const d = dx * dx + dy * dy;
    if (d > 1) continue;
    let v = 235;
    if (d > 0.72) v = 150; // outline-ish rim
    else if (dx + dy < -0.7) v = 255;
    else if (dy > 0.35) v = 190;
    ctx.fillStyle = `rgb(${v},${v},${v})`;
    ctx.fillRect(x, y, 1, 1);
  }
  // belly
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.fillRect(5, 8, 4, 3);
  return c;
}

/** The body tinted to one chit's hue, for drawing outside Pixi (the inspector's portrait). */
export function tintedChitBody(hue: number): HTMLCanvasElement {
  // draw grayscale then multiply by colour inside the body's alpha
  const [bc, bctx] = canvas(14, 14);
  bctx.drawImage(chitBody(), 0, 0);
  bctx.globalCompositeOperation = "multiply";
  bctx.fillStyle = `hsl(${hue} 58% 64%)`;
  bctx.fillRect(0, 0, 14, 14);
  bctx.globalCompositeOperation = "destination-in";
  bctx.drawImage(chitBody(), 0, 0);
  return bc;
}

export function chitOutline(): HTMLCanvasElement {
  const [c, ctx] = canvas(16, 16);
  for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
    const dx = (x - 7.5) / 7.4, dy = (y - 8.2) / 7.2;
    const d = dx * dx + dy * dy;
    if (d <= 1 && d > 0.74) { ctx.fillStyle = "rgba(20,14,30,0.85)"; ctx.fillRect(x, y, 1, 1); }
  }
  return c;
}

export function chitEyes(kind: "open" | "blink" | "sleep" | "happy"): HTMLCanvasElement {
  const [c, ctx] = canvas(10, 4);
  if (kind === "open") {
    ctx.fillStyle = "#fff"; ctx.fillRect(1, 0, 3, 3); ctx.fillRect(6, 0, 3, 3);
    ctx.fillStyle = "#1a1423"; ctx.fillRect(2, 1, 2, 2); ctx.fillRect(7, 1, 2, 2);
    ctx.fillStyle = "#fff"; ctx.fillRect(2, 1, 1, 1); ctx.fillRect(7, 1, 1, 1);
  } else if (kind === "happy") {
    ctx.fillStyle = "#1a1423"; ctx.fillRect(1, 1, 1, 1); ctx.fillRect(2, 0, 1, 1); ctx.fillRect(3, 1, 1, 1);
    ctx.fillRect(6, 1, 1, 1); ctx.fillRect(7, 0, 1, 1); ctx.fillRect(8, 1, 1, 1);
  } else {
    ctx.fillStyle = "#1a1423"; ctx.fillRect(1, 2, 3, 1); ctx.fillRect(6, 2, 3, 1);
  }
  return c;
}

export function chitFoot(): HTMLCanvasElement {
  const [c, ctx] = canvas(4, 2);
  ctx.fillStyle = "#2a1f2e"; ctx.fillRect(0, 0, 4, 2);
  return c;
}

export function shadowCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(14, 4);
  ctx.fillStyle = "rgba(0,0,0,0.28)";
  ctx.beginPath(); ctx.ellipse(7, 2, 6, 1.8, 0, 0, Math.PI * 2); ctx.fill();
  return c;
}

export function ringCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(24, 10);
  ctx.strokeStyle = "rgba(255,230,120,0.95)"; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.ellipse(12, 5, 10, 3.6, 0, 0, Math.PI * 2); ctx.stroke();
  return c;
}

// ----------------------------------------------------------------- item icons (8x8)

const ICONS: Record<string, (ctx: CanvasRenderingContext2D) => void> = {
  wood: (x) => { x.fillStyle = "#8a5a2e"; x.fillRect(0, 3, 8, 3); x.fillStyle = "#c79a62"; x.fillRect(0, 3, 1, 3); x.fillStyle = "#5e3b1d"; x.fillRect(1, 5, 7, 1); },
  stone: (x) => { x.fillStyle = "#8f929a"; x.fillRect(1, 2, 6, 5); x.fillStyle = "#c2c5cc"; x.fillRect(2, 2, 3, 2); x.fillStyle = "#62656c"; x.fillRect(1, 6, 6, 1); },
  fiber: (x) => { x.fillStyle = "#b7cc6e"; for (let i = 0; i < 4; i++) x.fillRect(1 + i * 2, 1, 1, 6); x.fillStyle = "#8a6a3a"; x.fillRect(0, 4, 8, 1); },
  berries: (x) => { x.fillStyle = "#d6334a"; x.fillRect(1, 3, 3, 3); x.fillRect(4, 2, 3, 3); x.fillRect(3, 5, 3, 2); x.fillStyle = "#ff8a98"; x.fillRect(1, 3, 1, 1); x.fillRect(4, 2, 1, 1); },
  clay: (x) => { x.fillStyle = "#b8704e"; x.fillRect(1, 2, 6, 5); x.fillStyle = "#d69474"; x.fillRect(2, 2, 3, 1); },
  sand: (x) => { x.fillStyle = "#e3c984"; x.fillRect(1, 4, 6, 3); x.fillRect(2, 3, 4, 1); x.fillStyle = "#c9ad68"; x.fillRect(2, 5, 1, 1); x.fillRect(5, 6, 1, 1); },
  ore: (x) => { x.fillStyle = "#6f7179"; x.fillRect(1, 2, 6, 5); x.fillStyle = "#e0883a"; x.fillRect(2, 3, 2, 1); x.fillRect(4, 5, 2, 1); },
  fish: (x) => { x.fillStyle = "#7fb6d6"; x.fillRect(1, 3, 5, 2); x.fillRect(6, 2, 2, 4); x.fillStyle = "#1a1423"; x.fillRect(2, 3, 1, 1); },
  seeds: (x) => { x.fillStyle = "#c7a25a"; x.fillRect(1, 4, 2, 2); x.fillRect(4, 3, 2, 2); x.fillRect(3, 6, 2, 1); },
  grain: (x) => { x.fillStyle = "#e3c15a"; x.fillRect(3, 0, 2, 5); x.fillRect(2, 1, 1, 3); x.fillRect(5, 1, 1, 3); x.fillStyle = "#9a8a3a"; x.fillRect(3, 5, 2, 3); },
  sharp_stone: (x) => { x.fillStyle = "#a6a9b1"; x.fillRect(2, 1, 2, 6); x.fillRect(4, 3, 2, 3); x.fillStyle = "#e6e8ee"; x.fillRect(2, 1, 1, 5); },
  cord: (x) => { x.fillStyle = "#c9a36a"; for (let i = 0; i < 4; i++) x.fillRect(i * 2, i % 2 ? 2 : 4, 2, 2); },
  brick: (x) => { x.fillStyle = "#b5523a"; x.fillRect(0, 2, 8, 4); x.fillStyle = "#d9795c"; x.fillRect(0, 2, 8, 1); x.fillStyle = "#7a3424"; x.fillRect(4, 3, 1, 3); },
  pot: (x) => { x.fillStyle = "#c26a45"; x.fillRect(1, 2, 6, 5); x.fillRect(2, 1, 4, 1); x.fillStyle = "#8a4428"; x.fillRect(1, 6, 6, 1); },
  charcoal: (x) => { x.fillStyle = "#26232a"; x.fillRect(1, 3, 6, 3); x.fillStyle = "#4a4652"; x.fillRect(2, 3, 2, 1); },
  clay_tablet: (x) => { x.fillStyle = "#c98f6a"; x.fillRect(1, 1, 6, 6); x.fillStyle = "#7a4a30"; x.fillRect(2, 2, 4, 1); x.fillRect(2, 4, 3, 1); },
  copper: (x) => { x.fillStyle = "#d9823a"; x.fillRect(1, 3, 6, 3); x.fillStyle = "#ffc07a"; x.fillRect(1, 3, 6, 1); },
  glass: (x) => { x.fillStyle = "rgba(170,220,240,0.9)"; x.fillRect(2, 1, 4, 6); x.fillStyle = "#fff"; x.fillRect(3, 2, 1, 3); },
  bread: (x) => { x.fillStyle = "#c98a3e"; x.fillRect(1, 3, 6, 3); x.fillStyle = "#f0c27a"; x.fillRect(2, 3, 4, 1); },
  cooked_fish: (x) => { x.fillStyle = "#c98050"; x.fillRect(1, 3, 5, 2); x.fillRect(6, 2, 2, 4); },
  berry_tart: (x) => { x.fillStyle = "#d9a55a"; x.fillRect(0, 4, 8, 3); x.fillStyle = "#b8334a"; x.fillRect(1, 3, 6, 2); },
  stone_axe: (x) => { x.fillStyle = "#8a5a2e"; x.fillRect(3, 1, 1, 7); x.fillStyle = "#9ea1a9"; x.fillRect(4, 1, 3, 3); },
  copper_axe: (x) => { x.fillStyle = "#8a5a2e"; x.fillRect(3, 1, 1, 7); x.fillStyle = "#e0883a"; x.fillRect(4, 1, 3, 3); },
  stone_pick: (x) => { x.fillStyle = "#8a5a2e"; x.fillRect(4, 2, 1, 6); x.fillStyle = "#9ea1a9"; x.fillRect(1, 1, 7, 2); },
  copper_pick: (x) => { x.fillStyle = "#8a5a2e"; x.fillRect(4, 2, 1, 6); x.fillStyle = "#e0883a"; x.fillRect(1, 1, 7, 2); },
  spear: (x) => { x.fillStyle = "#8a5a2e"; x.fillRect(1, 6, 1, 1); x.fillRect(2, 5, 1, 1); x.fillRect(3, 4, 1, 1); x.fillRect(4, 3, 1, 1); x.fillStyle = "#c2c5cc"; x.fillRect(5, 1, 2, 2); },
  basket: (x) => { x.fillStyle = "#c79a52"; x.fillRect(1, 3, 6, 4); x.fillStyle = "#8a6a3a"; x.fillRect(1, 5, 6, 1); x.fillRect(2, 1, 4, 1); },
  lantern: (x) => { x.fillStyle = "#e0883a"; x.fillRect(2, 1, 4, 1); x.fillRect(2, 6, 4, 1); x.fillStyle = "#ffe08a"; x.fillRect(2, 2, 4, 4); },
};

/** What a chit pulls behind it when it carries one (views: agent.vehicle): a sled, a cart or a covered wagon. */
export function vehicleCanvas(kind: string): HTMLCanvasElement {
  const [c, ctx] = canvas(18, 12);
  const wood = "#8a5a32", dark = "#5a3a1e", iron = "#3c3c40";
  if (kind === "sled") {
    ctx.fillStyle = wood; ctx.fillRect(2, 5, 13, 3);
    ctx.fillStyle = dark; ctx.fillRect(1, 9, 15, 1); ctx.fillRect(1, 8, 1, 1); ctx.fillRect(15, 8, 2, 1);
    ctx.fillRect(4, 8, 1, 1); ctx.fillRect(12, 8, 1, 1);
    ctx.fillStyle = "#b08050"; ctx.fillRect(3, 3, 10, 2);  // the load
  } else {
    const wagon = kind === "wagon";
    ctx.fillStyle = wood; ctx.fillRect(1, 5, wagon ? 15 : 12, 4);
    ctx.fillStyle = dark; ctx.fillRect(1, 8, wagon ? 15 : 12, 1);
    if (wagon) {  // the canvas cover
      ctx.fillStyle = "#e8e0c8"; ctx.fillRect(2, 1, 13, 4);
      ctx.fillStyle = "#cfc6ac"; ctx.fillRect(5, 1, 1, 4); ctx.fillRect(10, 1, 1, 4);
    }
    const wheel = (wx: number) => {
      ctx.fillStyle = iron; ctx.fillRect(wx, 8, 4, 4);
      ctx.fillStyle = "#9a9080"; ctx.fillRect(wx + 1, 9, 2, 2);
    };
    wheel(2); wheel(wagon ? 11 : 8);
    ctx.fillStyle = dark; ctx.fillRect(wagon ? 16 : 13, 6, 2, 1);  // the shaft
  }
  return c;
}

export function iconCanvas(key: string): HTMLCanvasElement {
  const [c, ctx] = canvas(8, 8);
  (ICONS[key] || ICONS.stone)(ctx);
  return c;
}
export const ICON_KEYS = Object.keys(ICONS);

// ----------------------------------------------------------------- light

export function glowCanvas(size = 64): HTMLCanvasElement {
  const [c, ctx] = canvas(size, size);
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.35, "rgba(255,255,255,0.6)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return c;
}

export function dotCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(3, 3);
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 1, 3, 1); ctx.fillRect(1, 0, 1, 3);
  return c;
}

export function flakeCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(2, 2);
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 2, 2);
  return c;
}

export function leafCanvas(color: string): HTMLCanvasElement {
  const [c, ctx] = canvas(3, 2);
  ctx.fillStyle = color; ctx.fillRect(0, 0, 3, 1); ctx.fillRect(1, 1, 1, 1);
  return c;
}

export { mix, shade };

/** A little wooden sign post: 10×12, the board on top, the post below. */
export function signPostCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(10, 12);
  ctx.fillStyle = "#5a3a22"; ctx.fillRect(4, 5, 2, 7);
  ctx.fillStyle = "#3a2414"; ctx.fillRect(0, 0, 10, 6);
  ctx.fillStyle = "#b07a48"; ctx.fillRect(1, 1, 8, 4);
  ctx.fillStyle = "#8a5a32"; ctx.fillRect(1, 3, 8, 1);
  return c;
}

/** One rain streak (1×6), drawn white and tinted. */
export function rainCanvas(): HTMLCanvasElement {
  const [c, ctx] = canvas(1, 6);
  const g = ctx.createLinearGradient(0, 0, 0, 6);
  g.addColorStop(0, "rgba(255,255,255,0)"); g.addColorStop(1, "rgba(255,255,255,1)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 1, 6);
  return c;
}

/** Animals (T31): small side-on sprites, 12×9, facing right. */
export function animalCanvas(kind: string): HTMLCanvasElement {
  const [c, x] = canvas(12, 9);
  if (kind === "sheep") {
    x.fillStyle = "#f2efe6"; x.fillRect(2, 2, 8, 5); x.fillRect(3, 1, 6, 1);
    x.fillStyle = "#d8d3c6"; x.fillRect(2, 6, 8, 1);
    x.fillStyle = "#3a3440"; x.fillRect(9, 2, 3, 3); x.fillRect(3, 7, 1, 2); x.fillRect(8, 7, 1, 2);
    x.fillStyle = "#fff"; x.fillRect(10, 3, 1, 1);
  } else if (kind === "wolf") {
    x.fillStyle = "#5d6270"; x.fillRect(2, 3, 7, 3); x.fillRect(8, 2, 3, 3); x.fillRect(0, 2, 2, 2);
    x.fillStyle = "#454a57"; x.fillRect(9, 1, 1, 1); x.fillRect(11, 3, 1, 1);
    x.fillRect(3, 6, 1, 3); x.fillRect(7, 6, 1, 3);
    x.fillStyle = "#e8e2c0"; x.fillRect(10, 3, 1, 1);
  } else {
    // deer
    x.fillStyle = "#a8703f"; x.fillRect(2, 3, 7, 3); x.fillRect(8, 1, 2, 3);
    x.fillStyle = "#7a4d28"; x.fillRect(3, 6, 1, 3); x.fillRect(8, 6, 1, 3); x.fillRect(9, 0, 1, 1); x.fillRect(7, 0, 1, 1);
    x.fillStyle = "#f3e2c6"; x.fillRect(2, 5, 6, 1); x.fillRect(1, 3, 1, 1);
    x.fillStyle = "#2a1a10"; x.fillRect(9, 2, 1, 1);
  }
  return c;
}

export function eyesGlowCanvas(): HTMLCanvasElement {
  const [c, x] = canvas(5, 2);
  x.fillStyle = "#ffe36a"; x.fillRect(0, 0, 1, 1); x.fillRect(3, 0, 1, 1);
  return c;
}
