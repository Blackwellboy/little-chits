"""python -m chits.lab run PROTOCOL --out DIR [--jobs N] [--url BRAIN=URL ...] | resume DIR [--jobs N] | analyze DIR [--unblind]
| lint PACK (a TreatmentPack: its problems and what it covers)"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import report, run
from ..invariants import InvariantBroken
from .spec import ExperimentSpec, SpecError


def _commit() -> str:
    try:
        here = Path(__file__).resolve().parent
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "-C", str(here), "status", "--porcelain", "--", "../.."], capture_output=True,
                               text=True, timeout=10).stdout.strip()
        return (out.stdout.strip() or "unknown") + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m chits.lab", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="pre-register and run a protocol")
    r.add_argument("protocol")
    r.add_argument("--out", required=True)
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--url", action="append", default=[], metavar="BRAIN=URL",
                   help="serve a model brain from this base URL instead of the protocol's (sealed in the manifest)")
    s = sub.add_parser("resume", help="finish the runs a stopped batch didn't")
    s.add_argument("out")
    s.add_argument("--jobs", type=int, default=1)
    a = sub.add_parser("analyze", help="write the comparison pack")
    a.add_argument("out")
    a.add_argument("--unblind", action="store_true")
    t = sub.add_parser("lint", help="check a TreatmentPack and report what it covers")
    t.add_argument("pack")
    args = p.parse_args(argv)
    if args.cmd == "lint":
        from . import treatment as T

        try:
            pack = json.loads(Path(args.pack).read_text())
        except (OSError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        problems = T.lint(pack)
        for x in problems:
            print(f"{x['level']}: {x['where']}: {x['problem']}")
        if isinstance(pack, dict):
            print(json.dumps(T.coverage(pack), indent=2))
        return 2 if any(x["level"] == "error" for x in problems) else 0
    try:
        if args.cmd in ("run", "resume"):
            if args.cmd == "run":
                spec = ExperimentSpec.load(args.protocol)
                for u in args.url:
                    bid, sep, url = u.partition("=")
                    if not sep or not url.strip():
                        raise SpecError(f"--url wants BRAIN=URL, not {u!r}")
                    if bid not in spec.brains:
                        raise SpecError(f"--url: no model brain {bid!r} in the protocol ({', '.join(spec.brains) or 'none'})")
                    spec.brains[bid] = dict(spec.brains[bid], base_url=url.strip())
                spec.validate()
            else:
                spec = ExperimentSpec.from_dict(json.loads((Path(args.out) / "manifest.json").read_text())["protocol"])
            prog = lambda d, n: print(f"  run {d}/{n}", file=sys.stderr, flush=True)
            res = run.run(spec, args.out, jobs=args.jobs, commit=_commit(),
                          started=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), progress=prog)
            print(f"{res['ran']} runs this time; {res['total']} in the experiment. Now: python -m chits.lab analyze {args.out}")
        else:
            path = report.write_pack(args.out, unblind=args.unblind)
            print(path.read_text())
            print(f"\nwritten: {path}")
    except (SpecError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except InvariantBroken as e:
        print(f"stopped: an invariant broke: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
