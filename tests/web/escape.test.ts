import { describe, expect, it } from "vitest";
import { dispatchEscape, ESC_GOD_TOOL, ESC_INSPECTOR, ESC_MENU, isFormControl, type EscapeLayer } from "../../web/src/ui/escape";

// one Escape used to close the ⋯ menu and the Inspector together, and the god tool's turn hung on mount order
const layer = (rank: number, took: boolean, log: string[], name: string): EscapeLayer =>
  ({ rank, handle: () => { log.push(name); return took; } });

describe("dispatchEscape", () => {
  it("gives the key to the top layer alone, whatever order they were added in", () => {
    const log: string[] = [];
    const ls = [layer(ESC_INSPECTOR, true, log, "inspector"), layer(ESC_MENU, true, log, "menu"), layer(ESC_GOD_TOOL, true, log, "god")];
    expect(dispatchEscape(ls, null)).toBe(true);
    expect(log).toEqual(["menu"]);
  });
  it("passes it down past a layer with nothing to close", () => {
    const log: string[] = [];
    const ls = [layer(ESC_INSPECTOR, true, log, "inspector"), layer(ESC_GOD_TOOL, false, log, "god")];
    expect(dispatchEscape(ls, null)).toBe(true);
    expect(log).toEqual(["god", "inspector"]);
    expect(dispatchEscape([layer(ESC_INSPECTOR, false, [], "x")], null)).toBe(false);
  });
  it("asks the latest of equal layers first", () => {
    const log: string[] = [];
    dispatchEscape([layer(ESC_MENU, true, log, "skip"), layer(ESC_MENU, true, log, "more")], null);
    expect(log).toEqual(["more"]);
  });
  it("leaves a key press in a form control to the control", () => {
    const log: string[] = [];
    for (const tagName of ["SELECT", "INPUT", "TEXTAREA"]) expect(dispatchEscape([layer(ESC_INSPECTOR, true, log, "i")], { tagName })).toBe(false);
    expect(dispatchEscape([layer(ESC_INSPECTOR, true, log, "i")], { tagName: "DIV", isContentEditable: true })).toBe(false);
    expect(log).toEqual([]);
    expect(isFormControl({ tagName: "BUTTON" })).toBe(false);
  });
});
