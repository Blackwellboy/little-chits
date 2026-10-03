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

describe("api", () => {
  it("marks a request that got no answer at all, so it gets a toast too", async () => {
    const { api, ApiError } = await import("../../web/src/net/socket");
    const real = globalThis.fetch;
    const g = globalThis as any;
    const hadLocation = "location" in g;
    if (!hadLocation) g.location = { search: "" };  // (the test runner has no page)
    globalThis.fetch = (() => Promise.reject(new TypeError("Failed to fetch"))) as typeof fetch;
    try {
      const e = await api("/api/health").catch((x) => x);
      expect(e).toBeInstanceOf(ApiError);
      expect(errorText(e)).toBe("Can't reach the game server (Failed to fetch)");
    } finally {
      globalThis.fetch = real;
      if (!hadLocation) delete g.location;
    }
  });
});
