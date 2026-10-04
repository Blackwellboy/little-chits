import { describe, expect, it } from "vitest";
import { rowClicked } from "../../web/src/ui/listPosition";

describe("the Knowledge list remembers where its reader was", () => {
  it("opening an entry remembers the list position, and closing it keeps that to go back to", () => {
    const opened = rowClicked({ open: null, top: null }, "recipe:cord", 120);
    expect(opened).toEqual({ open: "recipe:cord", top: 120 });
    expect(rowClicked(opened, "recipe:cord", 900)).toEqual({ open: null, top: 120 });
  });

  it("going from one entry to another goes back to the second row, not the first", () => {
    // (the saved position was only taken when nothing was open: closing the second entry returned to the first row)
    const first = rowClicked({ open: null, top: null }, "recipe:cord", 120);
    const second = rowClicked(first, "design:kiln", 640);
    expect(second).toEqual({ open: "design:kiln", top: 640 });
    expect(rowClicked(second, "design:kiln", 2000)).toEqual({ open: null, top: 640 });
  });

  it("keeps the last known position when the list can't be read", () => {
    const first = rowClicked({ open: null, top: null }, "recipe:cord", 120);
    expect(rowClicked(first, "design:kiln", null)).toEqual({ open: "design:kiln", top: 120 });
  });
});
