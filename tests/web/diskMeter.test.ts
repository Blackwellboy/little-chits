// run: cd web && npx vitest run --root .. --globals tests/web/diskMeter.test.ts
import { diskMeter, parseCapGb, size } from "../../web/src/ui/diskMeter";

const GIB = 1024 ** 3;
const storage = (bytes: number, limit: number, free: number) =>
  ({ bytes, run_bytes: bytes, frames_bytes: 0, free_bytes: free, limit_bytes: limit, warning: "" });

test("the meter shows used, cap and free in plain sizes", () => {
  const m = diskMeter(storage(1.25 * GIB, 5 * GIB, 151 * GIB));
  expect(m).toMatchObject({ used: "1.3 GB", cap: "5.0 GB", free: "151 GB", percent: 25, over: false, capGb: 5 });
});

test("over the cap the bar is full and says so", () => {
  const m = diskMeter(storage(28.3 * GIB, 20 * GIB, 3 * GIB));
  expect(m).toMatchObject({ used: "28 GB", cap: "20 GB", percent: 100, over: true });
});

test("nothing recorded, and a disk that can't be read", () => {
  expect(diskMeter(storage(0, 5 * GIB, -1))).toMatchObject({ used: "0 MB", free: "unknown", percent: 0, over: false });
  expect(size(300 * 1024 ** 2)).toBe("300 MB");
});

test("the cap is editable within what the server accepts", () => {
  expect(parseCapGb("10")).toBe(10);
  expect(parseCapGb(" 2.5 ")).toBe(2.5);
  expect(parseCapGb("0.5")).toBeNull();
  expect(parseCapGb("501")).toBeNull();
  expect(parseCapGb("lots")).toBeNull();
  expect(parseCapGb("")).toBeNull();
});
