"""One command from `git clone` to watching a civilisation (T29).

    little-chits [--port 8000] [--model http://127.0.0.1:18090/v1] [--mode versus|single|culture] [--no-browser]

With no model given, Little Chits looks for model servers on this machine the first time it runs:
two found means model vs model on the same island, one means a single-model world.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
import threading
import time
import webbrowser
from typing import List, Optional


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="little-chits", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1", help="who may connect (default: only this computer)")
    p.add_argument("--data", default=None, help="where worlds are saved (default ./data)")
    p.add_argument("--model", default=None, help="an OpenAI-compatible model server, e.g. http://127.0.0.1:18090/v1")
    p.add_argument("--mode", choices=["versus", "single", "culture", "rivals"], default=None)
    p.add_argument("--no-scan", action="store_true", help="don't look for model servers on first run")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--speed", type=int, default=None)
    p.add_argument("--token", default=None, help="require this access token for anything that changes the world")
    p.add_argument("--insecure", action="store_true", help="allow a public --host without a token (not recommended)")
    return p


def _loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_bind(host: str, token: Optional[str], insecure: bool) -> Optional[str]:
    """None if it's safe to start; otherwise a message saying why not."""
    if _loopback(host) or token or insecure:
        return None
    return (f"Refusing to listen on {host} without an access token: anyone on your network could change your worlds.\n"
            f"Add --token SOMETHING-SECRET (then open http://<this-machine>:PORT/?token=SOMETHING-SECRET),\n"
            f"or --insecure if you really mean it, or leave --host at 127.0.0.1.")


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    token = args.token or os.environ.get("CHITS_TOKEN") or None
    err = check_bind(args.host, token, args.insecure)
    if err:
        print(err, file=sys.stderr)
        return 2
    env = {"CHITS_DATA_DIR": args.data, "CHITS_MODEL_URL": args.model, "CHITS_MODE": args.mode,
           "CHITS_SPEED": None if args.speed is None else str(args.speed), "CHITS_TOKEN": token,
           "CHITS_AUTODETECT": "0" if args.no_scan else None}
    for k, v in env.items():
        if v:
            os.environ[k] = v
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}/"
    if token:
        url += f"?token={token}"
    if not args.no_browser:
        def _open() -> None:
            time.sleep(2.0)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()
    print(f"Little Chits is starting: {url}", flush=True)
    import uvicorn

    uvicorn.run("chits.app:app", host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
