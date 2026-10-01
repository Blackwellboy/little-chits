"""`make doctor`: prove a model works before a long run.

    python -m chits.tools.doctor [--url URL] [--model M] [--samples N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..brain import prompt as P
from ..brain.llm import BrainConfig, LLMBrain
from ..brain.parse import ParseError, parse_plan
from ..sim.world import World


async def check_brain(cfg: BrainConfig, samples: int = 3, seed: int = 1234) -> Dict[str, Any]:
    world = World("A", "Doctor", seed, "direct", 96, 6)
    chits = list(world.agents.values())[:samples]
    brain = LLMBrain(cfg)
    valid, got, lat, err = 0, 0, [], ""
    example: Optional[Dict[str, Any]] = None
    try:
        for a in chits:
            try:
                res = await brain.chat(P.messages(world, a))
            except Exception as e:
                err = err or f"{type(e).__name__}: {e}"[:300]
                continue
            got += 1
            lat.append(res["latency_ms"])
            try:
                plan = parse_plan(res["text"])
                valid += 1
                if example is None:
                    example = {"thought": plan["thought"], "goal": plan["goal"], "steps": plan["steps"]}
            except ParseError as e:
                err = err or f"unreadable reply: {e}"
    finally:
        await brain.close()
    ok = got > 0 and valid > 0
    latency = sum(lat) / len(lat) if lat else 0.0
    return {
        "ok": ok, "model": brain.stats.resolved_model or cfg.model or "", "samples": len(chits), "valid": valid,
        "valid_rate": valid / len(chits) if chits else 0.0, "latency_ms": latency, "tok_s": brain.stats.tok_per_s,
        "est_chits_1x": int(cfg.max_concurrency * 15000 / max(1, latency)) if ok else 0,
        "error": "" if ok else (err or "no replies"), "example": example,
    }


def _configs(args) -> List[BrainConfig]:
    if args.url:
        return [BrainConfig(id="cli", label=args.url, base_url=args.url, model=args.model or "")]
    out = []
    path = Path(os.environ.get("CHITS_DATA_DIR", "data")) / "brains.json"
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "data" / "brains.json"
    if path.exists():
        for b in json.loads(path.read_text()).get("brains", []):
            out.append(BrainConfig(**{k: v for k, v in b.items() if k in BrainConfig.__dataclass_fields__}))
    if os.environ.get("CHITS_MODEL_URL"):
        out.append(BrainConfig(id="env", label="CHITS_MODEL_URL", base_url=os.environ["CHITS_MODEL_URL"],
                               model=os.environ.get("CHITS_MODEL_NAME", "")))
    return out


async def _main(args) -> int:
    cfgs = _configs(args)
    if not cfgs:
        print("No brains configured. Use --url http://127.0.0.1:18191/v1 or add one in ⚙ Brains.")
        return 1
    all_ok = True
    for cfg in cfgs:
        r = await check_brain(cfg, samples=args.samples)
        name = cfg.label or cfg.id
        if r["ok"]:
            print(f"{name} · {r['model']} — OK · {r['valid']}/{r['samples']} valid · {r['latency_ms']:.0f} ms · "
                  f"{r['tok_s']:.0f} tok/s · ~{r['est_chits_1x']} chits at 1×")
            if r["example"]:
                print(f"   thought: {r['example']['thought'][:140]}")
                print(f"   goal: {r['example']['goal'][:100]}")
        else:
            all_ok = False
            print(f"{name} — FAILED · {r['error']}")
    return 0 if all_ok else 1


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Check a model can drive chits before a long run.")
    ap.add_argument("--url")
    ap.add_argument("--model")
    ap.add_argument("--samples", type=int, default=3)
    sys.exit(asyncio.run(_main(ap.parse_args(argv))))


if __name__ == "__main__":
    main()
