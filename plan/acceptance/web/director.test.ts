import { Director, scoreEvent, type DirectorEvent } from "../../../web/src/render/director";

const ev = (seq: number, kind: string, importance: number, extra: Partial<DirectorEvent> = {}): DirectorEvent => ({
  seq, tick: seq * 10, kind, importance, x: seq, y: 2, text: `${kind} ${seq}`, world: "A", ...extra,
});
const agents = [
  { id: "a3", x: 1, y: 1, act: "walking" },
  { id: "a2", x: 5, y: 5, act: "building hut" },
  { id: "a1", x: 9, y: 9, act: "sleeping" },
];

test("scores", () => {
  expect(scoreEvent(ev(1, "discovery", 5))).toBe(70);
  expect(scoreEvent(ev(1, "built", 2))).toBe(28);
  expect(scoreEvent(ev(1, "speech", 1))).toBe(10);
});

test("cuts to the best recent event and dwells", () => {
  const d = new Director({ minDwellMs: 8000, idleMs: 12000 });
  d.offer(ev(1, "birth", 4), 0);
  d.offer(ev(2, "discovery", 5), 0);
  d.offer(ev(3, "speech", 1), 0); // ignored: importance < 3
  d.offer(ev(4, "built", 4, { x: null }), 0); // ignored: no position
  const s = d.current(100, "A", agents)!;
  expect(s.seq).toBe(2);
  expect(s.zoom).toBe(4.2);
  expect(s.until).toBe(8100);
  expect(d.current(5000, "A", agents)!.seq).toBe(2); // dwell
  const s2 = d.current(8200, "A", agents)!;
  expect(s2.seq).toBe(1);
  expect(s2.zoom).toBe(3.5);
});

test("filters by world and age", () => {
  const d = new Director({ maxAgeMs: 60000 });
  d.offer(ev(1, "storm", 4, { world: "B" }), 0);
  d.offer(ev(2, "birth", 4), 0);
  expect(d.current(70000, "A", agents)!.seq).toBe(-1); // too old -> idle cut
  const d2 = new Director();
  d2.offer(ev(1, "storm", 4, { world: "B" }), 0);
  expect(d2.current(10, "A", agents)!.seq).toBe(-1);
  expect(d2.current(10, "B", agents)!.seq).toBe(1);
});

test("idle cuts prefer busy chits and rotate", () => {
  const d = new Director({ idleMs: 12000 });
  const s = d.current(0, "A", agents)!;
  expect(s.seq).toBe(-1);
  expect([s.x, s.y]).toEqual([5, 5]); // a2 is building
  expect(s.caption).toBe("");
  expect(d.current(1000, "A", agents)!.x).toBe(5); // still dwelling
  const n = d.current(12001, "A", agents)!;
  expect([n.x, n.y]).not.toEqual([5, 5]); // rotates away from previous idle target
  expect(new Director().current(0, "A", [])).toBeNull();
});

test("captions are trimmed", () => {
  const d = new Director();
  d.offer(ev(1, "first", 5, { text: "x".repeat(200) }), 0);
  const c = d.current(1, "A", agents)!.caption;
  expect(c.length).toBeLessThanOrEqual(90);
  expect(c.endsWith("…")).toBe(true);
});
