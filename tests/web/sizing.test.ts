import { describe, expect, it } from "vitest";
import { Advice, adviceLine, clampChits, followAdvice } from "../../web/src/ui/sizing";

// Size the world to the model: the New game dialog says how many chits the chosen brains keep up with, and offers
// that number in one click. A number the user typed is theirs.
const advice = (chits: number | null, text: string, unmeasured: string[] = []): Advice => ({ chits, text, unmeasured, limited_by: null });

describe("adviceLine", () => {
  it("warns and offers the model's number when the world is bigger than the model keeps up with", () => {
    const l = adviceLine(advice(13, "Qwen keeps up with about 13 chits."), 18);
    expect(l.level).toBe("warn");
    expect(l.use).toBe(13);
    expect(l.text).toBe("Qwen keeps up with about 13 chits. With 18 chits most moves will be instinct.");
  });
  it("is content when the world fits, and offers the bigger number when there is room", () => {
    expect(adviceLine(advice(13, "x"), 13)).toMatchObject({ level: "good", use: null });
    expect(adviceLine(advice(40, "x"), 18)).toMatchObject({ level: "good", use: 40 });
  });
  it("offers to measure a brain with no measurement, and has no number for instinct", () => {
    expect(adviceLine(advice(null, "Qwen: Speed not measured yet.", ["qwen"]), 18)).toMatchObject({ use: null, measure: true });
    const i = adviceLine(advice(null, "Instinct has no limit: any number of chits works."), 60);
    expect(i).toMatchObject({ use: null, measure: false, level: "muted" });
    expect(adviceLine(null, 18).text).toBe("");
  });
});

describe("followAdvice", () => {
  it("keeps a number the user typed when the advice changes", () => {
    expect(followAdvice(25, false, advice(13, "x"))).toBe(25);
  });
  it("moves a number taken from the advice with the advice", () => {
    expect(followAdvice(13, true, advice(6, "x"))).toBe(6);
    expect(followAdvice(13, true, advice(null, "x"))).toBe(13);
    expect(followAdvice(13, true, null)).toBe(13);
  });
  it("stays within what a new game accepts", () => {
    expect(clampChits(1)).toBe(2);
    expect(clampChits(200)).toBe(60);
    expect(followAdvice(13, true, advice(90, "x"))).toBe(60);
  });
});
