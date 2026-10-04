# Test harness

Runs instinct worlds without a model and reports what happened in them: the usual per-seed numbers, plus what went
wrong and what never happened at all. It watches from outside. The game gains no code and no cost, and a run with
the harness comes out the same as a run without it.

Run everything from the repo root with the project's Python (`.venv/bin/python`). Nothing outside the standard
library is needed.

## One world: `run.py`

```bash
python tools/harness/run.py 42 --days 60              # one JSON line
python tools/harness/run.py 42 --days 60 --autopsy    # the starved and stuck chits first, then the JSON line
python tools/harness/run.py 42 --server ../other-checkout/server --size 96 --chits 18 --culture direct
```

The JSON line has the per-seed numbers the A/B tables have always shown (`disc`, `era`, `pop`, `low`, `starved`,
`produced`, `food` and the others), plus:

- `preventable`: chits that starved while a store with food stood on their own land within 30 tiles.
- `stuck`, `stuck_episodes`: chits that replanned the same goal with a failing first step more than
  `STUCK_AFTER` (3) times in a row. `fail_streaks` gives how long every such run was, so the threshold can be
  checked against the data.
- `fired`: how often each mechanism fired over the run. `fired_by` breaks crafts down by recipe, builds by design,
  station goods by item and deaths by cause. `never_fired` lists the mechanisms that never fired.

`--autopsy` prints the last 30 moments of every chit that starved, recorded while its hunger was 40 or less. Each
moment shows its hunger, goal, head step (` R` marks a reflex), last result and the food it held. It also shows
the nearest store with food: its distance, whether it is on the chit's land (`land1`), and `UNREACH` if the chit
had marked it unreachable. Examples of stuck chits follow.

The mechanisms are listed in one place: `MECHANISMS` in `probe.py`. Each one is counted from the world's events
(`w.listeners`) or from the chits' own lifetime counters (`Agent.stats`). To count a new mechanism, add a line there.

## Two trees: `ab.py`

```bash
python tools/harness/ab.py BASE NEW --seeds "42 7 99 1 2 3 4 5 6 11 12 13" --days 60 --label my-change --jobs 8
```

`BASE` and `NEW` are checkouts, or their `server` dirs. Both sides are measured with this harness, so the base can
be an older tree. It prints:

- a table per seed and a mean row (`base>new`);
- whether the two sides came out identical;
- the mean count per mechanism, with `*` where they differ;
- the mechanisms that never fired on each side, and the difference between the two sides;
- every starvation, with its autopsy file;
- the stuck chits.

Rows go to `harness-out/LABEL.jsonl`, and each run's autopsy to `harness-out/LABEL/SEED-TAG.txt` (`--out` moves
them). A seed where either side fails is listed under `FAILED` with the reason, and kept out of every table and
mean. The run then exits 1. A base tree run against itself should print `identical: every seed`. If it does not, the run is not
deterministic and no A/B on it means anything.

Judge a change on 12-24 seeds and 60 days. Three seeds over 30 days have flattered changes that later failed.

## Workflow (agreed 2026-10-04)

1. **A behaviour change merges behind a module switch.** The switch is a module-level constant (like
   `projects.MAKE_FIRST`). It is off by default until the change's A/B is settled.
2. **`tests/identity_runner.py` turns each switch off**, so `tests/test_village_identity.py` keeps proving that, with
   the switch off, the world is the same as before the change.
3. **A one-line PR turns the switch on** once its A/B passes. The PR carries the `ab.py` output.
4. **Every starvation in an A/B is explained with `--autopsy`**, on both sides, before the A/B counts as passed. A
   preventable death on the new side is a bug, even when the means look better.
