import { describe, expect, it } from "vitest";
import { SKIP_CHOICES, SKIP_NOTE, skipProgress, skipResult, type SkipResult } from "../../web/src/ui/skip";

// ⏩ Skip ahead: what the top bar offers, says while skipping, and says when the skip is over.
const ended = (over: Partial<SkipResult>): SkipResult =>
  ({ until: "days", reason: "days", text: "", ended: 1, from_day: 3100, day: 3107, ticks: 7 * 240, seconds: 31.5, ...over });

describe("skip ahead", () => {
  it("offers the next discovery, the next big moment, a day and a week", () => {
    expect(SKIP_CHOICES.map((c) => [c.label, c.until, c.days])).toEqual([
      ["To the next discovery", "discovery", undefined], ["To the next big moment", "moment", undefined],
      ["1 day", "days", 1], ["7 days", "days", 7]]);
  });
  it("says plainly that skipped time is mostly instinct-driven", () => {
    expect(SKIP_NOTE).toContain("mostly instinct-driven");
  });
  it("shows the day it has reached and how long it has run", () => {
    expect(skipProgress({ until: "discovery", days: 30, from_day: 3100, day: 3112, seconds: 14 })).toBe("Skipping: day 3112, 14 s");
  });
  it("says how the skip ended in one plain sentence", () => {
    expect(skipResult(null)).toBe("");
    expect(skipResult(ended({}))).toBe("Skipped 7 days. It is day 3107.");
    expect(skipResult(ended({ ticks: 240, day: 3101 }))).toBe("Skipped 1 day. It is day 3101.");
    expect(skipResult(ended({ until: "discovery", reason: "found", text: "Ada discovered how to make rope — a first for the world!", day: 3104 })))
      .toBe("Stopped on day 3104: Ada discovered how to make rope — a first for the world!");
    expect(skipResult(ended({ until: "moment", reason: "limit", ticks: 30 * 240, day: 3130 }))).toBe("Nothing new in 30 days. Stopped on day 3130.");
    expect(skipResult(ended({ reason: "stopped", day: 3102 }))).toBe("The skip stopped on day 3102.");
    expect(skipResult(ended({ reason: "storage", day: 3102, text: "OSError: disk full" })))
      .toBe("The skip stopped on day 3102: the game could not be saved.");
  });
});
