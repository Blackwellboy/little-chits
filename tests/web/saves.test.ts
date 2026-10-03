import { describe, expect, it } from "vitest";
import { ApiError, errorText } from "../../web/src/net/socket";
import { fetchSaveFile, importSaveFile, loadConfirm, SAVE_FILE_MAX, savedAgo, saveFileName, saveFileProblem, saveLine,
  type SaveRow } from "../../web/src/ui/saves";

// 💾 Saves in the main UI: what a row says, what Load asks first, and the save file's trip to the server.
const row: SaveRow = { id: 3, name: "before winter", created: 1000, tick: 240 * 311 + 7, day: 312, population: 41, era: "Iron Age" };

describe("a save's row", () => {
  it("says the day, the population, the era and when it was made", () => {
    expect(saveLine(row, 1000 + 5 * 60)).toBe("Day 312 · 41 chits · Iron Age · saved 5 min ago");
    expect(saveLine({ ...row, population: 1, imported: true }, 1010)).toBe("Day 312 · 1 chit · Iron Age · saved just now · imported");
  });
  it("still says the day of a save that has no summary", () => {
    expect(saveLine({ id: 1, name: "old", created: 0, tick: 480 }, 2 * 86400)).toBe("Day 3 · saved 2 days ago");
  });
  it("counts time in plain words", () => {
    expect([savedAgo(100, 90), savedAgo(0, 59), savedAgo(0, 3599), savedAgo(0, 3600), savedAgo(0, 86400)])
      .toEqual(["just now", "just now", "59 min ago", "1 h ago", "1 day ago"]);
  });
});

describe("loading a save", () => {
  it("asks first, and says it starts a new timeline and marks the game", () => {
    const text = loadConfirm(row);
    expect(text).toContain("Load “before winter”?");
    expect(text).toContain("back to day 312");
    expect(text).toContain("a new timeline starts");
    expect(text).toContain("marked as modified");
  });
});

describe("a save file", () => {
  it("gets a name that is safe everywhere", () => {
    expect(saveFileName("before winter")).toBe("little-chits-before-winter.lcsave");
    expect(saveFileName("../../etc/passwd")).toBe("little-chits-etc-passwd.lcsave");
    expect(saveFileName("…")).toBe("little-chits-save.lcsave");
  });
  it("is turned away before the upload when it is empty or too big", () => {
    expect(saveFileProblem({ name: "a.lcsave", size: 0 })).toBe("This file is empty.");
    expect(saveFileProblem({ name: "a.lcsave", size: SAVE_FILE_MAX + 1 })).toBe("This file is too big (the limit is 64 MB).");
    expect(saveFileProblem({ name: "a.lcsave", size: 5000 })).toBe("");
  });
  it("travels with the access token in a header, and a refusal keeps the server's words", async () => {
    const g = globalThis as any;
    const real = globalThis.fetch;
    const hadLocation = "location" in g, hadStorage = "localStorage" in g;
    if (!hadLocation) g.location = { search: "?token=sesame" };
    if (!hadStorage) g.localStorage = { getItem: () => null, setItem: () => {} };
    const calls: { path: string; init: RequestInit }[] = [];
    try {
      globalThis.fetch = ((path: string, init: RequestInit) => {
        calls.push({ path, init });
        return Promise.resolve(new Response(JSON.stringify({ id: 9, name: "x", created: 1, tick: 2 }), { status: 200 }));
      }) as typeof fetch;
      expect((await importSaveFile(new Blob(["{}"]))).id).toBe(9);
      await fetchSaveFile(7);
      expect(calls.map((c) => [c.path, c.init.method ?? "GET", (c.init.headers as any).Authorization]))
        .toEqual([["/api/saves/import", "POST", "Bearer sesame"], ["/api/saves/7/export", "GET", "Bearer sesame"]]);
      globalThis.fetch = (() => Promise.resolve(new Response('{"detail":"This file is not a Little Chits save."}', { status: 400 }))) as typeof fetch;
      const e = await importSaveFile(new Blob(["nope"])).catch((x) => x);
      expect(e).toBeInstanceOf(ApiError);
      expect(errorText(e)).toBe("This file is not a Little Chits save.");
    } finally {
      globalThis.fetch = real;
      if (!hadLocation) delete g.location;
      if (!hadStorage) delete g.localStorage;
    }
  });
});
