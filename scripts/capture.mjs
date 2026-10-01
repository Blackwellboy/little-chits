#!/usr/bin/env node
// Capture PNG frames of Little Chits in record mode (?record=1), for timelapse clips.
//
//   node scripts/capture.mjs --url http://127.0.0.1:8000 --out frames --frames 900 --interval-ms 250 \
//        --aspect 9:16 --speed 25 --world A
//
// Needs Playwright with Chromium. If it's missing:  cd web && npm i -D playwright && npx playwright install chromium
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

function args(argv) {
  const o = { url: "http://127.0.0.1:8000", out: "frames", frames: 120, "interval-ms": 250, aspect: "16:9", width: 0, speed: "", world: "A" };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i].replace(/^--/, "");
    if (k in o) o[k] = argv[++i];
  }
  o.frames = Number(o.frames); o["interval-ms"] = Number(o["interval-ms"]); o.width = Number(o.width);
  return o;
}

async function loadPlaywright() {
  try { return await import("playwright"); } catch { /* try the web folder's copy */ }
  try {
    const req = createRequire(join(resolve(import.meta.dirname ?? ".", "..", "web"), "package.json"));
    return await import(req.resolve("playwright"));
  } catch { /* try a global install */ }
  try {
    const { execSync } = await import("node:child_process");
    const root = execSync("npm root -g", { encoding: "utf8" }).trim();
    return await import(join(root, "playwright", "index.mjs"));
  } catch { /* fall through */ }
  console.error("Playwright isn't installed. Install it once with:\n  cd web && npm i -D playwright && npx playwright install chromium");
  process.exit(2);
}

const SIZES = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1] };

const o = args(process.argv.slice(2));
const [aw, ah] = SIZES[o.aspect] || SIZES["16:9"];
// default: 1080 px on the short side
let W, H;
if (o.width) { W = o.width; H = Math.round((o.width * ah) / aw); }
else if (aw >= ah) { H = 1080; W = Math.round((1080 * aw) / ah); }
else { W = 1080; H = Math.round((1080 * ah) / aw); }

const pw = await loadPlaywright();
const chromium = pw.chromium || pw.default?.chromium;
const executablePath = process.env.PLAYWRIGHT_CHROMIUM || process.env.executablePath || undefined;
const browser = await chromium.launch({ executablePath });
const page = await browser.newPage({ viewport: { width: W, height: H } });
const q = new URLSearchParams({ record: "1", aspect: o.aspect, world: o.world });
if (o.speed) q.set("speed", String(o.speed));
const url = `${o.url.replace(/\/$/, "")}/?${q}`;
mkdirSync(o.out, { recursive: true });
console.log(`capturing ${o.frames} frames of ${url} at ${W}x${H}, one every ${o["interval-ms"]} ms`);
await page.goto(url);
await page.waitForTimeout(4000);
for (let i = 1; i <= o.frames; i++) {
  const t0 = Date.now();
  await page.screenshot({ path: join(o.out, `frame-${String(i).padStart(5, "0")}.png`) });
  if (i % 50 === 0) console.log(`  ${i}/${o.frames}`);
  const wait = o["interval-ms"] - (Date.now() - t0);
  if (wait > 0) await page.waitForTimeout(wait);
}
await browser.close();
console.log(`frames in ${o.out}`);
