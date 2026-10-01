# Instructions for coding agents

This file is for any coding agent working on this repo: Aider, opencode, OpenHands, Cline, Continue, ZCode,
Claude Code and so on.

## The build plan is the source of truth

All planned work lives in `plan/`. Each task has three parts:
- a **spec**: `plan/tasks/Txx-*.md`, which says what to build and why
- **acceptance tests**: `plan/acceptance/`, written *before* the code. They define the exact interface.
- a **gate**: `python scripts/plan.py verify Txx`

## Protocol, one task at a time

1. `python scripts/plan.py next` prints the next task whose dependencies are done, with its spec and rules.
2. Read the spec **and** its acceptance tests. The tests are the contract.
3. Implement it. Change only what the task needs.
4. Run `python scripts/plan.py verify Txx`. It checks:
   - the acceptance files are unmodified (sha256)
   - the task's acceptance tests pass
   - `tests/` passes and didn't shrink
   - every earlier task's acceptance tests still pass
   - for web tasks, the web app builds and its vitest tests pass
5. Fix whatever FAILs and repeat until every gate says PASS.
6. `python scripts/plan.py done Txx --commit` ticks it off in `plan/tasks.json` and `plan/PROGRESS.md`, and
   commits.
7. Go back to step 1.

## Hard rules
- **Never edit `plan/`.** That covers specs, acceptance tests and `tasks.json`; `plan.py done` updates the
  status itself. If a test looks wrong, stop and report it. Don't change it.
- **Never delete, skip or weaken tests** in `tests/`. Adding tests is welcome.
- **Never fake a pass.** No hard-coding test values, no special-casing test inputs, no mocking the thing
  under test.
- Keep the architecture:
  - the simulator (`server/chits/sim`) is authoritative, and brains only propose plans
  - World A and World B differ only in `CULTURE_FLAGS`
  - every story claim cites real events
- Python ≥3.10, standard library plus the existing deps. Put new optional deps behind a friendly error.
- Match the surrounding style: small functions, and comments only where the code isn't obvious.

## Handy commands
```bash
make install                       # venv + web deps
make test                          # regular suite
python scripts/plan.py status      # checklist
python scripts/plan.py verify T05  # all gates for one task
cd web && npm run build            # web typecheck + build
make fake-model                    # an OpenAI-compatible stand-in model on :18999
```

## Layout
- `server/chits/sim/`: the world (terrain, items and laws, agents, actions, world tick)
- `server/chits/brain/`: mind (scheduling), llm (OpenAI-compatible client), prompt, parse, instinct
- `server/chits/runtime.py`, `app.py`: the persistent runner, REST and WebSocket
- `web/src/render/`: PixiJS renderer and procedural art
- `web/src/ui/`: React panels
- `tests/`: regular tests
- `plan/`: the build plan (read-only for agents)

## Never
- Never run `plan.py lock` or `plan.py freeze` (they need `PLAN_AUTHOR=1`, which is for the plan author only).
- Never edit anything in `plan/acceptance/`. The gates compare it against the frozen `plan-lock` tag.
- Never let story code (`server/chits/story/`: moments, chronicle, narration) feed back into what chits see. The data path is one-way: simulation → events → moments → stories.
- In an `experiment` run (F1) nothing may silently replace a model's decision, rewind time or touch the world from outside.
