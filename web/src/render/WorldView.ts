import {
  Application, Container, Culler, Graphics, Rectangle, RenderTexture, Sprite, Text, TextStyle, Texture,
  TextureSource,
} from "pixi.js";
import * as A from "./art";
import { flameFrames, GREAT_WORKS } from "./buildings";
import { eraIndex, isLampTile, lampStyle, plazaSpots, statueTint, type Hero } from "./eras";
import { signGlyph, villageLabelVisible, weatherProfile, type WeatherProfile } from "./fx";
import type { AgentState, WorldData } from "../state/world";
import type { StructureView, WorldEvent } from "../types";
import { theme } from "../theme";

const TS = A.TS;
TextureSource.defaultOptions.scaleMode = "nearest";

class Tex {
  private cache = new Map<string, Texture>();
  get(key: string, make: () => HTMLCanvasElement): Texture {
    let t = this.cache.get(key);
    if (!t) { t = Texture.from(make()); this.cache.set(key, t); }
    return t;
  }
  destroy() { for (const t of this.cache.values()) t.destroy(true); this.cache.clear(); }
}

type ChitView = {
  root: Container; body: Sprite; outline: Sprite; eyes: Sprite; feet: [Sprite, Sprite]; shadow: Sprite;
  carry: Sprite; tool: Sprite; basket: Sprite; phase: number; blinkAt: number; lastAct: string;
};

type Chunk = { cx: number; cy: number; terrain?: Sprite; autumn?: Sprite; snow?: Sprite;
  pathCanvas?: HTMLCanvasElement; pathCtx?: CanvasRenderingContext2D; pathTex?: Texture; pathSprite?: Sprite };
const CH = 32;
// below this zoom single trees and plants are too small to see: only the painted ground, buildings and chits
const DETAIL_ZOOM = 0.45;
// below this, the whole-island overview image stands in for the painted terrain chunks
const MAP_ZOOM = 0.3;

/** A moving thing's draw order, rounded so it only changes when it passes a static item's key (trees and
 *  signs sort at multiples of TS, building bottoms at one less): the layer is re-sorted whenever a key changes. */
// buildings whose windows glow at night, and where their chimney smoke rises (tiles from the footprint's corner)
const HOMELIT = new Set(["hut", "brick_house", "library", "longhouse", "two_storey_house", "school"]);
const CHIMNEY: Record<string, [number, number]> = { brick_house: [1.5, 1.4], two_storey_house: [1.55, 2.6], longhouse: [1.5, 1.1] };

function sortKey(u: number): number {
  const m = Math.ceil(u / TS);
  return u > m * TS - 1 ? m * TS - 0.5 : m * TS - 1.5;
}

type StructView = { root: Container; sprite: Sprite | null; extra: Container; key: string; flame?: Sprite; smokeAt: number };
// what a station looks like while someone works a shift at it (worked_until is ahead of the clock)
const WORK_FX: Record<string, { light: number; smoke: boolean; spark: number }> = {
  kiln: { light: 4.5, smoke: true, spark: 0xffb050 },
  furnace: { light: 6, smoke: true, spark: 0xffd070 },
  forge: { light: 6, smoke: true, spark: 0xfff0a0 },
  factory: { light: 3, smoke: true, spark: 0xcfd8ff },
  workshop: { light: 0, smoke: false, spark: 0xd8b070 },
  mill: { light: 0, smoke: false, spark: 0xf4ecd8 },  // flour dust
};

type Particle = { s: Sprite; vx: number; vy: number; life: number; max: number; grow: number; fade: boolean; world: boolean; g: number };

const LABEL = new TextStyle({ fontFamily: "Silkscreen, monospace", fontSize: 11, fill: 0xffffff, stroke: { color: 0x0b0f1a, width: 3 }, align: "center" });
const LABEL_SEL = new TextStyle({ fontFamily: "Silkscreen, monospace", fontSize: 11, fill: 0xffe27a, stroke: { color: 0x0b0f1a, width: 3 }, align: "center" });
const EMOTE = new TextStyle({ fontFamily: "system-ui, 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif", fontSize: 15 });
const BUBBLE = new TextStyle({ fontFamily: "Inter, system-ui, sans-serif", fontSize: 11, fill: 0x1b1626, wordWrap: true, wordWrapWidth: 170, lineHeight: 14 });
const VILLAGE = new TextStyle({ fontFamily: "Silkscreen, monospace", fontSize: 22, fill: 0xfff4dc, stroke: { color: 0x0b0f1a, width: 4 }, letterSpacing: 2 });
const GLYPH = new TextStyle({ fontFamily: "system-ui, 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif", fontSize: 14 });
const FLOAT = new TextStyle({ fontFamily: "Silkscreen, monospace", fontSize: 13, fill: 0xffe27a, stroke: { color: 0x2a1a05, width: 4 } });

export type Selection = { kind: "agent" | "structure"; id: string } | null;

export class WorldView {
  app = new Application();
  private ready = false;
  private destroyed = false;
  private tex = new Tex();
  private data: WorldData | null = null;
  private unlisten: (() => void) | null = null;

  // a render group: the camera moves every frame, and without this pixi recomputed every sprite's transform
  root = new Container({ isRenderGroup: true });
  // Terrain is drawn in CH×CH-tile chunks, baked a few per frame (nearest the camera first),
  // so even very large maps load smoothly and only visible chunks cost anything to draw.
  private preview = new Sprite(); // 1 texel per tile, shown until a chunk is baked
  private terrain = new Container();
  private autumn = new Container();
  private snow = new Container();
  private pathLayer = new Container();
  private chunks = new Map<number, Chunk>();
  private bakeQueue: { key: number; layer: "terrain" | "autumn" | "snow" }[] = [];
  private water = new Container();
  private objects = new Container();
  private fx = new Container();
  private glow = new Container();
  private lightScene = new Container();
  private lightDark = new Graphics();
  private lightRT: RenderTexture | null = null;
  private lightSprite = new Sprite();
  private lightPool: Sprite[] = [];
  private glowPool: Sprite[] = [];
  private screen = new Container();
  private weather = new Container();
  private overlay = new Container();

  private resSprites = new Map<number, Sprite>();
  private sparkles: { s: Sprite; ph: number; sp: number }[] = [];
  private fish: { s: Sprite; i: number; ph: number }[] = [];
  private structs = new Map<string, StructView>();
  private chits = new Map<string, ChitView>();
  private labels = new Map<string, { name: Text; emote: Text; bubble: Container; bubbleText: Text; bubbleBg: Graphics; think: Text; lastSay: string; sel: boolean }>();
  private particles: Particle[] = [];
  private flames: Texture[] = [];
  private flakes: { s: Sprite; vx: number; vy: number; ph: number }[] = [];
  private season = "";
  private wxKey = "";
  private wx: WeatherProfile = weatherProfile("clear", "spring");
  private tintG = new Graphics();
  private flashG = new Graphics();
  private flashAt = -1e9;
  private nextFlash = 0;
  private signViews = new Map<string, { post: Sprite; glyph: Text }>();
  private signsRef: unknown = null;
  private villages: { id: string; name: string; x: number; y: number; rank?: string }[] = [];
  private villageTexts = new Map<string, Text>();
  private villagePoll: ReturnType<typeof setInterval> | null = null;
  // visible eras (eras.ts): the world's age and each age's first maker, and the statues standing for them
  private eraInfo: { index: number; heroes: Hero[] } = { index: 0, heroes: [] };
  private statueSprites: Sprite[] = [];
  private statueKey = "";
  private builtFor = "";
  private cullAt = { x: 0, y: 0, w: 0, h: 0, detail: true, n: "" };
  private detailBuilt = new Set<number>(); // chunks whose trees, plants, sparkles and fish exist
  private fishAt = new Set<number>();
  private onScreen = { trees: [] as Sprite[], sparkles: [] as { s: Sprite; ph: number; sp: number }[], fish: [] as { s: Sprite; i: number; ph: number }[] };

  cam = { x: 0, y: 0, zoom: 3 };
  private camTarget: { x: number; y: number } | null = null;
  selection: Selection = null;
  follow = false;
  /** how dark nights get: normal / soft / off */
  nightMode: "normal" | "soft" | "off" = "normal";
  onSelect: (s: Selection) => void = () => {};
  onCamera: (c: { x: number; y: number; zoom: number; w: number; h: number }) => void = () => {};
  onManual: () => void = () => {}; // a drag or click by the viewer
  onGodClick: ((x: number, y: number) => void) | null = null; // god mode armed: the next click targets a tile
  private groundTexts = new Map<string, Text>();
  private beasts = new Map<string, { s: Sprite; eyes: Sprite; x: number; y: number; tx: number; ty: number; kind: string }>();
  private hover: string | null = null;
  private resizer: ResizeObserver | null = null;
  private t = 0;

  async mount(el: HTMLElement) {
    await this.app.init({
      resizeTo: el, background: "#0b0f1a", antialias: false, autoDensity: true,
      resolution: Math.min(2, window.devicePixelRatio || 1), preference: "webgl",
    });
    if (this.destroyed) { this.app.destroy(true); return; }
    el.appendChild(this.app.canvas);
    this.app.canvas.style.imageRendering = "pixelated";
    // resizeTo only follows window resizes: switching Split -> one world widened the panel and the map stayed
    // drawn in the left half. Follow the element itself.
    this.resizer = new ResizeObserver(() => { if (!this.destroyed) this.app.queueResize(); });  // on the next frame, not mid-rebuild
    this.resizer.observe(el);
    this.flames = flameFrames().map((c) => Texture.from(c));
    this.objects.sortableChildren = true;
    // trees, plants, sparkles and fish are culled by cullDetail; structures and chits are few
    this.objects.cullableChildren = false;
    this.water.cullableChildren = false;
    this.root.addChild(this.preview, this.terrain, this.autumn, this.snow, this.pathLayer, this.water, this.objects, this.fx, this.lightSprite, this.glow);
    this.app.stage.addChild(this.root, this.tintG, this.weather, this.screen, this.overlay, this.flashG);
    this.tintG.eventMode = "none"; this.flashG.eventMode = "none";
    this.lightSprite.eventMode = "none";
    this.lightScene.addChild(this.lightDark);
    this.setupInput();
    this.app.ticker.add((tk) => this.update(tk.deltaMS));
    this.ready = true;
    if (this.data) this.rebuild();
  }

  destroy() {
    this.destroyed = true;
    this.resizer?.disconnect();
    this.unlisten?.();
    if (this.villagePoll) clearInterval(this.villagePoll);
    if (this.ready) {
      this.app.destroy(true, { children: true });
      this.tex.destroy();
    }
  }

  setWorld(data: WorldData, opts: { villages?: boolean } = {}) {
    this.unlisten?.();
    this.data = data;
    this.unlisten = data.listen({
      reset: () => this.rebuild(),
      res: (i) => this.updateRes(i),
      structure: (s) => this.updateStructure(s),
      removed: (id) => this.removeStructure(id),
      paths: (i, lvl) => this.updatePath(i, lvl),
      events: (evs) => this.onEvents(evs),
      agentGone: (id) => this.removeChit(id),
    });
    if (this.ready && data.ready) this.rebuild();
    // village names come from the server's settlement detection; they change slowly
    if (this.villagePoll) clearInterval(this.villagePoll);
    this.villages = [];
    if (opts.villages === false) return;
    const poll = () => {
      fetch(`/api/worlds/${data.id}/settlements`).then((r) => (r.ok ? r.json() : [])).then((v) => { this.villages = v || []; this.placeStatues(); }).catch(() => {});
      fetch(`/api/worlds/${data.id}/eras`).then((r) => (r.ok ? r.json() : null)).then((e) => { if (e) { this.eraInfo = e; this.placeStatues(); } }).catch(() => {});
    };
    poll();
    this.villagePoll = setInterval(poll, 10000);
  }

  // ------------------------------------------------------------------ building the scene
  private rebuild() {
    const d = this.data;
    if (!d || !d.ready || !this.ready) return;
    const size = d.size;
    // Detach in bulk before destroying: removing ~50,000 sprites one at a time searches the whole child list
    // for each (seconds on a 512 island). Structures and chits live in the same layer and are destroyed below.
    this.objects.removeChildren();
    for (const s of this.statueSprites) s.destroy();
    this.statueSprites = [];
    this.statueKey = "";  // (placed again by the next poll)
    for (const s of this.resSprites.values()) s.destroy();
    this.resSprites.clear();
    this.detailBuilt.clear();
    this.fishAt.clear();
    for (const v of this.structs.values()) v.root.destroy({ children: true });
    this.structs.clear();
    for (const c of this.chits.values()) c.root.destroy({ children: true });
    this.chits.clear();
    for (const l of this.labels.values()) { l.name.destroy(); l.emote.destroy(); l.bubble.destroy({ children: true }); l.think.destroy(); }
    this.labels.clear();
    this.water.removeChildren().forEach((c) => c.destroy());
    this.sparkles = []; this.fish = [];
    this.cullAt.n = ""; // every sprite is new: cull again
    this.onScreen = { trees: [], sparkles: [], fish: [] };
    for (const t of this.groundTexts.values()) t.destroy();
    this.groundTexts.clear();
    for (const b of this.beasts.values()) { b.s.destroy(); b.eyes.destroy(); }
    this.beasts.clear();
    for (const v of this.signViews.values()) { v.post.destroy(); v.glyph.destroy(); }
    this.signViews.clear(); this.signsRef = null;

    this.resetChunks();
    this.preview.texture?.destroy(true);
    this.preview.texture = Texture.from(A.previewCanvas(d.tiles, size, theme().terrain));
    this.preview.scale.set(TS);
    this.autumn.alpha = 0; this.snow.alpha = 0;
    this.seasonQueued = { autumn: false, snow: false };
    for (let cy = 0; cy < Math.ceil(size / CH); cy++)
      for (let cx = 0; cx < Math.ceil(size / CH); cx++) {
        const key = cy * 1000 + cx;
        this.chunks.set(key, { cx, cy });
        this.bakeQueue.push({ key, layer: "terrain" });
      }
    for (let i = 0; i < size * size; i++) if (d.paths[i]) this.drawPathTile(i % size, Math.floor(i / size));
    this.flushPaths();

    // trees, plants, sparkles and fish are made per chunk as the camera comes near (ensureDetail)
    for (const s of d.structures.values()) this.updateStructure(s);

    // lighting target: 2 texels per tile, linear filtering for soft light
    this.lightRT?.destroy(true);
    this.lightRT = RenderTexture.create({ width: size * 2, height: size * 2, scaleMode: "linear" });
    this.lightSprite.texture = this.lightRT;
    this.lightSprite.scale.set(TS / 2);
    this.lightDark.clear().rect(0, 0, size * 2, size * 2).fill(0x0a0f2c);

    const builtFor = `${d.meta.seed}:${size}`;
    if (this.builtFor !== builtFor) this.camTarget = null; // a new island: recenter on its chits
    this.builtFor = builtFor;
    if (!this.camTarget) {
      let sx = 0, sy = 0, n = 0;
      for (const a of d.agents.values()) { sx += a.x; sy += a.y; n++; }
      const cx = n ? sx / n : size / 2, cy = n ? sy / n : size / 2;
      this.cam.x = cx * TS; this.cam.y = cy * TS;
      this.camTarget = { x: this.cam.x, y: this.cam.y };
    }
    this.season = "";
    this.wxKey = "";
  }

  private resTexture(i: number): { tex: Texture | null; tree: boolean; dy: number } {
    const d = this.data!;
    const k = d.resKind[i], amt = d.resAmt[i], t = d.tiles[i];
    const v = (i * 2654435761) >>> 0;
    const winter = d.clock?.season === "winter";
    switch (k) {
      case A.R_WOOD:
        if (amt <= 0) return { tex: this.tex.get("stump", A.stumpCanvas), tree: false, dy: 4 };
        {
          const sz = amt >= 4 ? 1 : amt >= 2 ? 0.6 : 0.3;
          return { tex: this.tex.get(`tree${v % 6}_${sz}`, () => theme().tree(v % 6, sz)), tree: true, dy: 4 };
        }
      case A.R_BERRIES:
        return { tex: this.tex.get(`bush${v % 2}_${Math.min(4, amt)}_${winter}`, () => theme().bush(Math.min(4, amt), v % 2, winter)), tree: false, dy: 2 };
      case A.R_FIBER:
        return amt > 0 ? { tex: this.tex.get(`tuft${v % 4}`, () => A.tuftCanvas(v % 4)), tree: false, dy: 1 } : { tex: null, tree: false, dy: 0 };
      case A.R_STONE:
        if (t === A.ROCK || amt <= 0) return { tex: null, tree: false, dy: 0 };
        return { tex: this.tex.get(`boulder${v % 3}`, () => A.boulderCanvas(v % 3)), tree: false, dy: 1 };
      case A.R_ORE:
        return amt > 0 ? { tex: this.tex.get(`ore${v % 3}`, () => A.oreCanvas(v % 3)), tree: false, dy: -99 } : { tex: null, tree: false, dy: 0 };
      default:
        return { tex: null, tree: false, dy: 0 };
    }
  }

  private chunkOf(i: number) {
    const size = this.data!.size;
    return Math.floor(Math.floor(i / size) / CH) * 1000 + Math.floor((i % size) / CH);
  }

  /** Make the trees, plants, water sparkles and fish of the chunks on or next to the screen, a few per frame.
   *  Making all ~60,000 at once on a 512 island froze the page for seconds on every snapshot. */
  private ensureDetail(view: Rectangle, budgetMs: number) {
    const size = this.data!.size;
    const span = CH * TS, n = Math.ceil(size / CH);
    const cx0 = Math.max(0, Math.floor((view.x - span) / span)), cx1 = Math.min(n - 1, Math.floor((view.x + view.width + span) / span));
    const cy0 = Math.max(0, Math.floor((view.y - span) / span)), cy1 = Math.min(n - 1, Math.floor((view.y + view.height + span) / span));
    const t0 = performance.now();
    for (let cy = cy0; cy <= cy1; cy++)
      for (let cx = cx0; cx <= cx1; cx++) {
        if (this.detailBuilt.has(cy * 1000 + cx)) continue;
        if (performance.now() - t0 > budgetMs) return;
        this.buildDetail(cx, cy);
      }
  }

  /** Unmake the detail of chunks far from the view once many exist: panning (or the director) used to build
   *  every chunk of a 512 island, ~60,000 sprites the scene graph then paid for every frame. */
  private evictDetail(view: Rectangle) {
    if (this.resSprites.size + this.sparkles.length + this.fish.length < 20000) return;
    const span = CH * TS, pad = span * 3;
    const drop = new Set<number>();
    for (const key of this.detailBuilt) {
      const cx = key % 1000, cy = Math.floor(key / 1000);
      if (cx * span + span < view.x - pad || cx * span > view.x + view.width + pad
          || cy * span + span < view.y - pad || cy * span > view.y + view.height + pad) drop.add(key);
    }
    if (!drop.size) return;
    const gone = new Set<Sprite>();
    for (const [i, s] of this.resSprites) if (drop.has(this.chunkOf(i))) { gone.add(s); this.resSprites.delete(i); }
    const at = (x: number, y: number) => Math.floor(y / span) * 1000 + Math.floor(x / span);
    this.sparkles = this.sparkles.filter((sp) => (drop.has(at(sp.s.x, sp.s.y)) ? (gone.add(sp.s), false) : true));
    this.fish = this.fish.filter((f) => (drop.has(this.chunkOf(f.i)) ? (gone.add(f.s), this.fishAt.delete(f.i), false) : true));
    // detach in bulk (removing one child at a time searches the whole list each time)
    for (const layer of [this.objects, this.water]) {
      const keep = layer.children.filter((c) => !gone.has(c as Sprite));
      if (keep.length === layer.children.length) continue;
      layer.removeChildren();
      for (const c of keep) layer.addChild(c);
    }
    for (const s of gone) { s.removeFromParent(); s.destroy(); }
    for (const key of drop) this.detailBuilt.delete(key);
  }

  private buildDetail(cx: number, cy: number) {
    const d = this.data!;
    const size = d.size;
    this.detailBuilt.add(cy * 1000 + cx);
    const sparkTex = this.tex.get("sparkle", A.sparkleCanvas);
    const seed = d.meta.seed | 0;
    for (let y = cy * CH; y < Math.min(size, (cy + 1) * CH); y++)
      for (let x = cx * CH; x < Math.min(size, (cx + 1) * CH); x++) {
        const i = y * size + x;
        // per-tile randomness, so a chunk looks the same whenever and in whatever order it's made
        const r = (k: number) => (Math.imul((i + 1) ^ (seed + k * 0x9e3779b1), 2654435761) >>> 0) / 4294967296;
        if (d.tiles[i] <= A.SHALLOW && r(5) < 0.05) {
          const s = new Sprite(sparkTex);
          s.position.set(x * TS + r(6) * 12, y * TS + r(7) * 12);
          s.alpha = 0;
          this.water.addChild(s);
          this.sparkles.push({ s, ph: r(8) * 10, sp: 0.6 + r(9) * 1.2 });
        }
        this.updateRes(i);
      }
  }

  private updateRes(i: number) {
    const d = this.data!;
    const size = d.size;
    if (!this.detailBuilt.has(this.chunkOf(i))) return; // made later, from the latest data, when it comes into view
    const k = d.resKind[i];
    if (k === A.R_FISH) {
      if (!this.fishAt.has(i) && d.resAmt[i] > 0) {
        const s = new Sprite(this.tex.get("fish0", () => A.fishCanvas(0)));
        s.position.set((i % size) * TS, Math.floor(i / size) * TS);
        s.alpha = 0;
        this.water.addChild(s);
        this.fish.push({ s, i, ph: Math.random() * 20 });
        this.fishAt.add(i);
      }
      return;
    }
    const { tex, tree, dy } = this.resTexture(i);
    let s = this.resSprites.get(i);
    if (!tex) {
      if (s) { s.destroy(); this.resSprites.delete(i); }
      return;
    }
    if (!s) {
      s = new Sprite(tex);
      s.cullable = true;
      const x = (i % size) * TS, y = Math.floor(i / size) * TS;
      if (dy === -99) { s.anchor.set(0, 0); s.position.set(x, y); s.zIndex = -1; this.root.addChildAt(s, 4); }
      else {
        s.anchor.set(0.5, 1);
        const jx = ((i * 7919) % 5) - 2;
        s.position.set(x + TS / 2 + jx, y + TS + dy);
        s.zIndex = y + TS;
        this.objects.addChild(s);
      }
      this.resSprites.set(i, s);
    } else {
      s.texture = tex;
    }
    (s as any)._tree = tree;
  }

  // ------------------------------------------------------------------ chunked terrain
  private resetChunks() {
    for (const c of this.chunks.values()) {
      for (const sp of [c.terrain, c.autumn, c.snow, c.pathSprite]) sp?.destroy({ texture: true, textureSource: true });
    }
    this.chunks.clear();
    this.bakeQueue = [];
    for (const layer of [this.terrain, this.autumn, this.snow, this.pathLayer]) layer.removeChildren();
  }

  private chunkRegion(c: Chunk): A.Region {
    const size = this.data!.size;
    return { x0: c.cx * CH, y0: c.cy * CH, w: Math.min(CH, size - c.cx * CH), h: Math.min(CH, size - c.cy * CH) };
  }

  /** Bake queued chunks within a small time budget, only those on (or next to) the screen: a 512 island has
   *  256 chunks per layer at up to ~30 ms each, and a season change used to repaint all of them. Off-screen
   *  chunks wait (the 1-texel preview covers them) until the camera comes their way. */
  private bakeSome(budgetMs: number, view: Rectangle) {
    if (!this.bakeQueue.length) return;
    const d = this.data!;
    const span = CH * TS;
    const near = (c: Chunk) => c.cx * span + span >= view.x - span && c.cx * span <= view.x + view.width + span
      && c.cy * span + span >= view.y - span && c.cy * span <= view.y + view.height + span;
    const t0 = performance.now();
    for (let i = 0; i < this.bakeQueue.length && performance.now() - t0 < budgetMs;) {
      const q = this.bakeQueue[i];
      const c = this.chunks.get(q.key);
      if (!c || c[q.layer]) { this.bakeQueue.splice(i, 1); continue; }
      if (!near(c)) { i++; continue; }
      this.bakeQueue.splice(i, 1);
      const reg = this.chunkRegion(c);
      const baked = q.layer === "terrain" ? A.bakeTerrain(d.tiles, d.size, d.meta.seed, reg, theme().terrain)
        : (q.layer === "autumn" ? A.bakeAutumn : A.bakeSnow)(d.tiles, d.size, d.meta.seed, reg);
      const sp = new Sprite(Texture.from(baked));
      sp.position.set(reg.x0 * TS, reg.y0 * TS);
      sp.cullable = true;
      c[q.layer] = sp;
      (q.layer === "terrain" ? this.terrain : q.layer === "autumn" ? this.autumn : this.snow).addChild(sp);
    }
  }

  /** Seasonal overlays are only baked once a season needs them. */
  private seasonQueued = { autumn: false, snow: false };

  private queueSeasonLayer(layer: "autumn" | "snow") {
    if (this.seasonQueued[layer]) return; // (it used to rescan every chunk against the whole queue every frame)
    this.seasonQueued[layer] = true;
    for (const [key, c] of this.chunks) if (!c[layer]) this.bakeQueue.push({ key, layer });
  }

  /** Out of season and faded out: give the overlay's chunk textures back. */
  private freeSeasonLayer(layer: "autumn" | "snow") {
    if (!this.seasonQueued[layer]) return;
    this.seasonQueued[layer] = false;
    for (const c of this.chunks.values()) {
      c[layer]?.destroy({ texture: true, textureSource: true });
      c[layer] = undefined;
    }
    this.bakeQueue = this.bakeQueue.filter((q) => q.layer !== layer);
  }

  private dirtyPaths = new Set<Chunk>();

  private drawPathTile(x: number, y: number) {
    const d = this.data!;
    const c = this.chunks.get(Math.floor(y / CH) * 1000 + Math.floor(x / CH));
    if (!c) return;
    if (!c.pathCtx) {
      const reg = this.chunkRegion(c);
      [c.pathCanvas, c.pathCtx] = A.canvas(reg.w * TS, reg.h * TS);
    }
    A.drawPath(c.pathCtx!, x, y, d.paths[y * d.size + x], d.paths, d.size, c.cx * CH, c.cy * CH);
    this.dirtyPaths.add(c);
  }

  private flushPaths() {
    for (const c of this.dirtyPaths) {
      if (!c.pathTex) {
        c.pathTex = Texture.from(c.pathCanvas!);
        c.pathSprite = new Sprite(c.pathTex);
        c.pathSprite.position.set(c.cx * CH * TS, c.cy * CH * TS);
        c.pathSprite.cullable = true;
        this.pathLayer.addChild(c.pathSprite);
      } else c.pathTex.source.update();
    }
    this.dirtyPaths.clear();
  }

  private updatePath(i: number, lvl: number) {
    const d = this.data!;
    const size = d.size;
    const x = i % size, y = Math.floor(i / size);
    for (const [dx, dy] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= size || ny >= size) continue;
      this.drawPathTile(nx, ny);
    }
    this.flushPaths();
  }

  private structKey(s: StructureView): string {
    if (!s.complete) return `site`;
    let st = 1;
    if (s.design === "campfire") st = s.lit ? 1 : 0;
    if (s.design === "farm") st = !s.planted ? 0 : s.growth >= 1 ? 3 : s.growth > 0.4 ? 2 : 1;
    if (s.design === "stockpile" || s.design === "outpost") st = s.stored <= 0 ? 0 : s.stored < 40 ? 1 : s.stored < 120 ? 2 : 3;
    if (s.design === "warehouse") st = s.stored <= 0 ? 0 : s.stored < 160 ? 1 : s.stored < 480 ? 2 : 3;  // four times the room
    if (s.design === "mine") st = s.stored <= 0 ? 0 : s.stored < 6 ? 1 : s.stored < 12 ? 2 : 3;  // ore in the seam
    if (s.design === "sand_pit") st = s.stored <= 0 ? 0 : 1;  // sand to dig (an empty pit showed its heap, Codex #32)
    if (s.design === "bridge") st = (s.h > s.w ? 10 : 0) + Math.max(s.w, s.h); // which way it runs, how long
    // a home being rebuilt bigger: scaffolding redrawn as the work goes on
    const up = s.upgrade ? `:u${Math.round(s.upgrade.progress * 8)}${Object.keys(s.upgrade.needs).length ? "n" : ""}` : "";
    return `${s.design}:${st}:${s.ruined ? "r" : ""}${up}`;
  }

  private updateStructure(s: StructureView) {
    const key = this.structKey(s);
    let v = this.structs.get(s.id);
    const variant = parseInt(s.id.replace(/\D/g, "") || "0", 10);
    if (!v) {
      const root = new Container();
      root.cullable = true;
      const extra = new Container();
      root.addChild(extra);
      v = { root, sprite: null, extra, key: "", smokeAt: 0 };
      this.structs.set(s.id, v);
      this.objects.addChild(root);
    }
    const bottom = (s.y + s.h) * TS;
    v.root.position.set(s.x * TS, bottom);
    // a bridge lies flat on the water: whoever walks over it is drawn on top
    v.root.zIndex = s.design === "bridge" || s.design === "plaza" ? s.y * TS - 2 : bottom - 1;
    if (v.key !== key || !s.complete) {
      v.extra.removeChildren().forEach((c) => c.destroy());
      v.flame = undefined;
      if (v.sprite) { v.sprite.destroy(); v.sprite = null; }
      const paint = theme().painters[s.design];
      if (s.complete && paint) {
        const [, st, ru] = key.split(":");
        const tex = this.tex.get(`b:${s.design}:${variant % 3}:${st}`, () => paint(variant % 3, +st));
        const sp = new Sprite(tex);
        sp.anchor.set(0, 1);
        sp.x = (s.w * TS - tex.width) / 2;
        if (ru) { sp.tint = 0x8a8a8a; sp.alpha = 0.85; sp.skew.x = -0.04; }
        v.root.addChildAt(sp, 0);
        v.sprite = sp;
        if (s.upgrade) this.drawUpgrade(v.extra, s, tex.height);
        if (s.design === "campfire" && s.lit) {
          const f = new Sprite(this.flames[0]);
          f.anchor.set(0.5, 1);
          f.position.set(TS / 2, -5);
          v.extra.addChild(f);
          v.flame = f;
        }
      } else if (!s.complete) {
        this.drawSite(v.extra, s);
      }
      v.key = key;
    }
  }

  private drawSite(c: Container, s: StructureView) {
    const g = new Graphics();
    const w = s.w * TS, h = s.h * TS;
    const p = s.progress;
    const need = Object.values(s.needs).reduce((a, b) => a + b, 0);
    // foundation
    g.rect(1, -h + 1, w - 2, h - 2).fill({ color: 0x8a6a45, alpha: 0.55 });
    for (let x = 0; x < w; x += 4) { g.rect(x, -h, 2, 1).fill(0xf2e2b8); g.rect(x, -1, 2, 1).fill(0xf2e2b8); }
    for (let y = 0; y < h; y += 4) { g.rect(0, -h + y, 1, 2).fill(0xf2e2b8); g.rect(w - 1, -h + y, 1, 2).fill(0xf2e2b8); }
    // a great work: the building itself rises with the work, from the ground up
    const paint = theme().painters[s.design];
    if (GREAT_WORKS.has(s.design) && p > 0.02 && paint) {
      const tex = this.tex.get(`${s.design}:0`, () => paint(0, 0));
      const spr = new Sprite(tex);
      spr.anchor.set(0, 1);
      spr.alpha = 0.9;
      const shown = Math.round(tex.height * Math.min(1, p));
      const m = new Graphics().rect(0, -shown, tex.width, shown).fill(0xffffff);
      spr.mask = m;
      c.addChild(spr, m);
    }
    // scaffold rising with progress
    const H = Math.round(6 + p * (h + 10));
    g.rect(2, -H, 2, H).fill(0xa0703e); g.rect(w - 4, -H, 2, H).fill(0xa0703e);
    for (let y = 4; y < H; y += 6) g.rect(2, -y, w - 4, 1).fill(0xc08a50);
    if (p > 0.1) g.rect(4, -Math.round(p * h * 0.8) - 2, w - 8, Math.round(p * h * 0.8)).fill({ color: 0xc9a06a, alpha: 0.8 });
    // material piles waiting
    if (need > 0) { g.rect(w / 2 - 3, -5, 6, 3).fill(0x6b4526); }
    // progress bar
    g.roundRect(0, -H - 7, w, 4, 2).fill({ color: 0x000000, alpha: 0.55 });
    g.roundRect(0, -H - 7, Math.max(2, w * (need > 0 ? 0.02 + 0.3 * (1 - need / 40) : p)), 4, 2).fill(need > 0 ? 0xf2b84b : 0x7fe07a);
    c.addChild(g);
  }

  /** Scaffolding round a home that is being rebuilt bigger, and a bar for how far the work is. */
  private drawUpgrade(c: Container, s: StructureView, spriteH: number) {
    const up = s.upgrade!;
    const g = new Graphics();
    const w = s.w * TS, H = Math.round(spriteH * (0.45 + 0.5 * up.progress));
    const waiting = Object.keys(up.needs).length > 0;
    for (const x of [-1, w - 1]) g.rect(x, -H, 2, H).fill(0xa0703e);
    for (let y = 6; y < H; y += 8) g.rect(-1, -y, w + 1, 1).fill(0xc08a50);
    if (waiting) g.rect(w / 2 - 4, -4, 8, 3).fill(0x6b4526); // materials still to come
    g.roundRect(0, -spriteH - 7, w, 4, 2).fill({ color: 0x000000, alpha: 0.55 });
    g.roundRect(0, -spriteH - 7, Math.max(2, w * (waiting ? 0.05 : up.progress)), 4, 2).fill(waiting ? 0xf2b84b : 0x7fe07a);
    c.addChild(g);
  }

  private removeStructure(id: string) {
    const v = this.structs.get(id);
    if (v) { v.root.destroy({ children: true }); this.structs.delete(id); }
  }

  // ------------------------------------------------------------------ chits
  private makeChit(a: AgentState): ChitView {
    const root = new Container();
    root.cullable = true;
    const shadow = new Sprite(this.tex.get("shadow", A.shadowCanvas)); shadow.anchor.set(0.5, 0.5); shadow.y = -1;
    const footTex = this.tex.get("foot", A.chitFoot);
    const f1 = new Sprite(footTex), f2 = new Sprite(footTex);
    f1.anchor.set(0.5, 1); f2.anchor.set(0.5, 1);
    const look = theme().chit.body(a.hue);
    const body = new Sprite(this.tex.get(look.key, look.paint)); body.anchor.set(0.5, 1);
    body.tint = look.tint;
    const outline = new Sprite(this.tex.get("outline", theme().chit.outline)); outline.anchor.set(0.5, 1);
    const eyes = new Sprite(this.tex.get("eyes:open", () => theme().chit.eyes("open"))); eyes.anchor.set(0.5, 0.5);
    const basket = new Sprite(this.tex.get("i:basket", () => A.iconCanvas("basket"))); basket.anchor.set(0.5, 1); basket.visible = false;
    const carry = new Sprite(); carry.anchor.set(0.5, 1); carry.visible = false;
    const tool = new Sprite(); tool.anchor.set(0.2, 0.9); tool.visible = false;
    root.addChild(shadow, basket, f1, f2, outline, body, eyes, carry, tool);
    this.objects.addChild(root);
    return { root, body, outline, eyes, feet: [f1, f2], shadow, carry, tool, basket, phase: Math.random() * 10, blinkAt: 0, lastAct: "" };
  }

  private removeChit(id: string) {
    const c = this.chits.get(id);
    if (c) {
      this.puff(c.root.x / TS, c.root.y / TS - 0.5, 0xd8e0ff, 8, -0.6);
      c.root.destroy({ children: true });
      this.chits.delete(id);
    }
    const l = this.labels.get(id);
    if (l) { l.name.destroy(); l.emote.destroy(); l.bubble.destroy({ children: true }); l.think.destroy(); this.labels.delete(id); }
  }

  private label(id: string) {
    let l = this.labels.get(id);
    if (!l) {
      const name = new Text({ text: "", style: LABEL, resolution: 2 }); name.anchor.set(0.5, 1);
      const emote = new Text({ text: "", style: EMOTE, resolution: 2 }); emote.anchor.set(0.5, 1);
      const think = new Text({ text: "", style: LABEL, resolution: 2 }); think.anchor.set(0.5, 1);
      const bubble = new Container();
      const bubbleBg = new Graphics();
      const bubbleText = new Text({ text: "", style: BUBBLE, resolution: 2 });
      bubble.addChild(bubbleBg, bubbleText);
      bubble.visible = false;
      this.screen.addChild(name, emote, think, bubble);
      l = { name, emote, bubble, bubbleText, bubbleBg, think, lastSay: "", sel: false };
      this.labels.set(id, l);
    }
    return l;
  }

  // ------------------------------------------------------------------ effects
  private particle(tex: Texture, x: number, y: number, o: Partial<Particle> & { tint?: number; scale?: number; alpha?: number; blend?: string }) {
    const s = new Sprite(tex);
    s.anchor.set(0.5);
    s.position.set(x, y);
    s.tint = o.tint ?? 0xffffff;
    s.scale.set(o.scale ?? 1);
    s.alpha = o.alpha ?? 1;
    if (o.blend) (s as any).blendMode = o.blend;
    this.fx.addChild(s);
    this.particles.push({ s, vx: o.vx ?? 0, vy: o.vy ?? 0, life: o.max ?? 60, max: o.max ?? 60, grow: o.grow ?? 0, fade: o.fade ?? true, world: true, g: o.g ?? 0 });
  }

  burst(tx: number, ty: number, tint: number, n = 20) {
    const tex = this.tex.get("dot", A.dotCanvas);
    for (let i = 0; i < n; i++) {
      const a = -Math.PI / 2 + (Math.random() - 0.5) * 2.4, sp = 0.8 + Math.random() * 1.6;
      this.particle(tex, tx * TS, ty * TS - 6, { vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, g: 0.06, max: 28 + Math.random() * 22, tint, blend: "add", scale: 0.6 + Math.random() * 0.5 });
    }
  }

  puff(tx: number, ty: number, tint: number, n = 5, vy = -0.25) {
    const tex = this.tex.get("glow16", () => A.glowCanvas(16));
    for (let i = 0; i < n; i++) {
      this.particle(tex, tx * TS + (Math.random() - 0.5) * 8, ty * TS, { vx: (Math.random() - 0.5) * 0.3, vy: vy * (0.6 + Math.random()), max: 60 + Math.random() * 40, tint, scale: 0.4 + Math.random() * 0.4, grow: 0.01, alpha: 0.5 });
    }
  }

  floatText(tx: number, ty: number, text: string) {
    const t = new Text({ text, style: FLOAT, resolution: 2 });
    t.anchor.set(0.5, 1);
    t.position.set(tx * TS, ty * TS - 20);
    t.scale.set(0.5);
    this.fx.addChild(t);
    this.particles.push({ s: t as any, vx: 0, vy: -0.25, life: 160, max: 160, grow: 0, fade: true, world: true, g: 0 });
  }

  private onEvents(evs: WorldEvent[]) {
    for (const e of evs) {
      if (e.x == null || e.y == null) continue;
      if (e.kind === "discovery" || e.kind === "first") {
        this.burst(e.x + 0.5, e.y, 0xffe27a, 26);
        const what = (e.text.match(/(?:make|of an?|build|imagined|paved the first) ([a-z ]+?)(?: —|$| from|!)/) || [])[1];
        this.floatText(e.x + 0.5, e.y, "✦ " + (what ? what.trim() : "discovery") + "!");
      } else if (e.kind === "built") {
        this.burst(e.x + 0.5, e.y + 0.5, e.data?.first ? 0xfff0b0 : 0xc8f0a0, e.data?.first ? 30 : 14);
      } else if (e.kind === "birth") {
        const tex = this.tex.get("dot", A.dotCanvas);
        for (let i = 0; i < 10; i++) this.particle(tex, e.x * TS + 8 + (Math.random() - 0.5) * 10, e.y * TS, { vx: (Math.random() - 0.5) * 0.4, vy: -0.5 - Math.random() * 0.4, max: 70, tint: 0xff7aa8, scale: 1.2, blend: "add" });
      } else if (e.kind === "learned" && e.data?.how === "taught") {
        this.burst(e.x + 0.5, e.y, 0x9ad0ff, 6);
      } else if (e.kind === "death") {
        this.puff(e.x + 0.5, e.y, 0xc8d0ff, 10, -0.5);
      }
    }
  }

  // ------------------------------------------------------------------ input & camera
  private setupInput() {
    const cv = this.app.canvas;
    let drag: { x: number; y: number; cx: number; cy: number; moved: boolean; moved0?: boolean } | null = null;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinch0 = 0, zoom0 = 1;
    cv.addEventListener("pointerdown", (e) => {
      cv.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [p, q] = [...pointers.values()];
        pinch0 = Math.hypot(p.x - q.x, p.y - q.y); zoom0 = this.cam.zoom;
      }
      drag = { x: e.clientX, y: e.clientY, cx: this.cam.x, cy: this.cam.y, moved: false };
    });
    cv.addEventListener("pointermove", (e) => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2 && pinch0) {
        const [p, q] = [...pointers.values()];
        this.setZoom(zoom0 * Math.hypot(p.x - q.x, p.y - q.y) / pinch0);
        return;
      }
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
        if (drag.moved) {
          if (!drag.moved0) { drag.moved0 = true; this.onManual(); }
          this.follow = false;
          this.cam.x = drag.cx - dx / this.cam.zoom;
          this.cam.y = drag.cy - dy / this.cam.zoom;
          this.camTarget = { x: this.cam.x, y: this.cam.y };
        }
      } else {
        this.hover = this.pick(e.offsetX, e.offsetY)?.id ?? null;
      }
    });
    const end = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch0 = 0;
      if (drag && !drag.moved && pointers.size === 0 && this.onGodClick) {
        const p = this.screenToWorld(e.offsetX, e.offsetY);
        this.onGodClick(Math.floor(p.x / TS), Math.floor(p.y / TS));
        drag = null;
        return;
      }
      if (drag && !drag.moved && pointers.size === 0) {
        const hit = this.pick(e.offsetX, e.offsetY);
        this.onManual();
        this.selection = hit;
        this.onSelect(hit);
      }
      if (pointers.size === 0) drag = null;
    };
    cv.addEventListener("pointerup", end);
    cv.addEventListener("pointercancel", end);
    cv.addEventListener("wheel", (e) => {
      e.preventDefault();
      const before = this.screenToWorld(e.offsetX, e.offsetY);
      this.setZoom(this.cam.zoom * Math.pow(1.0015, -e.deltaY));
      const after = this.screenToWorld(e.offsetX, e.offsetY);
      this.cam.x += before.x - after.x; this.cam.y += before.y - after.y;
      this.camTarget = { x: this.cam.x, y: this.cam.y };
    }, { passive: false });
  }

  setZoom(z: number) { this.cam.zoom = Math.max(Math.min(0.6, this.fitZoom()), Math.min(7, z)); }

  /** The zoom at which the whole island fits in view (a 512 island needs far less than 0.6). */
  fitZoom() {
    const size = this.data?.size ?? 96;
    return (0.95 * Math.min(this.app.screen.width, this.app.screen.height)) / (size * TS);
  }

  /** The ＋/－ buttons: zoom around the middle of the view. */
  zoomBy(f: number) {
    this.onManual();
    this.follow = false;
    this.setZoom(this.cam.zoom * f);
  }

  /** The ⤢ button: the whole island at once. */
  showAll() {
    this.onManual();
    this.follow = false;
    const size = this.data?.size ?? 96;
    this.camTarget = { x: (size * TS) / 2, y: (size * TS) / 2 };
    this.setZoom(this.fitZoom());
  }

  /** Put the camera straight on a tile at this zoom, no flight (a moment close-up holds it there). */
  jumpTo(tx: number, ty: number, zoom: number) {
    if (!this.ready) return; // (setZoom needs the screen size)
    this.follow = false;
    this.cam.x = tx * TS; this.cam.y = ty * TS;
    this.camTarget = { x: this.cam.x, y: this.cam.y };
    this.setZoom(zoom);
  }

  flyTo(tx: number, ty: number, zoom?: number) {
    this.follow = false;
    this.camTarget = { x: tx * TS, y: ty * TS };
    if (zoom) this.cam.zoom = Math.max(this.cam.zoom, zoom);
  }

  screenToWorld(sx: number, sy: number) {
    const w = this.app.screen.width, h = this.app.screen.height;
    return { x: this.cam.x + (sx - w / 2) / this.cam.zoom, y: this.cam.y + (sy - h / 2) / this.cam.zoom };
  }

  /** A statue for each age's first maker, on free ground by the biggest village's centre (visible eras). */
  private placeStatues() {
    const d = this.data;
    if (!d || !d.ready) return;
    const village = [...this.villages].sort((a: any, b: any) => (b.population ?? 0) - (a.population ?? 0))[0];
    const heroes = this.eraInfo.heroes || [];
    const size = d.size;
    const occupied = new Set<number>();
    for (const s of d.structures.values()) for (let y = s.y; y < s.y + s.h; y++) for (let x = s.x; x < s.x + s.w; x++) occupied.add(y * size + x);
    const free = (x: number, y: number) => {
      if (x < 1 || y < 1 || x >= size - 1 || y >= size - 1) return false;
      const i = y * size + x, t = d.tiles[i];
      return t > A.SHALLOW && t !== A.ROCK && t !== A.FOREST && !occupied.has(i) && d.paths[i] !== 2;
    };
    const spots = village && heroes.length ? plazaSpots(village.x, village.y, heroes.length, free) : [];
    const key = spots.map(([x, y], i) => `${x},${y},${heroes[i].who}`).join("|") + `|${this.eraInfo.index}`;
    if (key === this.statueKey) return;
    this.statueKey = key;
    for (const s of this.statueSprites) s.destroy();
    this.statueSprites = spots.map(([x, y], i) => {
      const tint = statueTint(eraIndex(heroes[i].era));
      const tex = this.tex.get(`statue:${tint}`, () => {
        const [c, ctx] = A.canvas(12, 22);
        const hex = (n: number) => `#${n.toString(16).padStart(6, "0")}`;
        ctx.fillStyle = "rgba(0,0,0,0.25)"; ctx.fillRect(1, 19, 10, 3);
        ctx.fillStyle = "#8f8a80"; ctx.fillRect(2, 15, 8, 5); ctx.fillStyle = "#a7a296"; ctx.fillRect(2, 15, 8, 1);
        ctx.fillStyle = hex(tint); ctx.fillRect(4, 8, 4, 7); ctx.fillRect(3, 9, 6, 3); ctx.fillRect(4, 3, 4, 4);
        ctx.fillStyle = "rgba(255,255,255,0.25)"; ctx.fillRect(4, 3, 1, 12);
        return c;
      });
      const sp = new Sprite(tex);
      sp.anchor.set(0.5, 1);
      sp.position.set((x + 0.5) * TS, (y + 1) * TS);
      sp.zIndex = (y + 1) * TS - 1;
      this.objects.addChild(sp);
      return sp;
    });
  }

  private worldToScreen(wx: number, wy: number) {
    const w = this.app.screen.width, h = this.app.screen.height;
    return { x: (wx - this.cam.x) * this.cam.zoom + w / 2, y: (wy - this.cam.y) * this.cam.zoom + h / 2 };
  }

  private pick(sx: number, sy: number): Selection {
    const d = this.data;
    if (!d) return null;
    const p = this.screenToWorld(sx, sy);
    let best: [number, string] | null = null;
    const now = performance.now();
    for (const a of d.agents.values()) {
      const [x, y] = d.agentPos(a, now);
      const dx = (x + 0.5) * TS - p.x, dy = (y + 0.5) * TS - 5 - p.y;
      const dd = dx * dx + dy * dy;
      if (dd < (TS * 0.9) ** 2 && (!best || dd < best[0])) best = [dd, a.id];
    }
    if (best) return { kind: "agent", id: best[1] };
    const tx = Math.floor(p.x / TS), ty = Math.floor(p.y / TS);
    for (const s of d.structures.values()) {
      if (tx >= s.x && tx < s.x + s.w && ty >= s.y - (s.complete ? 1 : 0) && ty < s.y + s.h) return { kind: "structure", id: s.id };
    }
    return null;
  }

  // ------------------------------------------------------------------ per-frame
  private update(dtMs: number) {
    const d = this.data;
    if (!d || !d.ready || !this.lightRT) return;
    const dt = Math.min(3, dtMs / 16.67);
    this.t += dtMs / 1000;
    const now = performance.now();
    const clock = d.clock;
    const sw = this.app.screen.width, sh = this.app.screen.height;

    // camera
    if (this.follow && this.selection?.kind === "agent") {
      const a = d.agents.get(this.selection.id);
      if (a) {
        const [x, y] = d.agentPos(a, now);
        this.camTarget = { x: (x + 0.5) * TS, y: (y + 0.5) * TS };
      }
    }
    if (this.camTarget) {
      const k = 1 - Math.pow(0.001, dtMs / 1000);
      this.cam.x += (this.camTarget.x - this.cam.x) * Math.min(1, k * 1.5);
      this.cam.y += (this.camTarget.y - this.cam.y) * Math.min(1, k * 1.5);
    }
    const Z = this.cam.zoom;
    this.root.scale.set(Z);
    this.root.position.set(Math.round(sw / 2 - this.cam.x * Z), Math.round(sh / 2 - this.cam.y * Z));
    const view = new Rectangle(-this.root.x / Z - TS * 2, -this.root.y / Z - TS * 3, sw / Z + TS * 4, sh / Z + TS * 6);
    this.onCamera({ x: this.cam.x / TS, y: this.cam.y / TS, zoom: Z, w: sw / Z / TS, h: sh / Z / TS });

    // seasons
    const season = clock?.season || "spring";
    const autumnT = season === "autumn" ? 1 : 0;
    const snowT = season === "winter" ? 1 : 0;
    // (an exponential fade never reached 0, so both overlays were drawn, invisibly, all year)
    const fade = (c: Container, to: number) => { c.alpha += (to - c.alpha) * 0.02 * dt; if (Math.abs(to - c.alpha) < 0.004) c.alpha = to; };
    fade(this.autumn, autumnT);
    fade(this.snow, snowT);
    if (season === "autumn" || this.autumn.alpha > 0) this.queueSeasonLayer("autumn");
    else this.freeSeasonLayer("autumn");
    if (season === "winter" || this.snow.alpha > 0) this.queueSeasonLayer("snow");
    else this.freeSeasonLayer("snow");
    // far out, a tile is about a pixel: the one-texel-per-tile preview looks the same as the painted chunks and
    // costs one texture instead of hundreds, so show that and leave the chunks unpainted
    const overview = Z < MAP_ZOOM;
    this.terrain.visible = !overview;
    this.autumn.visible = !overview && this.autumn.alpha > 0;
    this.snow.visible = !overview && this.snow.alpha > 0;
    const paintBudget = Math.min(20, Math.max(1, dtMs / 16.67));
    if (!overview) this.bakeSome((this.bakeQueue.some((q) => q.layer === "terrain") ? 10 : 4) * paintBudget, view);
    const wxKey = `${clock?.weather || "clear"}|${season}`;
    if (wxKey !== this.wxKey) {
      this.wxKey = wxKey;
      this.wx = weatherProfile(clock?.weather || "clear", season);
      this.setupWeather(this.wx);
    }
    if (season !== this.season) {
      this.season = season;
      if (season === "winter" || this.season === "spring") for (const [i] of this.resSprites) if (d.resKind[i] === A.R_BERRIES) this.updateRes(i);
    }

    // what's on screen: only those trees, plants, sparkles and fish are made, drawn and animated
    const detail = Z >= DETAIL_ZOOM;
    const budget = Math.min(20, Math.max(1, dtMs / 16.67)); // work budgets per unit of time, not per frame
    if (detail) { this.ensureDetail(view, 6 * budget); this.evictDetail(view); }
    this.cullDetail(view, detail);
    for (const sp of this.onScreen.sparkles) {
      const v = Math.sin(this.t * sp.sp + sp.ph);
      sp.s.alpha = v > 0.85 ? (v - 0.85) * 5 : 0;
    }
    for (const f of this.onScreen.fish) {
      if (d.resAmt[f.i] <= 0) { f.s.alpha = 0; continue; }
      const ph = (this.t * 0.6 + f.ph) % 6;
      if (ph < 1.2) { f.s.texture = this.tex.get(`fish${Math.floor(ph / 0.4)}`, () => A.fishCanvas(Math.floor(ph / 0.4))); f.s.alpha = 0.9; }
      else f.s.alpha = 0;
    }
    // trees sway
    for (const s of this.onScreen.trees) {
      if (s.destroyed) continue;
      s.skew.x = Math.sin(this.t * 1.3 + s.x * 0.05 + s.y * 0.03) * 0.035;
    }

    // structures animation
    const maxDark = { normal: 0.55, soft: 0.3, off: 0 }[this.nightMode];
    const lamp = lampStyle(this.eraInfo.index);
    const dark = clock ? Math.max(0, Math.min(maxDark, (1 - clock.daylight) * maxDark * 1.15)) : 0;
    const glowTex = this.tex.get("glow64", () => A.glowCanvas(64));
    let nLight = 0, nGlow = 0;
    const addLight = (tx: number, ty: number, r: number, tint: number, intensity: number) => {
      let l = this.lightPool[nLight++];
      if (!l) {
        l = new Sprite(glowTex);
        l.anchor.set(0.5);
        (l as any).blendMode = "erase";
        this.lightScene.addChild(l);
        this.lightPool.push(l);
      }
      l.visible = true;
      l.position.set(tx * 2, ty * 2);
      l.scale.set((r * 4) / 64);
      l.alpha = intensity;
      if (dark > 0.05) {
        let g = this.glowPool[nGlow++];
        if (!g) {
          g = new Sprite(glowTex);
          g.anchor.set(0.5);
          (g as any).blendMode = "add";
          this.glow.addChild(g);
          this.glowPool.push(g);
        }
        g.visible = true;
        g.position.set(tx * TS, ty * TS);
        g.scale.set((r * TS * 0.8) / 64);
        g.tint = tint;
        g.alpha = Math.min(0.3, dark * 0.45) * intensity;
      }
    };
    if (lamp && dark > 0.1) {  // lamps along the roads (visible eras): only the ones on screen, at most 160
      const Z = this.cam.zoom, size = d.size;
      const x0 = Math.max(0, Math.floor((this.cam.x - sw / 2 / Z) / TS)), x1 = Math.min(size - 1, Math.ceil((this.cam.x + sw / 2 / Z) / TS));
      const y0 = Math.max(0, Math.floor((this.cam.y - sh / 2 / Z) / TS)), y1 = Math.min(size - 1, Math.ceil((this.cam.y + sh / 2 / Z) / TS));
      let n = 0;
      for (let y = y0; y <= y1 && n < 160; y++) for (let x = x0; x <= x1 && n < 160; x++) {
        if (d.paths[y * size + x] === 2 && isLampTile(x, y, lamp.every)) { addLight(x + 0.5, y + 0.5, lamp.radius, lamp.tint, lamp.intensity); n++; }
      }
    }
    for (const [id, v] of this.structs) {
      const s = d.structures.get(id);
      if (!s) continue;
      if (s.design === "lighthouse" && s.complete && !s.ruined && dark > 0.05) {
        addLight(s.x + 1, s.y - 2.2, 10 + Math.sin(this.t * 2) * 1.5, 0xfff0b0, 1);  // its lamp, sweeping the dark
      }
      if (v.flame) {
        v.flame.texture = this.flames[Math.floor(this.t * 8 + v.root.x) % 4];
        const flick = 0.85 + Math.sin(this.t * 13 + v.root.x) * 0.08 + Math.random() * 0.05;
        addLight(s.x + 0.5, s.y + 0.4, 5.5 * flick, 0xffa040, 1);
        if (now > v.smokeAt) { v.smokeAt = now + 350 + Math.random() * 400; this.puff(s.x + 0.5, s.y - 0.2, 0x9a9a9a, 1, -0.3); }
      } else if (s.complete && !s.ruined && (s.worked_until ?? -1) > (clock?.tick ?? 0) && WORK_FX[s.design]) {
        // a shift is being worked here: a hot glow, thick smoke and sparks (the workshop: sawdust)
        const fx = WORK_FX[s.design];
        const cx = s.x + s.w / 2, cy = s.y + s.h / 2;
        if (fx.light) addLight(cx, cy + 0.3, fx.light, 0xff8a30, 1);
        if (now > v.smokeAt) {
          v.smokeAt = now + 220 + Math.random() * 260;
          if (fx.smoke) this.puff(cx, s.y - 0.8, 0x6a6a6a, 2, -0.4);
          this.puff(cx + (Math.random() - 0.5) * s.w * 0.6, cy, fx.spark, 2, -0.9);
        }
      } else if (s.complete && !s.ruined && (s.design === "kiln" || s.design === "furnace" || s.design === "smithy")) {
        addLight(s.x + 0.5, s.y + (s.design === "smithy" ? 1.4 : 0.6), s.design === "kiln" ? 3 : 4, 0xff7a30, 0.9);
        if (now > v.smokeAt) { v.smokeAt = now + 500 + Math.random() * 500; this.puff(s.x + 0.5, s.y - (s.design === "furnace" ? 1.1 : s.design === "smithy" ? 1.5 : 0.6), 0x7a7a7a, 1, -0.35); }
      } else if (s.complete && !s.ruined && HOMELIT.has(s.design) && dark > 0.25) {
        addLight(s.x + s.w / 2, s.y + s.h * 0.6, s.design === "two_storey_house" || s.design === "longhouse" ? 3 : 2.4, 0xffd080, 0.8);
        const chimney = CHIMNEY[s.design];
        if (chimney && now > v.smokeAt) { v.smokeAt = now + 900 + Math.random() * 800; this.puff(s.x + chimney[0], s.y - chimney[1], 0x8a8a8a, 1, -0.3); }
      }
    }

    // chits
    const winter = season === "winter";
    for (const a of d.agents.values()) {
      let c = this.chits.get(a.id);
      if (!c) c = this.makeChit(a), this.chits.set(a.id, c);
      const [x, y] = d.agentPos(a, now);
      const moving = Math.hypot(a.tx - x, a.ty - y) > 0.02 || a.act === "walking" || a.act === "exploring";
      const sleeping = a.act === "sleeping";
      const working = /gathering|building|crafting|experimenting|repairing|harvesting|planting|tending/.test(a.act);
      c.phase += dt * (moving ? 0.35 : working ? 0.25 : 0.06);
      const bob = sleeping ? 0 : moving ? Math.abs(Math.sin(c.phase)) * 1.6 : working ? Math.abs(Math.sin(c.phase * 1.4)) * 1.1 : Math.sin(c.phase) * 0.4;
      c.root.position.set((x + 0.5) * TS, (y + 1) * TS - 2);
      const zc = sortKey((y + 1) * TS + 1);
      if (c.root.zIndex !== zc) c.root.zIndex = zc;
      const sc = a.child ? 0.72 : 1;
      c.root.scale.set(sc * (a.facing < 0 ? -1 : 1), sc);
      const squash = moving ? 1 + Math.sin(c.phase * 2) * 0.05 : working ? 1 - Math.abs(Math.sin(c.phase * 1.4)) * 0.08 : 1;
      c.body.scale.set(1 / squash * (sleeping ? 1.12 : 1), squash * (sleeping ? 0.8 : 1));
      c.outline.scale.copyFrom(c.body.scale);
      c.body.y = -bob; c.outline.y = -bob + 1;
      theme().chit.placeEyes(c.eyes, c.body, bob, sleeping, moving);
      c.feet[0].x = -3 + (moving ? Math.sin(c.phase) * 1.5 : 0); c.feet[0].y = 0;
      c.feet[1].x = 3 - (moving ? Math.sin(c.phase) * 1.5 : 0); c.feet[1].y = 0;
      c.feet[0].visible = c.feet[1].visible = !sleeping;
      // eyes
      let eyeKind: "open" | "blink" | "sleep" | "happy" = "open";
      if (sleeping) eyeKind = "sleep";
      else if (a.emote === "♥" || a.emote === "✨" || a.emote === "🎁") eyeKind = "happy";
      else {
        if (now > c.blinkAt + 150) { if (Math.random() < 0.004 * dt) c.blinkAt = now; }
        if (now - c.blinkAt < 150) eyeKind = "blink";
      }
      c.eyes.texture = this.tex.get(`eyes:${eyeKind}`, () => theme().chit.eyes(eyeKind));
      // carried stuff
      c.basket.visible = a.basket; c.basket.position.set(-5, -bob - 3);
      if (a.carry) {
        c.carry.texture = this.tex.get(`i:${a.carry}`, () => A.iconCanvas(a.carry!));
        c.carry.visible = !sleeping; c.carry.position.set(0, -bob - 13);
      } else c.carry.visible = false;
      if (a.tool && !sleeping) {
        c.tool.texture = this.tex.get(`i:${a.tool}`, () => A.iconCanvas(a.tool!));
        c.tool.visible = true;
        c.tool.position.set(6, -bob - 4);
        c.tool.rotation = working ? Math.sin(c.phase * 2.8) * 0.8 - 0.3 : 0.1;
      } else c.tool.visible = false;
      // work dust
      if (working && Math.random() < 0.03 * dt) this.puff(x + 0.5 + (Math.random() - 0.5) * 0.6, y + 1, 0xd8c8a0, 1, -0.15);
      if (winter && moving && Math.random() < 0.02 * dt) this.puff(x + 0.5, y + 1, 0xffffff, 1, -0.05);
      // a lantern or light bulb carried lights the night round its holder (whatever other tool is shown in hand)
      if (a.light || a.tool === "lantern") addLight(x + 0.5, y + 0.5, 3, 0xffe08a, 0.8);
    }

    for (let i = nLight; i < this.lightPool.length; i++) this.lightPool[i].visible = false;
    for (let i = nGlow; i < this.glowPool.length; i++) this.glowPool[i].visible = false;
    // lighting pass (only when it's dark enough to see: it redrew a size*2 square texture every frame)
    this.lightDark.alpha = 1;
    if (dark > 0.005) this.app.renderer.render({ container: this.lightScene, target: this.lightRT, clear: true });
    this.lightSprite.visible = dark > 0.005;
    this.lightSprite.alpha = dark;

    // particles
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.life -= dt;
      p.s.x += p.vx * dt; p.s.y += p.vy * dt;
      p.vy += p.g * dt;
      if (p.grow) p.s.scale.set(p.s.scale.x + p.grow * dt);
      if (p.fade) p.s.alpha = Math.max(0, Math.min(p.s.alpha, (p.life / p.max) * 1.2));
      if (p.life <= 0) { p.s.destroy(); this.particles.splice(i, 1); }
    }
    if (this.particles.length > 600) this.particles.splice(0, 100).forEach((p) => p.s.destroy());

    this.updateWeather(dt, sw, sh);
    this.updateLabels(now, sw, sh);
    this.updateSignsAndVillages(sw, sh);
    this.updateAnimals(dt, dark);
    Culler.shared.cull(this.root, new Rectangle(0, 0, sw, sh), false);
  }

  /** Show only the trees, plants, water sparkles and fish near the screen, and none of them when zoomed far out
   *  (the painted ground already shows forests and lakes there). They never move, so this only reruns when the
   *  camera has moved a few tiles or sprites were added or removed; Pixi's own culler measured every one of the
   *  ~55,000 on a 512 island every frame. */
  private cullDetail(view: Rectangle, detail: boolean) {
    const r = this.cullAt;
    const far = TS * 4;
    const n = `${this.resSprites.size}:${this.sparkles.length}:${this.fish.length}`; // sprites made or removed
    if (r.detail === detail && r.n === n && Math.abs(view.x - r.x) < far && Math.abs(view.y - r.y) < far
        && Math.abs(view.width - r.w) < far && Math.abs(view.height - r.h) < far) return;
    Object.assign(r, { x: view.x, y: view.y, w: view.width, h: view.height, detail, n });
    const m = TS * 8; // margin: bigger than `far`, so nothing pops in before the next pass
    const x0 = view.x - m, y0 = view.y - m, x1 = view.x + view.width + m, y1 = view.y + view.height + m;
    const inView = (s: Sprite) => detail && s.x >= x0 && s.x <= x1 && s.y >= y0 && s.y <= y1;
    const on = { trees: [] as Sprite[], sparkles: [] as typeof this.sparkles, fish: [] as typeof this.fish };
    for (const s of this.resSprites.values()) {
      s.visible = inView(s);
      if (s.visible && (s as any)._tree) on.trees.push(s);
    }
    for (const sp of this.sparkles) if ((sp.s.visible = inView(sp.s))) on.sparkles.push(sp);
    for (const f of this.fish) if ((f.s.visible = inView(f.s))) on.fish.push(f);
    this.onScreen = on;
  }

  private updateLabels(now: number, sw: number, sh: number) {
    const d = this.data!;
    const Z = this.cam.zoom;
    const showNames = Z >= 3.2;
    for (const a of d.agents.values()) {
      const [x, y] = d.agentPos(a, now);
      const p = this.worldToScreen((x + 0.5) * TS, (y + 1) * TS);
      const onScreen = p.x > -100 && p.x < sw + 100 && p.y > -60 && p.y < sh + 60;
      const selected = this.selection?.kind === "agent" && this.selection.id === a.id;
      const hovered = this.hover === a.id;
      const l = this.label(a.id);
      const head = p.y - (a.child ? 13 : 18) * Z;
      l.name.visible = onScreen && (showNames || selected || hovered);
      if (l.name.visible) {
        l.name.text = a.name;
        l.name.position.set(p.x, head - 2);
        if (l.sel !== selected) { l.sel = selected; l.name.style = selected ? LABEL_SEL : LABEL; }
      }
      l.emote.visible = onScreen && !!a.emote && Z > 1.2;
      if (l.emote.visible) { l.emote.text = a.emote; l.emote.position.set(p.x + 9 * Z * 0.6, head - (l.name.visible ? 12 : 0)); }
      l.think.visible = onScreen && a.think && Z > 1.2 && !a.say;
      if (l.think.visible) {
        const dots = ".".repeat(1 + (Math.floor(now / 350) % 3));
        l.think.text = "💭" + dots;
        l.think.position.set(p.x - 10 * Z * 0.5, head - (l.name.visible ? 12 : 0));
      }
      const saying = !!a.say && onScreen && Z > 0.9;
      l.bubble.visible = saying;
      if (saying) {
        if (l.lastSay !== a.say) {
          l.lastSay = a.say;
          l.bubbleText.text = a.say.length > 110 ? a.say.slice(0, 108) + "…" : a.say;
          const w = Math.min(180, l.bubbleText.width + 14), h = l.bubbleText.height + 10;
          l.bubbleBg.clear().roundRect(0, 0, w, h, 8).fill({ color: 0xfffaf0, alpha: 0.96 }).stroke({ color: 0x2a2140, width: 1.5 });
          l.bubbleBg.moveTo(w / 2 - 5, h).lineTo(w / 2, h + 7).lineTo(w / 2 + 5, h).fill({ color: 0xfffaf0 });
          l.bubbleText.position.set(7, 5);
        }
        l.bubble.position.set(p.x - l.bubbleBg.width / 2, head - l.bubbleBg.height - (l.name.visible ? 14 : 4));
      }
    }
    // selection ring
    let ring = this.overlay.getChildByLabel("ring") as Sprite | null;
    if (!ring) { ring = new Sprite(this.tex.get("ring", A.ringCanvas)); ring.label = "ring"; ring.anchor.set(0.5); this.overlay.addChild(ring); }
    ring.visible = false;
    if (this.selection?.kind === "agent") {
      const a = d.agents.get(this.selection.id);
      if (a) {
        const [x, y] = d.agentPos(a, now);
        const p = this.worldToScreen((x + 0.5) * TS, (y + 1) * TS - 2);
        ring.visible = true; ring.position.set(p.x, p.y);
        ring.scale.set(Z * (1 + Math.sin(now / 200) * 0.06) * (a.child ? 0.75 : 1));
      }
    } else if (this.selection?.kind === "structure") {
      const s = d.structures.get(this.selection.id);
      if (s) {
        const p = this.worldToScreen((s.x + s.w / 2) * TS, (s.y + s.h) * TS);
        ring.visible = true; ring.position.set(p.x, p.y);
        ring.scale.set(Z * s.w * 0.8);
      }
    }
  }

  private setupWeather(wx: WeatherProfile) {
    this.weather.removeChildren().forEach((c) => c.destroy());
    this.flakes = [];
    const sw = this.app.screen.width, sh = this.app.screen.height;
    const kind = wx.particles;
    let tex: Texture | null = null; let tints: number[] = [0xffffff];
    if (kind === "snow") tex = this.tex.get("flake", A.flakeCanvas);
    if (kind === "rain") { tex = this.tex.get("rain", A.rainCanvas); tints = [0xbcd0f0, 0xa8bce0]; }
    if (kind === "leaves") { tex = this.tex.get("leaf", () => A.leafCanvas("#ffffff")); tints = [0xd9822b, 0xc2452d, 0xe8b04a, 0xa8632a]; }
    if (kind === "petals") { tex = this.tex.get("petal", () => A.leafCanvas("#ffffff")); tints = [0xffd3e8, 0xfff6c2, 0xffffff]; }
    if (kind === "fireflies") { tex = this.tex.get("dot", A.dotCanvas); tints = [0xfff6a0]; }
    if (!tex) return;
    const angle = Math.atan2(wx.wind * 3, 9);
    for (let i = 0; i < wx.count; i++) {
      const s = new Sprite(tex);
      s.position.set(Math.random() * sw, Math.random() * sh);
      s.tint = tints[i % tints.length];
      let vx = (Math.random() - 0.3) * wx.wind * 2, vy = 0.5 + Math.random() * 0.6;
      if (kind === "snow") { s.scale.set(1 + Math.random() * 1.6); vy = 0.6 + Math.random() * 1.1; s.alpha = 0.5 + Math.random() * 0.5; }
      else if (kind === "rain") {
        s.scale.set(1.2, 2.5 + Math.random() * 2);
        s.rotation = -angle;
        const sp = 8 + Math.random() * 5;
        vy = sp; vx = wx.wind * 3 * (sp / 9);
        s.alpha = 0.35 + Math.random() * 0.35;
      } else if (kind === "fireflies") { s.scale.set(1.5 + Math.random()); vx = 0; vy = 0; s.alpha = 0; (s as any).blendMode = "add"; }
      else { s.scale.set(1.5 + Math.random()); s.alpha = 0.5 + Math.random() * 0.5; }
      this.weather.addChild(s);
      this.flakes.push({ s, vx, vy, ph: Math.random() * 10 });
    }
  }

  private updateWeather(dt: number, sw: number, sh: number) {
    const kind = this.wx.particles;
    const night = this.data?.clock ? this.data.clock.daylight < 0.35 : false;
    for (const f of this.flakes) {
      f.ph += 0.03 * dt;
      if (kind === "fireflies") {
        f.s.x += Math.sin(f.ph * 1.3) * 0.4 * dt; f.s.y += Math.cos(f.ph) * 0.3 * dt;
        f.s.alpha = night ? Math.max(0, Math.sin(f.ph * 2.2)) * 0.9 : 0;
      } else if (kind === "rain") {
        f.s.x += f.vx * dt; f.s.y += f.vy * dt;
      } else {
        f.s.x += (f.vx + Math.sin(f.ph) * 0.4) * dt; f.s.y += f.vy * dt;
        f.s.rotation += 0.02 * dt;
      }
      if (f.s.y > sh + 5) { f.s.y = -10; f.s.x = Math.random() * (sw + 200) - 100; }
      if (f.s.x > sw + 5) f.s.x = -5;
      if (f.s.x < -5) f.s.x = sw + 5;
      if (f.s.y < -12) f.s.y = sh + 5;
    }
    // colour wash: rain and storms darken, drought warms and shimmers
    const wx = this.wx;
    this.tintG.clear();
    if (wx.tintAlpha > 0) {
      const shimmer = this.wxKey.startsWith("drought") ? Math.sin(this.t * 2.1) * 0.03 : 0;
      this.tintG.rect(0, 0, sw, sh).fill({ color: wx.tint, alpha: Math.max(0, wx.tintAlpha + shimmer) });
    }
    // lightning: a white flash every 4-9 s that fades over ~250 ms
    const now = performance.now();
    if (wx.lightning) {
      if (!this.nextFlash) this.nextFlash = now + 4000 + Math.random() * 5000;
      if (now >= this.nextFlash) { this.flashAt = now; this.nextFlash = now + 4000 + Math.random() * 5000; }
    } else this.nextFlash = 0;
    const fa = Math.max(0, 1 - (now - this.flashAt) / 250);
    this.flashG.clear();
    if (fa > 0) this.flashG.rect(0, 0, sw, sh).fill({ color: 0xffffff, alpha: 0.75 * fa });
  }

  /** Deer, sheep and wolves (T31), gliding between the positions the server sends. */
  private updateAnimals(dt: number, dark: number) {
    const d = this.data!;
    const seen = new Set<string>();
    for (const [id, kind, x, y] of d.animals) {
      seen.add(id);
      let b = this.beasts.get(id);
      if (!b) {
        const s = new Sprite(this.tex.get(`animal:${kind}`, () => A.animalCanvas(kind)));
        s.anchor.set(0.5, 1);
        const eyes = new Sprite(this.tex.get("wolfeyes", A.eyesGlowCanvas));
        eyes.anchor.set(0.5);
        (eyes as any).blendMode = "add";
        eyes.visible = false;
        this.objects.addChild(s);
        this.fx.addChild(eyes);
        b = { s, eyes, x, y, tx: x, ty: y, kind };
        this.beasts.set(id, b);
      }
      if (x !== b.tx) b.s.scale.x = x > b.tx ? 1 : -1;
      b.tx = x; b.ty = y;
      const k = Math.min(1, 0.06 * dt);
      b.x += (b.tx - b.x) * k; b.y += (b.ty - b.y) * k;
      b.s.position.set((b.x + 0.5) * TS, (b.y + 1) * TS - 2);
      const zb = sortKey((b.y + 1) * TS);
      if (b.s.zIndex !== zb) b.s.zIndex = zb;
      if (kind === "wolf") {
        b.eyes.visible = dark > 0.2;
        b.eyes.alpha = Math.min(1, dark * 1.6) * (0.75 + Math.sin(this.t * 3 + b.x) * 0.25);
        b.eyes.position.set((b.x + 0.5) * TS + 3 * b.s.scale.x, (b.y + 1) * TS - 8);
      }
    }
    for (const [id, b] of this.beasts) if (!seen.has(id)) { b.s.destroy(); b.eyes.destroy(); this.beasts.delete(id); }
  }

  /** Signs (T07) as little posts in the world, with their glyph in screen space; village names from above. */
  private updateSignsAndVillages(sw: number, sh: number) {
    const d = this.data!;
    const Z = this.cam.zoom;
    if (this.signsRef !== d.signs) {
      this.signsRef = d.signs;
      const keep = new Set(d.signs.map((g) => g.id));
      for (const [id, v] of this.signViews) if (!keep.has(id)) { v.post.destroy(); v.glyph.destroy(); this.signViews.delete(id); }
      for (const g of d.signs) {
        let v = this.signViews.get(g.id);
        if (!v) {
          const post = new Sprite(this.tex.get("signpost", A.signPostCanvas));
          post.anchor.set(0.5, 1);
          const glyph = new Text({ text: "", style: GLYPH });
          glyph.anchor.set(0.5, 1);
          this.objects.addChild(post); this.overlay.addChild(glyph);
          v = { post, glyph };
          this.signViews.set(g.id, v);
        }
        v.post.position.set((g.x + 0.5) * TS, (g.y + 1) * TS);
        v.post.zIndex = (g.y + 1) * TS;
        v.glyph.text = signGlyph(g.symbol);
      }
    }
    for (const g of d.signs) {
      const v = this.signViews.get(g.id);
      if (!v) continue;
      const p = this.worldToScreen((g.x + 0.5) * TS, (g.y + 1) * TS - 12);
      v.glyph.visible = Z > 1.5 && p.x > -20 && p.x < sw + 20 && p.y > -20 && p.y < sh + 20;
      if (v.glyph.visible) v.glyph.position.set(p.x, p.y - 2);
    }
    // things lying on the ground (T28): drawn with their icons, artifacts big
    const seen = new Set<string>();
    for (const g of d.ground) {
      const key = `${g.x},${g.y}`;
      seen.add(key);
      let t = this.groundTexts.get(key);
      if (!t) { t = new Text({ text: "", style: GLYPH }); t.anchor.set(0.5, 0.85); this.overlay.addChildAt(t, 0); this.groundTexts.set(key, t); }
      t.text = g.icon;
      const big = ["alien_ship", "meteorite", "golden_idol", "treasure_chest"].some((k) => g.items[k]);
      t.scale.set(Math.max(0.5, Z / 3) * (big ? (g.items.alien_ship ? 2.6 : 1.5) : 0.8));
      const p = this.worldToScreen((g.x + 0.5) * TS, (g.y + 0.9) * TS);
      t.visible = Z > 0.9 && p.x > -60 && p.x < sw + 60 && p.y > -60 && p.y < sh + 60;
      if (t.visible) t.position.set(p.x, p.y);
    }
    for (const [k, t] of this.groundTexts) if (!seen.has(k)) { t.destroy(); this.groundTexts.delete(k); }
    this.app.canvas.style.cursor = this.onGodClick ? "crosshair" : "";
    const show = villageLabelVisible(Z);
    const keep = new Set(this.villages.map((v) => v.id));
    for (const [id, t] of this.villageTexts) if (!keep.has(id)) { t.destroy(); this.villageTexts.delete(id); }
    for (const v of this.villages) {
      let t = this.villageTexts.get(v.id);
      if (!t) { t = new Text({ text: v.name, style: VILLAGE }); t.anchor.set(0.5); t.alpha = 0.7; this.overlay.addChildAt(t, 0); this.villageTexts.set(v.id, t); }
      // a town or a city says so under its name (sim/settlements.py ranks)
      t.text = v.rank === "town" || v.rank === "city" ? `${v.name}
${v.rank === "city" ? "City" : "Town"}` : v.name;
      t.scale.set(v.rank === "city" ? 1.3 : v.rank === "town" ? 1.15 : 1);
      t.visible = show;
      if (show) { const p = this.worldToScreen((v.x + 0.5) * TS, (v.y + 0.5) * TS); t.position.set(p.x, p.y); }
    }
  }
}
