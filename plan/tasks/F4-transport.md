# F4 · A bounded, sequenced live stream

**Why:** today each browser gets an unbounded queue. A slow or backgrounded tab can pile up frames forever.
The UI also says LIVE as soon as the socket opens, before it has any world. And a stale socket from before a
reconnect can still deliver messages. A small, strict protocol fixes all three.

## Build
1. **Server.**
   - `Runtime.new_client_queue() -> asyncio.Queue(maxsize=256)`.
   - `Runtime.push(q, msg: dict)` stamps `msg["gen"] = self.gen` and `msg["seq"]` (a per-queue counter
     starting at 1), then enqueues the JSON.
     - When the queue is full, empty it, restart that queue's `seq` at 1, and enqueue a fresh hello
       (`{"type": "hello", "resync": true, …}`) plus snapshots. The browser always gets a consistent
       picture, never a gap it can't see.
   - `Runtime.gen` increments on every reset, restore and epoch fork. Every message a client receives goes
     through `push`, including hello, snapshot, frame, status and pong.
   - `/ws` uses `new_client_queue()`, and handles `{"type": "resync"}` by re-sending hello and snapshots.
2. **Client protocol:** a pure module `web/src/net/stream.ts` exporting `class StreamState`:
   - `status`: `"connecting" | "syncing" | "live" | "reconnecting" | "offline"`
   - `open()`: sets status `syncing` and forgets the last seq and gen.
   - `accept(msg)`: returns `{ deliver: boolean, resync: boolean }`.
     - A `hello` resets expectations: store its `gen` and `seq`, and remember which world ids it lists.
     - Status becomes `live` only when a snapshot has arrived for every world in the latest hello.
     - A message whose `gen` differs from the current one is dropped (`deliver: false`).
     - A seq gap (`seq` ≠ last + 1) → `{ deliver: false, resync: true }`, and status goes back to `syncing`
       until the next hello and snapshots.
   - `close(permanent)`: sets `reconnecting` or `offline`.
3. **Client socket.** `Socket` uses `StreamState`.
   - Each `connect()` gets a generation token, and handlers from an older WebSocket object are ignored.
   - A `resync` result sends `{"type": "resync"}`.
   - The UI connection label shows SYNCING while syncing.

## Done when
`python scripts/plan.py verify F4` passes.
