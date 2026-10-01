/**
 * The live-stream protocol, kept pure so it can be tested without a browser.
 * The server stamps every message with a stream generation (`gen`) and a per-connection sequence (`seq`).
 * The session is only LIVE once a hello and a snapshot for every world in it have arrived; a gap in `seq`
 * means something was lost, so we ask for a resync and ignore everything until the next hello.
 */
export type StreamStatus = "connecting" | "syncing" | "live" | "reconnecting" | "offline";

export class StreamState {
  status: StreamStatus = "connecting";
  private gen: number | null = null;
  private lastSeq: number | null = null;
  private expect: Set<string> = new Set();
  private got: Set<string> = new Set();
  private awaitingHello = true;

  open() {
    this.status = "syncing";
    this.gen = null;
    this.lastSeq = null;
    this.expect.clear();
    this.got.clear();
    this.awaitingHello = true;
  }

  accept(msg: any): { deliver: boolean; resync: boolean } {
    const seq = typeof msg?.seq === "number" ? msg.seq : null;
    if (msg?.type === "hello") {
      this.gen = typeof msg.gen === "number" ? msg.gen : null;
      this.lastSeq = seq;
      this.expect = new Set((msg.worlds ?? []).map((w: any) => w.id));
      this.got.clear();
      this.awaitingHello = false;
      this.status = this.expect.size ? "syncing" : "live";
      return { deliver: true, resync: false };
    }
    if (this.awaitingHello) return { deliver: false, resync: false };
    if (this.gen !== null && typeof msg?.gen === "number" && msg.gen !== this.gen) return { deliver: false, resync: false };
    if (seq !== null && this.lastSeq !== null && seq !== this.lastSeq + 1) {
      this.awaitingHello = true;
      this.status = "syncing";
      return { deliver: false, resync: true };
    }
    if (seq !== null) this.lastSeq = seq;
    if (msg?.type === "snapshot" && msg.world?.id) {
      this.got.add(msg.world.id);
      if (this.status === "syncing" && [...this.expect].every((id) => this.got.has(id))) this.status = "live";
    }
    return { deliver: true, resync: false };
  }

  close(permanent: boolean) {
    this.status = permanent ? "offline" : "reconnecting";
    this.awaitingHello = true;
  }
}
