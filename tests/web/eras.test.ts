import { describe, expect, it } from "vitest";
import { eraIndex, isLampTile, lampStyle, plazaSpots, statueTint } from "../../web/src/render/eras";

describe("visible eras", () => {
  it("names map to ages, unknown names to the first", () => {
    expect(eraIndex("Copper Age")).toBe(6);
    expect(eraIndex("Space Age")).toBe(10);
    expect(eraIndex(undefined)).toBe(0);
  });

  it("lamps light the roads only from the copper age, brighter as the ages go on", () => {
    expect(lampStyle(5)).toBeNull();
    const oil = lampStyle(6)!, electric = lampStyle(9)!;
    expect(oil.every).toBeGreaterThan(electric.every);
    expect(electric.radius).toBeGreaterThan(oil.radius);
    let lamps = 0;
    for (let x = 0; x < 60; x++) if (isLampTile(x, 5, oil.every)) lamps++;
    expect(lamps).toBe(10);
  });

  it("statues are stone early and metal later", () => {
    expect(statueTint(2)).not.toBe(statueTint(6));
    expect(statueTint(7)).not.toBe(statueTint(6));
  });

  it("statues stand on free tiles near the plaza, apart from each other", () => {
    const blocked = new Set(["10,12", "11,12"]);
    const spots = plazaSpots(10, 10, 4, (x, y) => !blocked.has(`${x},${y}`));
    expect(spots).toHaveLength(4);
    for (const [x, y] of spots) expect(blocked.has(`${x},${y}`)).toBe(false);
    for (let i = 0; i < spots.length; i++)
      for (let j = i + 1; j < spots.length; j++)
        expect(Math.abs(spots[i][0] - spots[j][0]) + Math.abs(spots[i][1] - spots[j][1])).toBeGreaterThanOrEqual(2);
    expect(plazaSpots(0, 0, 3, () => false)).toEqual([]);
    // a village's centre is an average of its buildings: the statues still stand on whole tiles
    const onTiles = plazaSpots(237.48, 269.52, 3, (x, y) => Number.isInteger(x) && Number.isInteger(y));
    expect(onTiles).toHaveLength(3);
  });
});


import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { electrified, POWER_RADIUS, roadStyle, wireTargets } from "../../web/src/render/eras";

describe("roads, wires and lights by what a world has", () => {
  it("paves roads by the age", () => {
    expect(roadStyle(0)).toBe(0); expect(roadStyle(7)).toBe(0);
    expect(roadStyle(8)).toBe(1); expect(roadStyle(9)).toBe(2); expect(roadStyle(10)).toBe(2);
  });
  it("runs wires only to buildings a power station reaches, nearest first, capped", () => {
    const st = { id: "p", x: 50, y: 50, w: 2, h: 2 };
    const near = Array.from({ length: 14 }, (_, i) => ({ id: `b${i}`, x: 52 + i, y: 50, w: 2, h: 2 }));
    const far = { id: "far", x: 90, y: 90, w: 2, h: 2 };
    const pairs = wireTargets([st], [...near, far, st], 20, 10);
    expect(pairs.length).toBe(10);
    expect(pairs.map(([, b]) => b.id)).not.toContain("far");
    expect(pairs[0][1].id).toBe("b0");
    expect(wireTargets([], near)).toEqual([]);
  });
  it("lights a building only within a station's reach", () => {
    const st = { id: "p", x: 50, y: 50, w: 2, h: 2 };
    expect(electrified({ id: "h", x: 60, y: 50, w: 2, h: 2 }, [st])).toBe(true);
    expect(electrified({ id: "h", x: 80, y: 50, w: 2, h: 2 }, [st])).toBe(false);
    expect(electrified({ id: "h", x: 60, y: 50, w: 2, h: 2 }, [])).toBe(false);
    expect(electrified({ id: "h", x: 50 + POWER_RADIUS, y: 50, w: 2, h: 2 }, [st])).toBe(true);  // (the edge of its reach counts)
    expect(electrified({ id: "h", x: 51 + POWER_RADIUS, y: 50, w: 2, h: 2 }, [st])).toBe(false);
  });
  it("reaches as far as the server says a power station does", () => {
    const src = readFileSync(resolve(__dirname, "../../server/chits/sim/buildings.py"), "utf8");
    const m = src.match(/^POWER_RADIUS, POWER_SPEED = (\d+),/m);
    expect(m).not.toBeNull();
    expect(POWER_RADIUS).toBe(Number(m![1]));
  });
});
