// run: cd web && npx vitest run --root .. --globals tests/web/packFile.test.ts
import { packForReset, packLabel, readPackText } from "../../web/src/ui/packFile";

test("a picked file must be small JSON with an object at the top", () => {
  expect(readPackText('{"schema":1,"id":"honey"}')).toEqual({ ok: true, pack: { schema: 1, id: "honey" } });
  expect(readPackText("not json")).toMatchObject({ ok: false });
  expect(readPackText("[1,2]")).toMatchObject({ ok: false });
  expect(readPackText("null")).toMatchObject({ ok: false });
  expect(readPackText(`{"x":"${"a".repeat(70000)}"}`)).toMatchObject({ ok: false, error: expect.stringContaining("64 KB") });
});

test("the pack in play is named plainly", () => {
  expect(packLabel(null)).toBe("none");
  expect(packLabel({ id: "honey", name: "Honey", version: "1.0", sha256: "ab", items: ["a", "b", "c", "d"], recipes: ["a"] }))
    .toBe("Honey 1.0 (4 items, 1 recipe)");
});

test("the new game keeps, drops or replaces the pack, and an experiment never takes one", () => {
  const pack = { schema: 1 };
  expect(packForReset(null, false)).toBeUndefined(); // keep what the running game has
  expect(packForReset("none", false)).toEqual({});
  expect(packForReset(pack, false)).toBe(pack);
  expect(packForReset(pack, true)).toEqual({});
  expect(packForReset(null, true)).toEqual({});
});
