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
