// Visible eras: what a village looks like as it moves up the ages. Pure logic (tested in tests/web/eras.test.ts);
// the renderer draws it. Nothing here is simulation truth: lamps and statues show what the world already records
// (its age, and who first made each age's key thing).

export const ERA_NAMES = ["Wanderers", "Firekeepers", "Toolmakers", "Farmers", "Potters", "Scribes", "Copper Age",
  "Iron Age", "Machine Age", "Electric Age", "Space Age"];

export type Hero = { era: string; who: string; day: number };
export type LampStyle = { every: number; radius: number; tint: number; intensity: number };

export function eraIndex(name: string | undefined | null): number {
  const i = ERA_NAMES.indexOf(name || "");
  return i < 0 ? 0 : i;
}

/** Lamps along the roads at night: none before copper (a lantern needs glass and copper), oil lamps then, brighter
 *  and whiter as the ages go on, electric street lights at the end. */
export function lampStyle(era: number): LampStyle | null {
  if (era < 6) return null;
  if (era < 8) return { every: 6, radius: 2.2, tint: 0xffc070, intensity: 0.75 };  // copper and iron: oil lamps
  if (era < 9) return { every: 4, radius: 2.8, tint: 0xffe0a0, intensity: 0.85 };  // machines: gas lamps
  return { every: 3, radius: 3.4, tint: 0xe8f0ff, intensity: 0.95 };  // electric
}

/** Is this road tile one of the lamp posts? A fixed pattern, so lamps don't jump about as roads are added. */
export function isLampTile(x: number, y: number, every: number): boolean {
  return ((x * 7 + y * 13) % every + every) % every === 0;
}

/** The colour of a statue: stone for the early ages, then the metal the age is named for. */
export function statueTint(era: number): number {
  return era >= 9 ? 0xd9dde6 : era >= 8 ? 0x8a8f99 : era >= 7 ? 0x6e737c : era >= 6 ? 0xc27a45 : 0xb9b3a6;
}

/** Where the statues stand: free tiles spiralling out from just below the village's centre, one per hero. */
export function plazaSpots(cx: number, cy: number, n: number, free: (x: number, y: number) => boolean,
  reach = 8): [number, number][] {
  const out: [number, number][] = [];
  const taken = new Set<string>();
  // a village's centre is an average (237.48, 269.52): on it every spot was a fraction of a tile, never free
  cx = Math.round(cx);
  cy = Math.round(cy);
  for (let r = 0; r <= reach && out.length < n; r++) {
    for (let dy = -r; dy <= r && out.length < n; dy++) {
      for (let dx = -r; dx <= r && out.length < n; dx++) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
        const x = cx + dx, y = cy + 2 + dy, k = `${x},${y}`;
        if (taken.has(k) || !free(x, y)) continue;
        // keep a tile between statues so each stands on its own
        if ([...taken].some((t) => { const [tx, ty] = t.split(",").map(Number); return Math.abs(tx - x) + Math.abs(ty - y) < 2; })) continue;
        taken.add(k);
        out.push([x, y]);
      }
    }
  }
  return out;
}

/** Roads as the ages go on: cobbles until the machines come, then crushed-stone macadam, then asphalt with a painted
 *  line once there is electricity. 0 cobble, 1 macadam, 2 asphalt. */
export function roadStyle(era: number): 0 | 1 | 2 {
  return era >= 9 ? 2 : era >= 8 ? 1 : 0;
}

export const POWER_RADIUS = 20;  // server/chits/sim/buildings.py POWER_RADIUS: what a power station reaches

type Box = { id: string; x: number; y: number; w: number; h: number };

/** How far apart two footprints are, the simulator's way (world.Structure.dist, buildings.powered): tiles in the
 *  larger of the two axes, between their nearest edges. A building is in a station's reach if any tile of it is. */
export function reach(a: Box, b: Box): number {
  const dx = Math.max(a.x - (b.x + b.w - 1), 0, b.x - (a.x + a.w - 1));
  const dy = Math.max(a.y - (b.y + b.h - 1), 0, b.y - (a.y + a.h - 1));
  return Math.max(dx, dy);
}

/** Which buildings each power station's wires run to: the nearest within its reach (it really speeds the stations
 *  there, and lights the homes), at most `max` each. Pure, for the renderer's wire layer. */
export function wireTargets(stations: Box[], buildings: Box[], radius = POWER_RADIUS, max = 10): [Box, Box][] {
  const out: [Box, Box][] = [];
  for (const s of stations) {
    const near = buildings.filter((b) => b.id !== s.id)
      .map((b) => ({ b, d: reach(s, b) }))
      .filter((o) => o.d <= radius).sort((p, q) => p.d - q.d || (p.b.id < q.b.id ? -1 : 1)).slice(0, max);
    for (const o of near) out.push([s, o.b]);
  }
  return out;
}

/** Is a building lit by electricity: within reach of a working power station. */
export function electrified(b: Box, stations: Box[], radius = POWER_RADIUS): boolean {
  return stations.some((s) => reach(s, b) <= radius);
}

/** The best carrier a chit has, which it is drawn pulling: a wagon, else a cart, else a sled. */
export const VEHICLES = ["wagon", "cart", "sled"] as const;
