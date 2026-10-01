# T01 · `make doctor`: prove a model works before a long run

**Why:** before pointing a GPU at the chits for a whole night, one command should tell you whether the model
answers, whether its replies parse, how fast it is, and roughly how many chits it can drive.

## Build
Create `server/chits/tools/__init__.py` (empty) and `server/chits/tools/doctor.py` with:

```python
async def check_brain(cfg: BrainConfig, samples: int = 3, seed: int = 1234) -> dict
```
- Builds a fresh `World("A", "Doctor", seed, "direct", 96, 6)`, takes the first `samples` chits,
  builds `prompt.messages(world, chit)` for each and sends them with `LLMBrain(cfg).chat(...)`.
- Parses each reply with `parse_plan`. A reply counts as valid if it parses.
- Always closes the brain (`await brain.close()`), even on errors.
- Returns a dict with exactly these keys:
  - `ok`: bool. True if at least one reply came back and parsed.
  - `model`: str. The resolved model name, or `""`.
  - `samples`: int.
  - `valid`: int. The number of replies that parsed.
  - `valid_rate`: float, `valid / samples`.
  - `latency_ms`: float, the mean over replies received (0 if none).
  - `tok_s`: float, `brain.stats.tok_per_s`.
  - `est_chits_1x`: int, `int(cfg.max_concurrency * 15000 / max(1, latency_ms))` when ok, else 0.
  - `error`: str. `""` when ok; otherwise the first error message (connection failure, etc.).
  - `example`: dict or None. The first parsed plan (`{"thought","goal","steps"}`).

Also provide a CLI, `python -m chits.tools.doctor [--url URL] [--model M] [--samples N]`:
- With no `--url`, check every brain in `data/brains.json`, plus `CHITS_MODEL_URL` if it's set.
- Print one readable line per brain, e.g.
  `RTX 5090 · qwen3-27b — OK · 3/3 valid · 2400 ms · 38 tok/s · ~50 chits at 1×`,
  then the example thought and goal.
- Exit 0 if every brain is ok, otherwise 1.

Add a Makefile target, `doctor:`, that runs `cd server && ../$(BIN)/python -m chits.tools.doctor $(ARGS)`.

## Done when
`python scripts/plan.py verify T01` passes. On the real GPUs, `make doctor ARGS="--url http://127.0.0.1:18090/v1"` prints OK.
