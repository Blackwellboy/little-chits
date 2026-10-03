import { describe, expect, it } from "vitest";
import { WHY_NOTHING, whyLines, type WhyData } from "../../web/src/ui/why";

// 🐢 "Why is nothing happening?": the panel shows the server's sentences, the whole game's first
describe("whyLines", () => {
  const d: WhyData = {
    game: [{ kind: "paused", text: "The game is paused." }],
    worlds: {
      A: { name: "Ember", day: 12, brain: "instinct", reasons: [{ kind: "failure", text: "No sand near home: 35 failed tries so far." }] },
      B: { name: "Frost", day: 12, brain: "m", reasons: [] },
    },
  };

  it("puts what stops every world before a world's own reasons", () => {
    expect(whyLines(d, "A").map((l) => l.text)).toEqual(["The game is paused.", "No sand near home: 35 failed tries so far."]);
    expect(whyLines(d, "B").map((l) => l.kind)).toEqual(["paused"]);
  });

  it("has nothing to say for a world with no reasons, or one the server did not send", () => {
    const quiet: WhyData = { game: [], worlds: { A: { ...d.worlds.A, reasons: [] } } };
    expect(whyLines(quiet, "A")).toEqual([]);
    expect(whyLines(quiet, "Z")).toEqual([]);
    expect(WHY_NOTHING).toMatch(/Nothing is holding/);
  });
});
