// run: cd web && npx vitest run --root .. --globals tests/web/moment.test.ts
import { parseMomentParams, parseRecordParams } from "../../web/src/ui/recordLayout";

test("a moment close-up: where, how close, and the caption", () => {
  const q = "?record=1&world=A&focus=41.5,23&zoom=3.8&caption=Molo+discovered+bread&label=World+A+%C2%B7+Day+12";
  expect(parseMomentParams(q)).toEqual({ x: 41.5, y: 23, zoom: 3.8, caption: "Molo discovered bread", label: "World A · Day 12" });
  expect(parseRecordParams(q)).toMatchObject({ record: true, world: "A" }); // record mode itself is unchanged
});

test("no focus, no moment; odd values are tamed", () => {
  expect(parseMomentParams("?record=1&world=A")).toBeNull();
  expect(parseMomentParams("?focus=abc")).toBeNull();
  expect(parseMomentParams("?focus=10,20")).toMatchObject({ zoom: 3.5, caption: "", label: "" });
  expect(parseMomentParams("?focus=10,20&zoom=99").zoom).toBe(7);
  expect(parseMomentParams("?focus=10,20&zoom=-1").zoom).toBe(3.5);
  expect(parseMomentParams(`?focus=1,2&caption=${"x".repeat(500)}`)!.caption.length).toBe(200);
});
