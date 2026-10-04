import { describe, expect, it } from "vitest";
import { popCapText, validCap } from "../../web/src/ui/popCap";

describe("chits per world", () => {
  const free = { cap: null, min: 6, island: 90 };
  const held = { cap: 20, min: 6, island: 90 };

  it("says plainly what a limit does and that nobody is removed", () => {
    expect(popCapText(held)).toBe("Each world is held at 20 chits. Nobody is removed: births pause until a world is below 20.");
    expect(popCapText(free)).toContain("No limit beyond the island's own (90)");
  });

  it("takes a whole number between the smallest a game allows and the island's own limit", () => {
    expect(validCap(20, free)).toBe(true);
    expect(validCap(6, free)).toBe(true);
    expect(validCap(90, free)).toBe(true);
    expect(validCap(5, free)).toBe(false);
    expect(validCap(91, free)).toBe(false);
    expect(validCap(20.5, free)).toBe(false);
    expect(validCap(Number.NaN, free)).toBe(false);
  });
});
