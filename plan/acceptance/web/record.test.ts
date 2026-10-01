import { parseRecordParams, stageSize } from "../../../web/src/ui/recordLayout";

test("defaults", () => {
  expect(parseRecordParams("")).toEqual({ record: false, aspect: "16:9", world: "A", director: false, captions: false, speed: null });
  expect(parseRecordParams("?record=1")).toEqual({ record: true, aspect: "16:9", world: "A", director: true, captions: true, speed: null });
});

test("params", () => {
  const p = parseRecordParams("?record=true&aspect=9:16&world=split&director=0&speed=25");
  expect(p).toEqual({ record: true, aspect: "9:16", world: "split", director: false, captions: true, speed: 25 });
  expect(parseRecordParams("?record=1&aspect=4:3&world=Z&speed=7")).toMatchObject({ aspect: "16:9", world: "A", speed: null });
  expect(parseRecordParams("?record=1&aspect=1%3A1").aspect).toBe("1:1");
});

test("stage sizes", () => {
  expect(stageSize("16:9", 1920, 1080)).toEqual({ width: 1920, height: 1080, left: 0, top: 0 });
  expect(stageSize("9:16", 1920, 1080)).toEqual({ width: 607, height: 1080, left: 656, top: 0 });
  expect(stageSize("1:1", 1000, 800)).toEqual({ width: 800, height: 800, left: 100, top: 0 });
  expect(stageSize("16:9", 800, 1000)).toEqual({ width: 800, height: 450, left: 0, top: 275 });
});
