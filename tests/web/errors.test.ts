import { describe, expect, it } from "vitest";
import { errorText } from "../../web/src/net/socket";

// a failed request says the server's reason, not "409 {json}" in the console (issue #63)
describe("errorText", () => {
  it("gives FastAPI's detail", () => {
    expect(errorText(new Error('409 {"detail":"brains can\'t be swapped during an experiment run"}')))
      .toBe("brains can't be swapped during an experiment run");
  });
  it("falls back to the status and the start of the body", () => {
    expect(errorText(new Error("502 Bad Gateway"))).toBe("502 Bad Gateway");
    expect(errorText(new Error("network down"))).toBe("network down");
  });
});
