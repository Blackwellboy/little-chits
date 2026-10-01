# T15 · Experiment runner: model vs model, headless, packaged for posting

**Why:** "I gave two AIs the same island for 5 days" is the post. One command should run it without the
browser, as fast as the GPUs allow, and drop a folder with everything needed to post.

## Build
Create `server/chits/tools/experiment.py`:

```python
async def run_experiment(brains: dict[str, BrainConfig | None], days: float, out_dir: Path, *, seed: int = 1234,
                         chits: int = 12, max_wall_s: float | None = None) -> dict
```
- **Worlds.** Twin worlds from the same seed: `"A"` direct and `"B"` stigmergy. Each has `chits` chits.
- **Brains.** `brains` maps world id to a config, or None for instinct. Create a `Mind` (config path
  `out_dir/brains.json`), upsert each config and `assign` it.
- **Stepping.** Step both worlds tick by tick with `mind.hook`, until `days*240` ticks or `max_wall_s`.
  - Call `await asyncio.sleep(0)` at least every 5 ticks.
  - While more than half of the model-driven chits are idle-waiting on a reply (`thinking` and no plan, or
    only filler), `await asyncio.sleep(0.02)` instead of stepping. The world waits for the models, so the
    result reflects the model, not instinct.
- **Writes into `out_dir`:**
  - `summary.json`:
    `{"seed", "days", "ticks", "wall_s", "worlds": {id: {"brain", "label", "culture", "stats", "decisions", "model_plans", "brain_stats"}}}`
    - `decisions` is the sum of `agent.decisions`.
    - `model_plans` is the number of plans adopted from a model.
    - `brain_stats` is `LLMBrain.stats.__dict__`, or `{}` for instinct.
  - `events_A.jsonl`, `events_B.jsonl`: one `Event.to_dict()` per line.
  - `summary.md`: a title with both labels, a numbers table, the top 5 moments per world (T11), and the X
    thread (T13).
  - `card.svg`: the T14 scoreboard.
- **Cleanup.** Close the Mind at the end (`await mind.close()`). Return the summary dict.

**CLI** `python -m chits.tools.experiment --a <url|instinct> --b <url|instinct> [--days 3] [--chits 12] [--seed 1234] [--out DIR] [--model-a NAME] [--model-b NAME]`
- The default out is `data/experiments/<YYYYmmdd-HHMMSS>`.
- Print progress once per in-game day, then the path.

**Makefile:** `experiment:`. Example:
`make experiment ARGS="--a http://127.0.0.1:18090/v1 --b http://127.0.0.1:18080/v1 --days 3"`.

**Scoreboard, not a verdict (added after review):** `summary.md` and the card never name an overall "best
model".
- They show separate axes: survival (population, deaths by cause), discovery (count and pace), inventions
  (T20), knowledge spread, construction diversity, social activity, model latency, unreadable-reply rate and
  fallback rate (F2).
- A civilisation experiment is not a model benchmark (T04). Keep the two in separate outputs.
- When F1 is done, `run_experiment` uses the `experiment` contract and copies the run manifest into
  `out_dir`.

## Done when
`python scripts/plan.py verify T15` passes. 🖐 Then run a real 1-day 5090-vs-3090 experiment and read `summary.md`.
