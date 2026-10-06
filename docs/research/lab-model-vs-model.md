# Model vs model in the Lab

How to run a model-vs-model study with `chits.lab`, and what each run records. The first study is
`docs/protocols/jevk5-vs-gemma.json`: JevK5 9B against Gemma 4 12B, on the same island and culture.
Its results: [jevk5-vs-gemma-2026-10.md](jevk5-vs-gemma-2026-10.md).

## What a model arm does

- **Strict:** the model decides every plan. A chit waits for its own model and is never given an instinct plan.
  There is no focus routing, and no repair unless one is declared.
- **Lockstep:** every call made on a tick is answered before the next tick, so a faster card changes the wall time,
  not the world.
- **Seeded:** each request carries a seed made from the run's seed and the exact prompt.
- **The same sampling as `make experiment`:** `top_p 0.95`, `top_k 40`, `min_p 0.05`, unless a brain's `extra_body`
  sets its own. The two brains must then match, because the protocol refuses arms whose comparison settings differ.
- **A BrainTape per run** in `runs/<seed>_<label>/tape.jsonl`, holding every call and its answer or error.
- **Its server on record** in `runs/<seed>_<label>/server.json`: URL, model, sampling, and whether the seed was
  card-swapped. Like `treatment.json`, this is kept apart from `result.json`, which is what the blind report reads.
- **Thinking opportunities:** every run's final row carries three figures, and the report has a "Thinking
  opportunities" table of them. They are reported, not equalised.
  - `requests_per_chit_day`: requests to its model per chit-day.
  - `waiting_share`: the share of a model-minded chit's time spent waiting for its answer. Under lockstep this is
    0, because the world waits instead of the chit.
  - `wait_seconds_per_chit_day`: the wall seconds the world stood waiting for its model's answers, per chit-day.
    This is the lockstep wait. It is a cost of the card and the model, not a fact about the world.
  - `model_step_share`: the share of finished steps that came from the model's plans. The rest are reflexes.
- **Checked servers:** before anything is written, and again on resume, every server the protocol uses is asked what
  it serves, including card-swap servers. A server that doesn't answer, or doesn't list the brain's `model`, stops
  the run. A served id matches if it equals `model` or ends in `/model`, because llama.cpp may list the file's whole
  path. The manifest keeps what each server listed.

## Running it

```sh
# instinct only, no GPU
make lab ARGS="run docs/protocols/speech-vs-silence.json --out runs/speech --jobs 4"
make lab ARGS="analyze runs/speech"            # report-blind.md + CSVs; --unblind after the report is frozen

# model arms (owner's go-ahead for the cards)
CHITS_LAB_ALLOW_MODELS=1 make lab ARGS="run docs/protocols/jevk5-vs-gemma.json --out runs/jevk5-vs-gemma --jobs 2"
```

`--url BRAIN=URL` (repeatable) serves a brain from another base URL than the protocol's. The URL used is sealed in
the manifest and the fingerprint, so a run can't be resumed against a different server by mistake. `make lab` runs
from the repository root, so paths are relative to it. Keep `--jobs` low for model arms: parallel runs share each
server, and 12 failed calls in a row end a run.

## One card, two models (the RTX 5090 setup)

Serve each model from its own llama.cpp server on its own port of the same card, beside the live game:

```sh
CUDA_VISIBLE_DEVICES=<5090> llama-server -m /models/jevk5-9b-v0.3.3-Q8_0.gguf --alias jevk5-9b-v0.3.3-Q8_0.gguf \
    --host 127.0.0.1 --port 18195 -ngl 99 -np 4 -c 32768 --jinja
CUDA_VISIBLE_DEVICES=<5090> llama-server -m /models/gemma-4-12b-it-Q4_K_M.gguf --alias gemma-4-12b-it-Q4_K_M.gguf \
    --host 127.0.0.1 --port 18196 -ngl 99 -np 4 -c 32768 --jinja
```

- `--alias` set to the file name makes `/v1/models` list exactly the protocol's `model`, so the server check
  recognises it.
- `-np` must equal the protocol's `max_concurrency` (4), so neither model gets more parallel slots.
- `-c` is shared out between the slots (32768 / 4 = 8k tokens each). Check the prompt fits with
  `make doctor ARGS="--url http://127.0.0.1:18195/v1"`, and the same for 18196.
- Check free VRAM with `nvidia-smi` before starting the second server. Q8_0 9B and Q4_K_M 12B weights are roughly
  9-10 GB and 7-8 GB, plus their KV caches, and the live game on 18191 already holds its share.
- Both models share one card's compute, and the live game's. Lockstep makes that cost wall time only. If replies get
  slow, raise `timeout` (180 s in the protocol) rather than `-np`.
- Run `make lab ... --jobs 2` at most: each job is one world of 12 chits asking one server.

With one card, `card_swap` stays off: there is no other card to swap to.

## Two cards: paired card swaps

When each model can be served on both cards, give every model brain its server on the other card:

```json
"card_swap": {"jevk5": "http://127.0.0.1:<jevk5-on-card-2>/v1", "gemma": "http://127.0.0.1:<gemma-on-card-1>/v1"}
```

On the 2nd, 4th, 6th... seed, each model runs on its other server, so over each pair of seeds both models have used
both cards. The manifest's `runs[*].card_swapped` and each run's `server.json` say which seeds were swapped. All four
servers are checked before the run. Use an even number of seeds.

## Dry run

Before the cards, run the exact protocol against two fake servers that list the protocol's model names:

```sh
.venv/bin/python tests/fake_llm.py --port 18997 --latency 0.02 --model jevk5-9b-v0.3.3-Q8_0.gguf &
.venv/bin/python tests/fake_llm.py --port 18998 --latency 0.02 --model gemma-4-12b-it-Q4_K_M.gguf &
CHITS_LAB_ALLOW_MODELS=1 make lab ARGS="run docs/protocols/jevk5-vs-gemma.json --out /tmp/dry --jobs 4 \
    --url jevk5=http://127.0.0.1:18997/v1 --url gemma=http://127.0.0.1:18998/v1"
make lab ARGS="analyze /tmp/dry"
```

The fake's plans are random, so the numbers mean nothing. What a dry run checks is the config, the seals, the server
check, the tapes and the report.

**Dry run, 2026-10-05:** I ran the exact protocol (6 seeds × 2 arms × 25 days × 12 chits) against two fakes, with
`--jobs 4`. It finished 12 of 12 runs in 216 s, with 26,332 requests and none failed. Every tape held exactly as many
calls as its run made requests. The server check, `server.json`, the manifest's `sampling`, `lockstep`,
`request_seeds` and `servers`, and the blind report with its "Thinking opportunities" table were all as expected.

Two things to expect on the real cards:
- `model_step_share` was about 0.44. More than half of all finished steps are reflexes (the simulator's own
  automatic steps), even in strict mode.
- `waiting_share` is 0 in lockstep. The cost of thinking shows up in `wait_seconds_per_chit_day` and the wall time
  instead.

## Invalid runs

A run that breaks a hard invariant (`invariants.py`) isn't a result. This includes a model server that fails 12
requests in a row (`brain_unavailable`). That run alone stops, and the rest of the batch carries on.

- **The record.** The run gets two files instead of `result.json`.
  - `runs/<seed>_<label>/invalid-sealed.json` is the raw record: the invariant's kind and what broke, the tick and
    day, the seed, the arm and its brain, every break found at that tick (all of them, with their count and a count
    by kind), and its last 5 model calls from the tape. Like `server.json`, only an unblinded report reads it.
  - `runs/<seed>_<label>/invalid.json` is the blind copy, which the report and the command line read. It has no arm
    or brain field. Every arm's identities in its text are replaced by `arm <that arm's label>`, not only its own
    arm's. The identities are each arm's name; its brain's id; its label and each word of it; its model file, also
    without the extension and as the name before the first dash; and its servers (card swap included), with or
    without the scheme and trailing slash, and as host:port. They are matched as whole words, in any case. A string
    two arms share becomes `an arm`. This matters because a `brain_unavailable` break names the model that stopped
    answering, and a server or client may change the case of a model or host name.
  - Only the free text is redacted: what broke, each break's text, and each last call's error and reply. The
    structure (seed, label, kind, tick, counts) is never touched, so an arm or brain called `A` or `B` can't rewrite
    a record's label.
  - A brain with no `model` runs the first model its server lists, and its label falls back to that name. The run
    records it as `resolved_model` in `server.json`, and the redaction covers it too, along with everything that
    brain's servers listed in the manifest.
  - Records written before this (a single raw `invalid.json`, or `invalid-attempt-N.json`) are migrated on the first
    resume, analyze or CLI listing. The raw record moves to its sealed name, and a redacted copy takes its place.
    Both are marked `migrated`, with the time, and say that such records kept at most 20 breaks.
- **Exit code.** `make lab` finishes the batch, lists the invalid runs by label from their blind records, and exits 3.
- **The report.** An "Invalid runs" table lists them by label, blind. They are left out of the final values, and
  every paired difference involving that arm leaves the seed out. `analyze --unblind` shows the raw records.
- **Resuming.** A resume **keeps** an invalid run; it does not rerun it. Rerunning only the runs that broke, until
  they don't, would keep the lucky draws: a model whose server falls over on hard seeds would end up measured on the
  easy ones. When the cause was outside the experiment, such as a server that went down, use
  `CHITS_LAB_ALLOW_MODELS=1 make lab ARGS="resume DIR --retry-invalid"` (a model study refuses to resume without the variable). That declares the retry. Each earlier attempt is kept as
  `invalid-attempt-N.json`, `invalid-sealed-attempt-N.json` and `tape-attempt-N.jsonl`, the new `result.json` carries `invalid_attempts`, and the
  report says how many runs were retried.

**The first real study (2026-10-05)** lost its whole batch this way, after about 2 hours. Run `42_B` (JevK5 on
:18195) got 12 `ReadTimeout`s in a row after 653 good replies. The last good replies took 3-4 s against a 180 s
timeout, so the server stopped answering; nothing broke in the world. The `brain_unavailable` break was raised in
the worker, but `InvariantBroken` couldn't be unpickled in the parent process. That broke the process pool, and the
Gemma run beside it died too. Both causes are fixed: the exception now pickles, and a break ends only its own run.

## Not done yet

- Replaying a Lab run from its tape. The tape is recorded; `make experiment --replay` is still the only replay.
- An equal strategic-call budget (research item 43). Opportunities are reported, not capped.
