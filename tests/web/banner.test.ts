import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bannerDriver, type Shown } from "../../web/src/ui/banner";
import type { Toast } from "../../web/src/state/milestones";

// A town or city banner fills the screen for 6.5 s. An ordinary toast arriving meanwhile cancelled its timer and
// nothing set another: the banner stayed until someone clicked it (Codex review of PR #70).
const toast = (key: string, kind: string, data: any = {}): Toast =>
  ({ seq: 0, tick: 0, kind, text: key, importance: 4, actor: null, x: null, y: null, data, world: "A", key } as Toast);

describe("bannerDriver", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("takes the banner down on time even when other toasts arrive while it is up", () => {
    const calls: (Shown | null)[] = [];
    const d = bannerDriver((s) => calls.push(s));
    const town = toast("town", "town_rank", { rank: "town" });
    d.update([town]);
    expect(calls.at(-1)?.key).toBe("town");
    vi.advanceTimersByTime(3000);
    d.update([town, toast("hut", "built")]);  // an ordinary toast: no new banner
    vi.advanceTimersByTime(3000);
    expect(calls.at(-1)?.key).toBe("town");  // still up at 6 s
    vi.advanceTimersByTime(600);
    expect(calls.at(-1)).toBeNull();  // gone at 6.5 s, counted from when it appeared
    expect(calls.length).toBe(2);
  });

  it("gives a second banner its own full time and shows each banner once", () => {
    const calls: (Shown | null)[] = [];
    const d = bannerDriver((s) => calls.push(s));
    const town = toast("town", "town_rank", { rank: "town" });
    const age = toast("age", "era");
    d.update([town]);
    vi.advanceTimersByTime(5000);
    d.update([town, age]);
    expect(calls.at(-1)?.key).toBe("age");
    vi.advanceTimersByTime(2000);  // the town's time would have run out here
    expect(calls.at(-1)?.key).toBe("age");
    vi.advanceTimersByTime(4600);
    expect(calls.at(-1)).toBeNull();
    d.update([town, age]);  // both seen: nothing comes back
    expect(calls.at(-1)).toBeNull();
  });

  it("stops its timer when the page lets go of it", () => {
    const calls: (Shown | null)[] = [];
    const d = bannerDriver((s) => calls.push(s));
    d.update([toast("news", "storyteller")]);
    d.stop();
    vi.advanceTimersByTime(10000);
    expect(calls.length).toBe(1);
  });
});
