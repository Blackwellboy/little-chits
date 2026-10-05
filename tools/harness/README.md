# Test harness

Runs instinct worlds without a model and reports what happened in them: the usual per-seed numbers, plus what went
wrong and what never happened at all. With `--mind` it runs the model path too (below). It watches from outside. The game gains no code and no cost, and a run with
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

## The model in the loop: `run.py --mind`

An instinct run never builds a prompt, parses a reply, repairs a plan or escalates a choice, so it can't see what goes
wrong there. The live game can: `/api/why` has shown "gather None" 96 times, experiments with items that don't exist
and failed stores, none of which an instinct run produces. `--mind` runs the same world with every chit on one brain,
driven through the game's own Mind (`brain/mind.py`), and reports the model path's health.

```bash
python tools/harness/run.py 42 --days 20 --mind scripted              # the scripted model: no GPU, deterministic
python tools/harness/run.py 42 --days 20 --mind scripted --autopsy     # plus the model-path autopsy
python tools/harness/run.py 42 --days 2 --mind scripted --style full --bad-rate 0.3 --bad-kinds none_what,prose
python tools/harness/run.py 42 --days 5 --mind http://127.0.0.1:18191/v1   # a real server, only when given one
```

**The scripted model** (`scripted.py`) answers every request the game makes: a letter for a choice (with logprobs,
so the cascade's confidence gate and escalation run), a JSON plan for a full request, lessons for a reflection, a
letter for a vote. It reads only the prompt (full, compact or choice format), as a model does: it eats when hungry with
food in hand, builds a hut when homeless, tries an untried combination the scene lists only when it can gather every
input it lacks (repeats counted) and has room for them, crafts what it can gather for, gathers what is near. So a good
answer's failures are the world's, and only `--bad-rate` adds the model's own. At `--bad-rate` (default 0.15) it
answers in one of the ways live models have gone wrong (`--bad-kinds` picks among them):

| Kind | What it sends |
|---|---|
| `bad_letter` | a choice answer that is no option's letter |
| `none_what` | a step with `"what": null` |
| `unreal_item` | an experiment, gather or craft with an item no world has |
| `cant_run` | a step that can't run here: take or store iron, help site s9999, work at a factory |
| `unknown_verb` | a verb that doesn't exist (dropped by the parser) |
| `truncated` | a plan cut off mid-JSON |
| `prose` | no JSON at all (the mind asks once more) |

It plugs in below the game's model client, as an `httpx.MockTransport` on the brain: the request body, reply parsing,
the priority gate and the brain's counters all run as they do against a server, and nothing goes over a network. A
reply takes `--plan-ticks` (default 8) or `--choice-ticks` (default 1) world ticks, and the world waits each tick for
every request to reach that clock. So a scripted run is the same on every machine: `run.py` pins `PYTHONHASHSEED=0`
for a `--mind` run, because a prompt's text depends on string hashing (`world.village_failed` counts a set, and its
ties come out in hash order).

The game gains no code. Without `--mind` the harness is what it was: instinct only, no brain, no network. `--mind`
takes `scripted` or an `http(s)://` URL and nothing else. A run against a URL is not deterministic: the world moves
on at `--tick-seconds` per tick (0.5, the game at 1x) and replies land when they land.

The JSON line gains a `mind` section:

- `steps_by_source` (and `_pct`): every finished step by who planned it: `model_selected` (a choice),
  `model_generated` (a written plan), `model_repaired`, `routine`, `filler`, `reflex`, `instinct`, `duty`.
- `plans`, `decisions`: plans by source; each model request by style (`choose`, `cascade-full`, `full`, `repair`,
  `vote`...), parse (`ok`, `retried`, `repaired`, `failed`, `choice`, `invalid_choice`) and outcome (`adopted`,
  `stale`, `failed`). `rejected_steps`: steps the parser dropped. `brain`: the brain's own counters (parse failures,
  retries, repairs).
- `escalation`: cascade choices that asked for a full plan, granted or denied (budget, queue). `repairs`: plans asked
  for after a model step failed, and whether the repaired plan's first step worked. `reply_ticks`: ticks from asking
  a chit's mind to its answer.
- `model_steps`: model steps done and failed, and `failed_at_once` (failed within a tick of starting: they could not
  run at all), by verb and by reason. `model_failures`: the most common failed model steps over the run.
- `loops`: the same step (verb and object as written, so a null `what` shows as `None`) failing for the same reason
  more than `--loop-after` (3) times in a row for one chit, by origin, with episodes, the longest run and how many
  chits. `diag_loops` is the game's own loop detector (`diag.LOOP_N`).
- `why`: the `/api/why` sentences for the world. `planted`: what the scripted model got wrong on purpose, to set
  against what was caught.

`--autopsy` adds the model-path failures: for each model loop, and the first 12 model steps that failed at once, the
plan, its source (style, parse, letter chosen), the step, the result and the reply the plan came from.

### The rule

**Any change to prompts (`brain/prompt.py`), the parser (`brain/parse.py`) or plan handling (`brain/mind.py`,
`sim/actions.py` repair and adoption) also runs `--mind scripted` on a few seeds**, at least 42, 7 and 99 for 10-20
days, before and after the change. Compare `decisions`, `model_steps`, `loops` and `why`. A new model loop, a parse
or adoption rate that falls, or a planted kind that stops being caught is a regression even when instinct A/Bs are
even. The scripted model can't say whether a change helps a real model choose better; that is the decision bench's job.

### Model choices: `tools/decbench.py`

The decision bench scores a real model's one-letter choices on the game's own choice scenes (216 of them: real scenes
from instinct worlds on seeds 42, 7 and 24, plus clear-cut ones: starving with food in hand should eat, exhausted at
night should sleep). About 2 minutes per model. Run it from `server/`:

```bash
python ../tools/decbench.py build . items.json                              # the scenes, once per tree
python ../tools/decbench.py ask items.json http://127.0.0.1:18191/v1 jevk5 g 8   # one server, the game's prompt (g)
python ../tools/decbench.py score items.json items.json.ref.g.json items.json.jevk5.g.json
```

`score` prints the valid-letter share, accuracy on the clear-cut scenes, agreement with a reference model, mean
confidence and speed. Use it for prompt and model questions about *choosing*; use `--mind` for whether the model path
*works* (parsing, repair, escalation, adoption, steps that can't run); use versus runs on 3+ seeds for whether a model
builds a better civilisation. Bench agreement has not predicted in-game results.

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
