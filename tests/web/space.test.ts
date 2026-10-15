import { describe, expect, it } from "vitest";
import { launchEvent, spaceLines, type SpaceProgramme } from "../../web/src/ui/space";

// 🚀 The space programme as the Progress panel says it.
const sp = (over: Partial<SpaceProgramme>): SpaceProgramme =>
  ({ launches: 1, satellites: 0, moon_day: null, station_day: null, expeditions: 0, next: "satellite", rockets: 0, ...over });

describe("space programme", () => {
  it("says nothing before the first launch", () => {
    expect(spaceLines(null)).toBeNull();
    expect(spaceLines(sp({ launches: 0 }))).toBeNull();
  });
  it("names the next mission, and a rocket that is ready", () => {
    expect(spaceLines(sp({}))).toEqual({ head: "1 launch", done: [], next: "Next launch: a satellite circling the island." });
    expect(spaceLines(sp({ launches: 2, satellites: 1, next: "moon", rockets: 1 }))!.next)
      .toBe("Next launch: a landing on the Moon (a rocket is ready).");
  });
  it("lists what is up there in order", () => {
    const l = spaceLines(sp({ launches: 6, satellites: 1, moon_day: 410, station_day: 452, expeditions: 2, next: "expedition" }))!;
    expect(l.head).toBe("6 launches");
    expect(l.done).toEqual(["a satellite", "the Moon (day 410)", "a station in orbit (day 452)", "2 expeditions"]);
    expect(l.next).toBe("Next launch: an expedition beyond the Moon.");
  });
  it("sends a rocket up for the first launch and every mission", () => {
    expect(launchEvent("launch")).toBe(true);
    expect(launchEvent("space")).toBe(true);
    expect(launchEvent("built")).toBe(false);
  });
});
