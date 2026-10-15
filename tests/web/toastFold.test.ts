import { describe, expect, it } from "vitest";
import { foldToasts, TOAST_SHOWN, type Toast } from "../../web/src/state/milestones";

const toast = (seq: number, day: number, kind = "discovery", world = "A"): Toast =>
  ({ seq, tick: (day - 1) * 240 + seq, kind, text: `${kind} ${seq}`, importance: 5, actor: null, x: null, y: null, data: {}, world, key: `${world}-${seq}` });

// at 2× and up a burst of milestones stacked over the map, two worlds' interleaved out of day order
describe("foldToasts", () => {
  it("shows a few toasts as they are, in day order", () => {
    const v = foldToasts([toast(2, 5, "discovery", "B"), toast(1, 3)], false);
    expect(v.shown.map((t) => t.key)).toEqual(["A-1", "B-2"]);
    expect(v.chip).toBe("");
  });

  it("folds a burst into one chip, the newest left showing", () => {
    const v = foldToasts([toast(4, 9), toast(1, 2), toast(3, 7, "project_done"), toast(2, 4, "era")], false);
    expect(v.shown.map((t) => t.seq)).toEqual([4]);
    expect(v.folded.map((t) => t.seq)).toEqual([1, 2, 3]);
    expect(v.chip).toBe("3 milestones ▸");
    expect(v.shown.length + 1).toBeLessThanOrEqual(TOAST_SHOWN);
  });

  it("opens to every toast in day order, and says 'more' for a mix", () => {
    const ts = [toast(3, 6), toast(1, 2, "death"), toast(2, 4)];
    expect(foldToasts(ts, true).shown.map((t) => t.seq)).toEqual([1, 2, 3]);
    expect(foldToasts(ts, false).chip).toBe("2 more ▸");
    expect(foldToasts(ts.slice(0, 1).concat(toast(5, 1), toast(6, 1)), false).chip).toBe("2 milestones ▸");
  });

  it("never folds an error, and keeps the arrival order on the same tick", () => {
    const err: Toast = { ...toast(0, 1, "error"), tick: 0, key: "err-1", world: "" };
    const v = foldToasts([toast(1, 3), err, toast(2, 3), toast(3, 3)], false);
    expect(v.shown[v.shown.length - 1].key).toBe("err-1");
    expect(v.folded).not.toContainEqual(err);
    const same = [{ ...toast(1, 3), tick: 500 }, { ...toast(2, 3), tick: 500 }];
    expect(foldToasts(same, true).shown.map((t) => t.seq)).toEqual([1, 2]);
  });
});
