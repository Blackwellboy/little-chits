import { describe, expect, it } from "vitest";
import { instinctChip, thinkingLine, type Thinking } from "../../web/src/ui/watch";

const t = (p: Partial<Thinking>): Thinking => ({ brain: "m1", steps: 100, model_pct: 40, body_pct: 30, routine_pct: 20, instinct_pct: 10,
  fallback_pct: 0, on_instinct: false, why: "", ...p });

// ⚙ a world running without a model says so; one whose model is deciding does not
describe("instinctChip", () => {
  it("labels a world with no model, and one whose model has stopped deciding", () => {
    expect(instinctChip(t({ brain: "instinct", on_instinct: true, why: "no_model" }))!.text).toBe("⚙ running on instinct");
    expect(instinctChip(t({ on_instinct: true, why: "model_down", steps: 57 }))!.title).toContain("none of the last 57 steps");
    // before the server has answered, a world whose brain is instinct is still said to be
    expect(instinctChip(undefined, "instinct")).not.toBeNull();
  });
  it("says nothing while a model is thinking", () => {
    expect(instinctChip(t({}))).toBeNull();
    expect(instinctChip(undefined, "m1")).toBeNull();
    expect(instinctChip(t({ brain: "instinct", on_instinct: false }), "instinct")).toBeNull();
  });
});

describe("thinkingLine", () => {
  it("gives the shares of recent steps, the biggest first", () => {
    expect(thinkingLine(t({}))).toBe("model 40% · body reflexes 30% · upkeep 20% · instinct 10% of the last 100 steps");
    expect(thinkingLine(t({ brain: "instinct", model_pct: 0, instinct_pct: 70, body_pct: 30, routine_pct: 0 })))
      .toBe("No model: instinct 70% · body reflexes 30% of the last 100 steps");
    expect(thinkingLine(t({ why: "model_down", model_pct: 0, instinct_pct: 90, body_pct: 10, routine_pct: null })))
      .toBe("Model not deciding: instinct 90% · body reflexes 10% of the last 100 steps");
  });
  it("has nothing to share before any step is finished", () => {
    expect(thinkingLine(null)).toBe("No steps finished yet.");
    expect(thinkingLine(t({ steps: 0 }))).toBe("No steps finished yet.");
  });
});
