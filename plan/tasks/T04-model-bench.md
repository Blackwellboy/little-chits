# T04 · Model bench: score any number of models on the same scenes

**Why:** you have a folder of GGUFs. Before a long run, rank them on how well they *play*, not just on speed.

## Build
Create `server/chits/tools/bench.py`:

```python
def bench_scenes(n: int = 12, seed: int = 1234) -> list[list[dict]]
async def bench(brains: list[BrainConfig], scenes: int = 12, seed: int = 1234) -> dict
```
- `bench_scenes`: make one world, `World("A", "Bench", seed, "direct", 96, 12)`. Run it under `Instinct`
  for 900 ticks so chits have memories and knowledge. Then return `n` message lists
  (`prompt.messages(world, chit, style)`), one per chit, cycling through chits.
  - It's deterministic: the same seed gives identical output.
  - Use each brain's own `prompt_style` when benching it. That means `bench_scenes` takes
    `style: str = "full"` as a keyword argument.
- `bench`: send every scene to every brain, all brains concurrently. Parse each reply with `parse_plan`.
  Return:
  ```json
  {"seed": 1234, "scenes": 12, "results": {"<brain id>": {
      "label": "...", "model": "...", "valid_rate": 0.0-1.0, "mean_steps": float,
      "verb_diversity": int,        // distinct verbs across all valid plans
      "experiment_rate": 0.0-1.0,   // share of valid plans that contain an experiment step
      "social_rate": 0.0-1.0,       // share of valid plans with say/teach/give/help
      "latency_ms": float, "tok_s": float, "score": 0-100 float, "errors": int}}}
  ```
  - `score = 100 * (0.45*valid_rate + 0.15*min(1, mean_steps/4) + 0.15*min(1, verb_diversity/10)
    + 0.15*experiment_rate + 0.10*social_rate)`, rounded to 1 decimal.
  - A brain that fails every request gets `valid_rate` 0, `score` 0, and `errors` = scenes.
- CLI: `python -m chits.tools.bench [--url U ...] [--scenes N] [--out data/bench.json]`
  - With no `--url`, bench every enabled brain in `data/brains.json`.
  - Print a ranked table (best score first), and write the JSON to `--out`.
- Makefile: `bench:` target.

## Done when
`python scripts/plan.py verify T04` passes. 🖐 Then bench your GGUFs, e.g. start two `llama-server` processes and run `make bench ARGS="--url http://127.0.0.1:8080/v1 --url http://127.0.0.1:8081/v1"`.
