/**
 * One WebSocket for everything, with heartbeat + exponential backoff.
 * The visible status only flips to "reconnecting" after a grace period, so a
 * transient blip never makes the UI flicker.
 */
import { StreamState } from "./stream";

export type ConnStatus = "connecting" | "syncing" | "live" | "reconnecting" | "offline";

type Handler = (msg: any) => void;

export class Socket {
  private ws: WebSocket | null = null;
  private retry = 0;
  private handlers: Handler[] = [];
  private statusHandlers: ((s: ConnStatus) => void)[] = [];
  private lastMsg = 0;
  private heartbeat: number | undefined;
  private downSince = 0;
  private graceTimer: number | undefined;
  status: ConnStatus = "connecting";
  private stream = new StreamState();
  private conn = 0; // generation token: handlers from an older WebSocket are ignored

  constructor(private url: string) {}

  onMessage(h: Handler) { this.handlers.push(h); }
  onStatus(h: (s: ConnStatus) => void) { this.statusHandlers.push(h); }

  private setStatus(s: ConnStatus) {
    if (s === this.status) return;
    this.status = s;
    this.statusHandlers.forEach((h) => h(s));
  }

  connect() {
    const ws = new WebSocket(this.url);
    this.ws = ws;
    const token = ++this.conn;
    const mine = () => token === this.conn;
    ws.onopen = () => {
      if (!mine()) return;
      this.retry = 0;
      this.lastMsg = performance.now();
      this.downSince = 0;
      window.clearTimeout(this.graceTimer);
      this.stream.open();
      this.setStatus(this.stream.status);
    };
    ws.onmessage = (ev) => {
      if (!mine()) return;
      this.lastMsg = performance.now();
      let msg: any;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const r = this.stream.accept(msg);
      this.setStatus(this.stream.status);
      if (r.resync) this.send({ type: "resync" });
      if (!r.deliver || msg.type === "pong") return;
      for (const h of this.handlers) h(msg);
    };
    ws.onclose = () => { if (mine()) this.scheduleReconnect(); };
    ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
    window.clearInterval(this.heartbeat);
    let lastBeat = performance.now();
    this.heartbeat = window.setInterval(() => {
      const now = performance.now();
      const late = now - lastBeat > 6000; // this 3 s timer ran late: the page itself was busy, not the link
      lastBeat = now;
      if (late) { this.lastMsg = now; return; } // give the queued messages a chance before calling the link dead
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping", t: Date.now() }));
        // frames arrive ~8/s; 10s of silence means the link is dead even if the socket claims otherwise
        if (performance.now() - this.lastMsg > 10000) this.ws.close();
      }
    }, 3000);
  }

  private scheduleReconnect() {
    if (!this.downSince) {
      this.downSince = performance.now();
      window.clearTimeout(this.graceTimer);
      this.graceTimer = window.setTimeout(() => {
        if (this.downSince) this.setStatus(this.retry > 6 ? "offline" : "reconnecting");
      }, 3000);
    }
    const delay = Math.min(8000, 400 * Math.pow(1.7, this.retry++)) * (0.8 + Math.random() * 0.4);
    window.setTimeout(() => this.connect(), delay);
  }

  send(msg: any) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }
}

/** The access token (T29): read from ?token= once, then remembered in this browser. */
export function accessToken(): string {
  try {
    const q = new URLSearchParams(location.search).get("token");
    if (q) localStorage.setItem("chits:token", q);
    return q || localStorage.getItem("chits:token") || "";
  } catch {
    return new URLSearchParams(location.search).get("token") || "";
  }
}

export function socketUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const t = accessToken();
  return `${proto}://${location.host}/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}

/** API URLs used by img/a/download elements cannot send an Authorization header, so carry the remembered token. */
export function authedUrl(path: string): string {
  const t = accessToken();
  if (!t) return path;
  return `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(t)}`;
}

/** The server's own words for a failed request: api() throws "<status> <body>", and the body is FastAPI's
 *  {"detail": "..."} (issue #63: a 409 only ever reached the browser console). */
/** A request the game server refused, or couldn't be sent at all (the server restarting, say). */
export class ApiError extends Error {}

export function errorText(e: unknown): string {
  const m = String((e as Error)?.message ?? e).match(/^(\d{3}) ([\s\S]*)$/);
  if (!m) return String((e as Error)?.message ?? e);
  try {
    const d = JSON.parse(m[2]).detail;
    if (d) return typeof d === "string" ? d : JSON.stringify(d);
  } catch { /* not JSON */ }
  return `${m[1]} ${m[2].slice(0, 200)}`;
}

export async function api<T = any>(path: string, body?: any, method?: string): Promise<T> {
  const t = accessToken();
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (t) headers["Authorization"] = `Bearer ${t}`;
  let r: Response;
  try {
    r = await fetch(path, {
      method: method || (body !== undefined ? "POST" : "GET"),
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {  // (no answer at all: it gets a toast too, Codex review)
    throw new ApiError(`Can't reach the game server (${(e as Error)?.message ?? e})`);
  }
  if (!r.ok) throw new ApiError(`${r.status} ${await r.text()}`);
  return r.json();
}
