import { describe, expect, it } from "vitest";
import { dropRepeatedIdeas, holdOrder, insightLabel, instinctChip, lifeLines, stallLine, thinkingLine, type LifeEvent, type Thinking } from "../../web/src/ui/watch";

const t = (p: Partial<Thinking>): Thinking => ({ brain: "m1", steps: 100, model_pct: 40, body_pct: 30, routine_pct: 20, instinct_pct: 10,
  fallback_pct: 0, on_instinct: false, why: "", ...p });

// ⚙ a world running without a model says so; one whose model is deciding does not
describe("instinctChip", () => {
  it("labels a world with no model, and one whose model has stopped deciding", () => {
    expect(instinctChip(t({ brain: "instinct", on_instinct: true, why: "no_model" }))!.text).toBe("⚙ running on instinct");
    expect(instinctChip(t({ on_instinct: true, why: "model_down", steps: 57 }))!.title).toContain("not answering");
    expect(instinctChip(t({ brain: "instinct", on_instinct: true, why: "no_model", model_pct: 0 }))!.title).toContain("every chit");
    // before the server has answered, a world whose brain is instinct is still said to be
    expect(instinctChip(undefined, "instinct")).not.toBeNull();
  });
  it("does not say every chit acts on instinct when a voyager brought its model", () => {
    const c = instinctChip(t({ brain: "instinct", on_instinct: true, why: "no_model", model_pct: 12.4 }))!;
    expect(c.title).not.toContain("every chit");
    expect(c.title).toContain("12% of recent steps");
  });
  it("says nothing while a model is thinking, or only busy", () => {
    expect(instinctChip(t({ why: "busy", model_pct: 0, fallback_pct: 80 }))).toBeNull();
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
      .toBe("Model not answering: instinct 90% · body reflexes 10% of the last 100 steps");
    expect(thinkingLine(t({ why: "busy", model_pct: 0, instinct_pct: 80, body_pct: 20, routine_pct: 0, fallback_pct: 75.4, waiting_pct: 33.3 })))
      .toBe("The model is busy (75% of steps fell back to instinct, chits waited 33% of the time): instinct 80% · body reflexes 20% of the last 100 steps");
    expect(thinkingLine(t({ why: "busy", model_pct: 0, instinct_pct: 100, body_pct: 0, routine_pct: 0, fallback_pct: 100 })))
      .toBe("The model is busy (100% of steps fell back to instinct): instinct 100% of the last 100 steps");
  });
  it("has nothing to share before any step is finished", () => {
    expect(thinkingLine(null)).toBe("No steps finished yet.");
    expect(thinkingLine(t({ steps: 0 }))).toBe("No steps finished yet.");
  });
});

describe("dropRepeatedIdeas", () => {
  const ev = (seq: number, kind: string, knowledge?: string, how?: string) =>
    ({ seq, kind, data: knowledge ? { knowledge, how } : {} });
  it("tells each idea once per world, a first discovery counting as its telling", () => {
    const evs = [ev(1, "discovery", "design:forge", "insight"), ev(2, "learned", "design:forge", "insight"), ev(3, "birth"),
      ev(4, "learned", "design:kiln", "insight"), ev(5, "learned", "design:kiln", "insight"), ev(6, "learned", "design:forge", "insight")];
    expect(dropRepeatedIdeas(evs).map((e) => e.seq)).toEqual([1, 3, 4]);
  });
  it("leaves other learning alone", () => {
    const evs = [ev(1, "learned", "recipe:cord", "taught"), ev(2, "learned", "recipe:cord", "taught"), ev(3, "learned", "recipe:cord", "insight")];
    expect(dropRepeatedIdeas(evs).map((e) => e.seq)).toEqual([1, 2, 3]);
  });
});

// 👥 the People list re-sorted at speed under the pointer, and a click picked the wrong chit
describe("holdOrder", () => {
  it("keeps the order the list had when the pointer arrived", () => {
    expect(holdOrder(["a", "b", "c"], ["c", "a", "b"])).toEqual(["a", "b", "c"]);
  });
  it("drops the departed and puts newcomers at the end", () => {
    expect(holdOrder(["a", "b", "c"], ["d", "c", "a"])).toEqual(["a", "c", "d"]);
  });
  it("is the fresh order when nothing is held", () => {
    expect(holdOrder(null, ["c", "a"])).toEqual(["c", "a"]);
  });
});

describe("lifeLines", () => {
  const e = (seq: number, kind: string, role: LifeEvent["role"] = "self"): LifeEvent => ({ seq, day: seq, kind, role, text: kind, importance: 3 });
  it("puts a life in order, born to died, with an icon for each moment", () => {
    const l = lifeLines([e(9, "death"), e(1, "birth"), e(5, "birth", "child"), e(3, "invention"), e(4, "mystery")]);
    expect(l.map((x) => x.seq)).toEqual([1, 3, 4, 5, 9]);
    expect(l.map((x) => x.icon)).toEqual(["🍼", "💡", "·", "👶", "🕯"]);
  });
});

describe("lifeLines folding", () => {
  const l = (seq: number, day: number, what?: string, kind = "learned"): LifeEvent => ({ seq, day, kind, role: "self", text: `${kind} ${what}`, importance: 2, what });
  it("folds a day's learning into one line, and tells a newborn's birth first", () => {
    const evs = [l(1, 3, "cord"), l(2, 3, "clay pot"), l(3, 3, undefined, "birth"), l(4, 3, "a"), l(5, 3, "b"), l(6, 3, "c"), l(7, 3, "d"),
      l(8, 4, "brick"), l(9, 4, undefined, "invention"), l(10, 4, "kiln")];
    const out = lifeLines(evs);
    expect(out.map((x) => x.kind)).toEqual(["birth", "learned", "learned", "invention", "learned"]);
    expect(out[1].text).toBe("Learned 6 things: cord, clay pot, a, b, c and 1 more");
    expect(out[2].text).toBe("learned brick");  // (one thing stays as told)
    expect(out[4].text).toBe("learned kiln");  // (another moment between breaks the run)
  });
});

// 📚 the counter read "1094.8/24": insight piles up while the village holds as many open ideas as it can
describe("insightLabel", () => {
  it("counts towards the next idea", () => {
    expect(insightLabel(7.6, 24).text).toBe("7/24 insight to the next");
  });
  it("says the idea waits once the mark is passed, instead of a count over it", () => {
    const l = insightLabel(1094.8, 24);
    expect(l.text).toBe("next idea ready: waits for an open one to come true");
    expect(l.text).not.toContain("1094");
    expect(l.title).toContain("1095");
    expect(insightLabel(7.63, 24.5).title).toBe("7 of 25 insight");
    expect(insightLabel(24, 24).text).toContain("ready");
  });
  it("has no mark to count to in a world without scholars' ideas", () => {
    expect(insightLabel(3.2, 0).text).toBe("3 insight");
  });
});

describe("stallLine", () => {
  const ladder = [{ reached: true, day: null }, { reached: true, day: 5 }, { reached: true, day: 12 }, { reached: false, day: null }];
  const reasons = [{ kind: "paused", text: "The game is paused." }, { kind: "failure", text: "No sand near home: 35 failed tries so far." }];
  it("stays quiet while the age is young", () => {
    expect(stallLine(21, ladder, "Make brick", reasons)).toBeNull();
  });
  it("says how long, the step they are on and the biggest holdup", () => {
    expect(stallLine(52, ladder, "Make brick (4 of 10 for the kiln)", reasons))
      .toBe("No new age for 40 days. They are on: make brick (4 of 10 for the kiln). Biggest holdup: no sand near home: 35 failed tries so far.");
    expect(stallLine(22, ladder, null, null)).toBe("No new age for 10 days.");
  });
  it("counts from day 1 before any age is reached", () => {
    expect(stallLine(15, [{ reached: true, day: null }, { reached: false, day: null }], null, null)).toBe("No new age for 14 days.");
  });
});
