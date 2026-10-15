import { describe, expect, it } from "vitest";
import { mindDown, mindLabel, mindsDown } from "../../web/src/ui/mindState";
import type { BrainSummary } from "../../web/src/types";

// Live, World A's model stopped answering at day 806 and the pill still named it, as if it were thinking, for ~1,100
// days of instinct. A model the server says is down is named with its state wherever it is named.
const b = (over: Partial<BrainSummary> = {}): BrainSummary =>
  ({ id: "env", label: "env", thinking: 0, healthy: true, tok_s: 0, latency_ms: 0, ...over });

describe("mindState", () => {
  it("names a down model with its state, and an answering one plainly", () => {
    expect(mindLabel(b())).toBe("env");
    expect(mindLabel(b({ down: true, failing_since: 240 * 805 }))).toBe("env (not answering — instinct)");
    expect(mindLabel(undefined)).toBe("…");
    expect(mindDown(b({ id: "instinct", label: "Instinct (no model)", down: true }))).toBe(false);
  });

  it("keeps one line up per world whose model is down, with the day it stopped", () => {
    expect(mindsDown({ A: b(), B: b({ label: "gemma" }) })).toEqual([]);
    expect(mindsDown({ B: b({ label: "gemma", down: true, failing_since: 10 }), A: b({ down: true, failing_since: 240 * 805 + 3 }) }))
      .toEqual(["World A's mind env has stopped answering since day 806: the chits are running on instinct.",
                "World B's mind gemma has stopped answering since day 1: the chits are running on instinct."]);
  });
});

describe("mindState where the chits wait for their model", () => {
  it("says they wait, not that they run on instinct (model-led, model-only, experiment)", () => {
    const down = b({ down: true, failing_since: 240 * 2, chits_wait: true });
    expect(mindLabel(down)).toBe("env (not answering — waiting)");
    expect(mindsDown({ A: down })).toEqual(["World A's mind env has stopped answering since day 3: the chits wait for it."]);
  });
});
