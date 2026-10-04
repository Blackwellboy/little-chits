import { describe, expect, it } from "vitest";
import { lookButton } from "../../web/src/ui/look";

// the Look button did nothing during an experiment: the server refused (409) and the click swallowed it
describe("lookButton", () => {
  it("is locked during an experiment and says why", () => {
    const b = lookButton("default", "experiment");
    expect(b.disabled).toBe(true);
    expect(b.title).toContain("experiment");
    expect(b.label).toBe("classic");
  });
  it("switches between the looks in a play game", () => {
    expect(lookButton("default", "play")).toMatchObject({ disabled: false, next: "norse", label: "classic", glyph: "●" });
    expect(lookButton("norse", "play")).toMatchObject({ disabled: false, next: "default", label: "norse", glyph: "ᚠ" });
    expect(lookButton("norse", undefined).disabled).toBe(false);  // (no control state yet: as a play game)
  });
});
