"""Score any number of models on the same scenes: how well they *play*, not just how fast they are.

    python -m chits.tools.bench [--url U ...] [--scenes N] [--out data/bench.json]
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
from ..brain.instinct import Instinct
from ..brain.llm import BrainConfig, LLMBrain
from ..brain.parse import ParseError, parse_plan
from ..sim.world import World

SOCIAL = {"say", "teach", "give", "help"}


def bench_scenes(n: int = 12, seed: int = 1234, *, style: str = "full") -> List[List[Dict[str, str]]]:
    w = World("A", "Bench", seed, "direct", 96, 12)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    for _ in range(900):
        w.step(hook)
    chits = sorted(w.agents.values(), key=lambda a: a.id)
    return [P.messages(w, chits[i % len(chits)], style=style) for i in range(n)]


async def _bench_one(cfg: BrainConfig, scenes: int, seed: int) -> Dict[str, Any]:
    brain = LLMBrain(cfg)
    msgs = bench_scenes(scenes, seed, style=cfg.prompt_style or "full")
    valid, steps, verbs, exp, soc, errors, lat = 0, 0, set(), 0, 0, 0, []
    try:
        async def ask(m):
            try:
                return await brain.chat(m)
            except Exception:
                return None

        for res in await asyncio.gather(*(ask(m) for m in msgs)):
            if res is None:
                errors += 1
                continue
            lat.append(res["latency_ms"])
            try:
                plan = parse_plan(res["text"])
            except ParseError:
                continue
            valid += 1
            vs = [s["do"] for s in plan["steps"]]
            steps += len(vs)
            verbs |= set(vs)
            exp += "experiment" in vs
            soc += bool(SOCIAL & set(vs))
    finally:
        await brain.close()
    vr = valid / scenes if scenes else 0.0
    mean_steps = steps / valid if valid else 0.0
    er = exp / valid if valid else 0.0
    sr = soc / valid if valid else 0.0
    score = 100 * (0.45 * vr + 0.15 * min(1, mean_steps / 4) + 0.15 * min(1, len(verbs) / 10) + 0.15 * er + 0.10 * sr)
    return {"label": cfg.label or cfg.id, "model": brain.stats.resolved_model or cfg.model, "valid_rate": vr,
            "mean_steps": round(mean_steps, 2), "verb_diversity": len(verbs), "experiment_rate": er, "social_rate": sr,
            "latency_ms": round(sum(lat) / len(lat), 1) if lat else 0.0, "tok_s": round(brain.stats.tok_per_s, 1),
            "score": round(score, 1) if valid else 0.0, "errors": errors}


async def bench(brains: List[BrainConfig], scenes: int = 12, seed: int = 1234) -> Dict[str, Any]:
    results = await asyncio.gather(*(_bench_one(b, scenes, seed) for b in brains))
    return {"seed": seed, "scenes": scenes, "results": {b.id: r for b, r in zip(brains, results)}}


def _configs(urls: List[str]) -> List[BrainConfig]:
    if urls:
        return [BrainConfig(id=f"url{i + 1}", label=u, base_url=u) for i, u in enumerate(urls)]
    path = Path(os.environ.get("CHITS_DATA_DIR", "data")) / "brains.json"
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "data" / "brains.json"
    if not path.exists():
        return []
    out = []
    for b in json.loads(path.read_text()).get("brains", []):
        cfg = BrainConfig(**{k: v for k, v in b.items() if k in BrainConfig.__dataclass_fields__})
        if cfg.enabled:
            out.append(cfg)
    return out


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Rank models on the same chit scenes.")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--scenes", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", default="data/bench.json")
    args = ap.parse_args(argv)
    cfgs = _configs(args.url)
    if not cfgs:
        print("No brains to bench. Use --url http://127.0.0.1:18191/v1 (repeat for more).")
        sys.exit(1)
    r = asyncio.run(bench(cfgs, args.scenes, args.seed))
    rows = sorted(r["results"].items(), key=lambda kv: -kv[1]["score"])
    print(f"{'score':>6}  {'valid':>6}  {'steps':>5}  {'verbs':>5}  {'exp':>5}  {'social':>6}  {'ms':>7}  model")
    for bid, x in rows:
        print(f"{x['score']:>6.1f}  {x['valid_rate']:>6.0%}  {x['mean_steps']:>5.1f}  {x['verb_diversity']:>5}  "
              f"{x['experiment_rate']:>5.0%}  {x['social_rate']:>6.0%}  {x['latency_ms']:>7.0f}  {x['model'] or x['label']}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
