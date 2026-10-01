import { StreamState } from "../../../web/src/net/stream";

const hello = (gen: number, seq: number, ids = ["A", "B"]) => ({ type: "hello", gen, seq, worlds: ids.map((id) => ({ id })) });
const snap = (gen: number, seq: number, id: string) => ({ type: "snapshot", gen, seq, world: { id } });

test("live only after every world's snapshot", () => {
  const s = new StreamState();
  s.open();
  expect(s.status).toBe("syncing");
  expect(s.accept(hello(1, 1)).deliver).toBe(true);
  expect(s.status).toBe("syncing");
  s.accept(snap(1, 2, "A"));
  expect(s.status).toBe("syncing");
  s.accept(snap(1, 3, "B"));
  expect(s.status).toBe("live");
  expect(s.accept({ type: "frame", gen: 1, seq: 4 })).toEqual({ deliver: true, resync: false });
});

test("a gap asks for a resync; an old generation is ignored", () => {
  const s = new StreamState();
  s.open();
  s.accept(hello(2, 1, ["A"]));
  s.accept(snap(2, 2, "A"));
  expect(s.status).toBe("live");
  expect(s.accept({ type: "frame", gen: 2, seq: 5 })).toEqual({ deliver: false, resync: true });
  expect(s.status).toBe("syncing");
  expect(s.accept({ type: "frame", gen: 1, seq: 6 }).deliver).toBe(false);
  s.accept(hello(2, 1, ["A"]));
  s.accept(snap(2, 2, "A"));
  expect(s.status).toBe("live");
  s.close(false);
  expect(s.status).toBe("reconnecting");
  s.close(true);
  expect(s.status).toBe("offline");
});
