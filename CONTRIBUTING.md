# Contributing to Little Chits

Thanks for wanting to help. Little Chits is a simulator first: the world decides what happens, and a mind (instinct
or any LLM) only proposes plans. Most contributions are one of: a bug fix, a new building or item with the rules to
use it, a better instinct plan, a model-serving improvement, or a research tool.

## Getting set up

```bash
git clone https://github.com/<you>/little-chits && cd little-chits   # your fork
make install          # Python venv + web dependencies
make play             # start the game and open the browser
```

No GPU is needed to work on the simulator: the chits run on instinct, and `make fake-model` starts a stand-in
OpenAI-compatible model on port 18999 for trying the model paths. `docs/GPU_SETUP.md` covers real model servers.

## How changes get in

1. **Fork** the repository and work on a branch in your fork. (The main repository only accepts branches through
   pull requests from forks; maintainers use `dev/...` branches.)
2. Open a **pull request** against `main`. CI must be green: the Python tests, the web build, and the frozen plan's
   acceptance tests.
3. Keep a pull request to one change, with a short description of what changed and why.

## The rules the project keeps

- **Tests for every change, and a test that fails without it.** For a fix, the test reproduces the bug. Breaking
  your fix on purpose and watching the test fail is the quickest way to know the test is real.
- **Behaviour changes need an A/B, not one seed.** The simulation is chaotic per seed. A change to what chits do is
  judged over many seeds (we use 12 seeds × 30 and 60 days, instinct only), comparing discoveries, era, population,
  starvation and goods made. Say what you measured in the pull request.
- **`plan/` is frozen.** It is the original build plan and its acceptance tests are hash-locked; CI checks them.
  New work goes elsewhere.
- **The simulator is the authority.** A model never changes the world directly, and a model's chits never get
  knowledge the world didn't give them (no real item names for things nobody has discovered).
- **Experiments stay fair.** Anything under `make experiment` or the Lab runs in lockstep, with the same settings for
  every arm; see `docs/RESEARCH_PLAN_2026-09-30.md`.
- **No secrets, personal paths or machine names** in commits, logs or screenshots.

## Running the checks

```bash
.venv/bin/python -m pytest -q tests plan/acceptance   # the whole suite
cd web && npm run build                                # the observer
```

## Where to start

Issues labelled **good first issue** are small and self-contained. `docs/FIXES_2026-09-30.md` is the fix tracker
and `docs/RESEARCH_PLAN_2026-09-30.md` the research roadmap. Ideas and questions are welcome in Discussions.

By contributing you agree that your contributions are licensed under the MIT licence of this project.
