"""Print the divergence report of the running game (T23).

    python -m chits.tools.compare [--url http://127.0.0.1:8000] [--tweet]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--tweet", action="store_true", help="print the 280-character post instead of the report")
    args = ap.parse_args(argv)
    try:
        with urllib.request.urlopen(args.url.rstrip("/") + "/api/compare", timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"The game said: {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Couldn't reach Little Chits at {args.url} ({e}). Is it running?", file=sys.stderr)
        return 1
    print(data["tweet"] if args.tweet else data["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
