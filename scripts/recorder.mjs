#!/usr/bin/env node
// Auto-record (the 🎞 Recordings panel): watch the running game in record mode and save one JPEG frame every
// --interval-ms into --out, named by the time it was taken (<ms>.jpg), until it is stopped. The server cuts the
// frames into one clip per in-game day. Unlike capture.mjs it never changes the game's speed.
//
// Moments: the server writes one JSON command per line on stdin, e.g.
//   {"cmd":"moment","dir":".../frames/moments/moment-012-A-discovery-1","world":"A","x":40,"y":52,"zoom":3.8,
//    "caption":"Molo discovered bread","label":"World A · Day 12 · 14:00","seconds":15,"fps":10}
// and a second page, zoomed in on that spot with the caption, is filmed at live speed into `dir` (<ms>.jpg, as
// the browser paints them) with done.json written last. The day's frames carry on meanwhile.
//
//   node scripts/recorder.mjs --url http://127.0.0.1:8010 --out data/recordings/frames --world split --aspect 16:9
//
// Needs Playwright with Chromium:  cd web && npm i -D playwright && npx playwright install chromium
import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";

function args(argv) {
  const o = { url: "http://127.0.0.1:8000", out: "frames", "interval-ms": 500, aspect: "16:9", world: "split", fps: 2 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i].replace(/^--/, "");
    if (k in o) o[k] = argv[++i];
  }
  o["interval-ms"] = Number(o["interval-ms"]); o.fps = Number(o.fps);
  return o;
}

async function loadPlaywright() {
  try { return await import("playwright"); } catch { /* try the web folder's copy */ }
  try {
    const req = createRequire(join(resolve(import.meta.dirname ?? ".", "..", "web"), "package.json"));
    return await import(req.resolve("playwright"));
  } catch { /* fall through */ }
  console.error("Playwright isn't installed. Install it once with:\n  cd web && npm i -D playwright && npx playwright install chromium");
  process.exit(2);
}

// Filmed at 720p and scaled up by ffmpeg: under WSL there is no GPU for the headless browser, so every pixel
// is drawn on the CPU. Mesa's llvmpipe (Vulkan) is about twice as fast as Chromium's own SwiftShader.
const SIZES = { "16:9": [1280, 720], "9:16": [720, 1280], "1:1": [960, 960] };
const o = args(process.argv.slice(2));
const [W, H] = SIZES[o.aspect] || SIZES["16:9"];
const pw = await loadPlaywright();
const chromium = pw.chromium || pw.default?.chromium;
const launch = () => chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined,
  args: ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist"],
});
const browser = await launch();
// Moments are filmed in a browser of their own: all pages of one browser share a single (software) GPU
// process, and with the day's page drawing in it too a moment got ~2.5 frames a second instead of ~8.
let momentBrowser = null;
async function momentBrowserUp() {
  if (!momentBrowser || !momentBrowser.isConnected()) momentBrowser = await launch();
  return momentBrowser;
}
const base = o.url.replace(/\/$/, "");
const url = `${base}/?${new URLSearchParams({ record: "1", aspect: o.aspect, world: o.world })}`;
mkdirSync(o.out, { recursive: true });
let stopping = false;
for (const sig of ["SIGTERM", "SIGINT"]) process.on(sig, () => { stopping = true; });
// commands from the server, one JSON per line; the server that started us went away: stop too
const moments = [];
createInterface({ input: process.stdin })
  .on("line", (line) => {
    try {
      const m = JSON.parse(line);
      if (m.cmd === "moment" && m.dir) { moments.push(m); if (moments.length === 1) filmMoments(); }
    } catch (e) { console.error(`bad command: ${e.message ?? e}`); }
  })
  .on("close", () => { stopping = true; });

async function open() {
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  await page.goto(url, { waitUntil: "load", timeout: 60000 });
  await page.waitForTimeout(3000);
  return page;
}

// ------------------------------------------------------------------ moments, one at a time
async function filmMoments() {
  while (moments.length && !stopping) {
    const m = moments[0];
    try { await filmMoment(m); } catch (e) {
      console.error(`moment failed: ${e.message ?? e}`);
      try { writeFileSync(join(m.dir, "done.json"), JSON.stringify({ frames: 0, error: String(e.message ?? e) })); } catch { /* gone */ }
    }
    moments.shift();
  }
}

async function filmMoment(m) {
  mkdirSync(m.dir, { recursive: true });
  // a 3/4-size page drawn at 4/3 pixel density: the same 720p of pixels to draw as the day's page, with the
  // names, speech bubbles and caption a third bigger in the frame
  const ctx = await (await momentBrowserUp()).newContext({ viewport: { width: Math.round(W * 0.75), height: Math.round(H * 0.75) }, deviceScaleFactor: 4 / 3 });
  try {
    const page = await ctx.newPage();
    const q = new URLSearchParams({
      record: "1", aspect: o.aspect, world: m.world, director: "0", focus: `${m.x},${m.y}`, zoom: String(m.zoom),
      caption: m.caption || "", label: m.label || "",
    });
    await page.goto(`${base}/?${q}`, { waitUntil: "load", timeout: 30000 });
    // the world has arrived and its view is drawing
    await page.waitForFunction((w) => (window.__chits?.worlds?.[w]?.agents?.size ?? 0) > 0 && !!window.__chits?.views?.[w]?.app?.ticker,
      m.world, { timeout: 20000, polling: 200 });
    const fps = Math.max(12, Math.round((m.fps || 10) * 1.5));
    await page.evaluate(({ w, x, y, zoom, fps }) => {
      const v = window.__chits.views[w];
      v.app.ticker.maxFPS = fps;
      // a build without moment support (?focus=): aim the camera from here, without the caption
      if (!window.__chits.moment) { v.flyTo(x, y); v.setZoom(zoom); v.cam.x = x * 16; v.cam.y = y * 16; }
    }, { w: m.world, x: m.x, y: m.y, zoom: m.zoom, fps });
    await page.waitForTimeout(1200); // the camera lands and nearby chunks are baked
    // the screencast hands over frames as the page paints them (~8-10 a second on the CPU), far cheaper than
    // screenshots; each is named by when it was painted so the clip can play them back at their real timing
    const cdp = await ctx.newCDPSession(page);
    let n = 0, t0 = 0, t1 = 0;
    cdp.on("Page.screencastFrame", async (f) => {
      const ms = Math.round(f.metadata.timestamp * 1000);
      try {
        if (!t0) t0 = ms;
        t1 = ms;
        writeFileSync(join(m.dir, `${ms}.jpg`), Buffer.from(f.data, "base64"));
        n += 1;
      } catch { /* the folder was abandoned */ }
      try { await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch { /* page closing */ }
    });
    const [w, h] = SIZES[o.aspect] || SIZES["16:9"];
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: w, maxHeight: h, everyNthFrame: 1 });
    const end = Date.now() + (m.seconds || 15) * 1000;
    while (Date.now() < end && !stopping) await new Promise((r) => setTimeout(r, 250));
    await cdp.send("Page.stopScreencast").catch(() => {});
    await new Promise((r) => setTimeout(r, 200)); // the last frame's write
    writeFileSync(join(m.dir, "done.json"), JSON.stringify({ frames: n, seconds: (t1 - t0) / 1000 }));
    console.log(`moment filmed: ${m.dir} (${n} frames in ${((t1 - t0) / 1000).toFixed(1)} s)`);
  } finally {
    await ctx.close().catch(() => {});
  }
}

// ------------------------------------------------------------------ the day, a frame every interval
console.log(`recording ${url} at ${W}x${H}, one frame every ${o["interval-ms"]} ms into ${o.out}`);
// a steady clock for names and pacing: the wall clock under WSL steps back ~2.7 s every ~30 s
const origin = Date.now() - performance.now();
const stamp = () => Math.round(origin + performance.now());
// nobody watches this page live: render a couple of times per frame taken, to spare the CPU
const renderFps = Math.max(o.fps, Math.ceil(2000 / o["interval-ms"]));
// Frames come from the page's screencast (what it last painted), not page.screenshot(): a screenshot reads the
// pixels back and stalls the one software GPU process every page shares (~400 ms each on a busy CPU, and a
// moment being filmed alongside dropped to 2 fps). A screenshot is only taken when nothing was painted lately.
let latest = null;
async function cast(p) {
  latest = null;
  const cdp = await p.context().newCDPSession(p);
  cdp.on("Page.screencastFrame", async (f) => {
    latest = { data: f.data, at: stamp(), used: false };
    try { await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch { /* page closing */ }
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
}
let page = await open();
await cast(page).catch((e) => console.error(`no screencast (${e.message ?? e}): screenshots only`));
let failures = 0, n = 0;
while (!stopping) {
  const t0 = stamp();
  try {
    if (n++ % 20 === 0) await page.evaluate((fps) => {
      for (const v of Object.values(window.__chits?.views ?? {})) if (v?.app?.ticker) v.app.ticker.maxFPS = fps;
    }, renderFps);
    let jpg = null;
    if (latest && !latest.used) { jpg = Buffer.from(latest.data, "base64"); latest.used = true; }
    else if (!latest || t0 - latest.at > 2000) jpg = await page.screenshot({ type: "jpeg", quality: 85 });
    if (jpg) {  // (else: nothing new painted since the last frame, and it's recent: wait for the next)
      const tmp = join(o.out, `.${t0}.jpg`);
      writeFileSync(tmp, jpg);
      renameSync(tmp, join(o.out, `${t0}.jpg`));  // appears whole, never half-written
    }
    failures = 0;
  } catch (e) {
    failures += 1;
    console.error(`frame failed (${failures}): ${e.message ?? e}`);
    if (failures >= 3) {
      try { await page.close(); } catch { /* already gone */ }
      await new Promise((r) => setTimeout(r, 5000));
      try { page = await open(); await cast(page); failures = 0; } catch (e2) { console.error(`reopen failed: ${e2.message ?? e2}`); }
    }
  }
  const wait = o["interval-ms"] - (stamp() - t0);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
}
await browser.close();
await momentBrowser?.close().catch(() => {});
console.log("recorder stopped");
