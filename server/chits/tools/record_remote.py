"""Auto-record a Little Chits server that is already running, from outside and read-only: the same day
timelapses, stories and live moment close-ups as the 🎞 recorder built into the server, into a folder of your own.

    python -m chits.tools.record_remote --server http://127.0.0.1:8010 --out /tmp/rec --minutes 10

It only reads the server: the event stream on /ws (as any viewer does) and GET /api/run, /api/worlds and
/api/worlds/<w>/events. The pages it films are ordinary record-mode viewers. --page films the web app from another
address (a newer build of it, say, proxied to the same server); by default the server's own. Chronicle pages
aren't fetched (asking for one can start a narration), so the day stories hold what happened and the moments.
Needs node + Playwright and ffmpeg, like the built-in recorder.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from ..recorder import TICKS_PER_DAY, Recorder


def _get(base: str, path: str, **params: Any) -> Any:
    url = base.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


class RemoteStore:
    def __init__(self, base: str) -> None:
        self.base = base

    def events(self, world_id: str, *, since_tick: int = 0, until_tick: Optional[int] = None, min_importance: int = 1,
               limit: int = 500, epoch: Optional[str] = None) -> List[Dict[str, Any]]:
        evs = _get(self.base, f"/api/worlds/{world_id}/events", since=since_tick, min_importance=min_importance,
                   limit=limit)
        return [e for e in evs if until_tick is None or e["tick"] < until_tick]


class RemoteRuntime:
    """Just enough of chits.runtime.Runtime for a Recorder, fed from the server's HTTP API and event stream."""

    def __init__(self, server: str, out: Path) -> None:
        self.server = server.rstrip("/")
        self.data_dir = out
        run = _get(self.server, "/api/run")
        self.run_id = run.get("run_id") or "remote"
        self.mode = run.get("mode", "")
        self.store = RemoteStore(self.server)
        self.worlds: Dict[str, SimpleNamespace] = {}
        self._names: Dict[str, Dict[str, str]] = {}
        self._brains: Dict[str, Dict[str, Any]] = {}
        for m in _get(self.server, "/api/worlds"):
            self.worlds[m["id"]] = SimpleNamespace(id=m["id"], name=m.get("name", m["id"]), label=m.get("label", ""),
                                                   epoch=m.get("epoch"), tick=(m.get("clock") or {}).get("tick", 0),
                                                   agents={}, dead={}, beliefs={},
                                                   timeline=lambda ep=m.get("epoch"): [(ep, None)])  # the server reads its own
            self._brains[m["id"]] = m.get("brain") or {}

    def names(self, w: Any) -> Dict[str, str]:
        return dict(self._names.get(w.id, {}))

    def brain_summary(self) -> Dict[str, Any]:
        return self._brains

    def take(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fold one stream message into the worlds; returns the events it carried."""
        kind = msg.get("type")
        if kind in ("hello", "status") and isinstance(msg.get("brains"), dict):
            self._brains.update(msg["brains"])
        wid = msg.get("world") if kind == "frame" else (msg.get("world") or {}).get("id") if kind == "snapshot" else None
        w = self.worlds.get(wid) if isinstance(wid, str) else None
        if w is None:
            return []
        w.tick = (msg.get("clock") or {}).get("tick", w.tick)
        agents = msg.get("agents")
        if agents is not None:
            names = self._names.setdefault(w.id, {})
            now = {}
            for a in agents:
                names[a["id"]] = a.get("name", a["id"])
                now[a["id"]] = SimpleNamespace(id=a["id"], name=a.get("name"), x=a.get("x", 0), y=a.get("y", 0))
            w.agents = now
        # a snapshot carries recent history the recorder has already seen (or missed): only live frames count
        return list(msg.get("events") or []) if kind == "frame" else []


def run(server: str, out: Path, page: Optional[str], minutes: float, aspect: str) -> int:
    import websockets  # uvicorn[standard] brings it

    out.mkdir(parents=True, exist_ok=True)
    rt = RemoteRuntime(server, out)
    rec = Recorder(rt)
    rec.settings.update(enabled=True, url=(page or server).rstrip("/"), aspect=aspect, moments=True)
    rec._save()
    missing = rec.missing()
    if missing:
        print("Can't record: missing " + "; ".join(missing), file=sys.stderr)
        return 2
    rec.start()
    print(f"recording run {rt.run_id} of {server} into {rec.dir} (pages from {rec.settings['url']})", flush=True)

    # the stream is drained on its own, without pause: a viewer that falls behind gets resynced by the server
    # (a fresh snapshot of every world, costly on a big island). Recording work happens on this thread.
    inbox: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
    deadline = time.monotonic() + minutes * 60
    ws_url = "ws" + rt.server[4:] + "/ws"

    async def reader() -> None:
        while time.monotonic() < deadline:  # the server restarting is no reason to stop: wait and reconnect
            try:
                async with websockets.connect(ws_url, max_size=None, open_timeout=30) as ws:
                    while time.monotonic() < deadline:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        except asyncio.TimeoutError:
                            continue
                        inbox.put(json.loads(raw))
            except (OSError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as e:
                print(f"stream lost ({e}); reconnecting", flush=True)
                await asyncio.sleep(5)
        inbox.put(None)

    t = threading.Thread(target=lambda: asyncio.run(reader()), daemon=True)
    t.start()
    recorded: Optional[int] = None
    next_watch = 0.0
    try:
        while True:
            try:
                msg = inbox.get(timeout=1)
            except queue.Empty:
                msg = {}
                if not t.is_alive():
                    break
            if msg is None:
                break
            for e in rt.take(msg):
                rec.on_event(msg["world"], e)
            # a day is handed over once every world has finished it (as the server's own recorder does)
            if rt.worlds and msg.get("type") == "frame":
                done = min((w.tick - 10) // TICKS_PER_DAY for w in rt.worlds.values())
                if recorded is None or done < recorded:
                    recorded = done
                elif done > recorded:
                    recorded = done
                    print(f"day {done} ended: encoding its clip", flush=True)
                    rec.day_ended(done)
            if time.monotonic() >= next_watch:
                next_watch = time.monotonic() + 5
                rec.watch()
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
        rec._collect_moments()  # one the browser finished as it was stopped
        for th in list(rec._threads):
            th.join(timeout=120)
    print(f"stopped. {rec.last_error or ''}".strip(), flush=True)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m chits.tools.record_remote", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default="http://127.0.0.1:8000", help="the running game (only read)")
    p.add_argument("--out", required=True, help="where recordings/<run>/... go")
    p.add_argument("--page", default=None, help="film the web app from this address instead (same server behind it)")
    p.add_argument("--minutes", type=float, default=10.0)
    p.add_argument("--aspect", choices=["16:9", "9:16", "1:1"], default="16:9")
    a = p.parse_args(argv)
    return run(a.server, Path(a.out), a.page, a.minutes, a.aspect)


if __name__ == "__main__":
    sys.exit(main())
