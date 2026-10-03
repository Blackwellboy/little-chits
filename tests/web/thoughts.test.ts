import { describe, expect, it } from "vitest";
import { stepText, thoughtLine } from "../../web/src/ui/thoughts";

describe("a line of Recent thoughts", () => {
  it("shows a plan as its steps", () => {
    const l = { ok: true, thought: "We need wood", goal: "gather", steps: [{ do: "gather", what: "wood" }, { do: "experiment", with: ["stone", "wood"] }, { do: "sleep" }] };
    expect(thoughtLine(l)).toEqual({ quote: "We need wood", goal: "gather", rest: "gather wood → experiment stone+wood → sleep" });
    expect(stepText({ do: "craft", what: ["cord", "wood"] })).toBe("craft cord+wood");
  });

  it("shows a cascade choice that has no steps instead of throwing (issue #74)", () => {
    const l = { ok: true, chose: "E", confidence: 0.68, escalated: true };
    expect(() => thoughtLine(l)).not.toThrow();
    expect(thoughtLine(l)).toEqual({ quote: "", goal: "", rest: "picked option E (68% sure), then wrote its own plan" });
    expect(thoughtLine({ ok: true, chose: "B" }).rest).toBe("picked option B");
  });

  it("never throws on an entry it does not know", () => {
    for (const l of [{}, { ok: true }, { steps: null }, { steps: [null] }, null, undefined]) {
      expect(() => thoughtLine(l)).not.toThrow();
    }
  });
});
