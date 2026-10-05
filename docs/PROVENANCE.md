# Who decided what: provenance

"Instinct" used to cover several mechanisms, and only some of them are a model deciding anything. Each mechanism is listed below with the category its plans and steps are counted under (`server/chits/provenance.py`):

| Mechanism | Where | Category |
|---|---|---|
| A. Strategic heuristic planner: chooses a plan when no model does | `brain/instinct.py` `Instinct.plan`, adopted in `Mind._instinct_plan` | `instinct_plan` (also a pioneer's duty) |
| B. Menu generator: drafts the options a choose/cascade model picks from | `Instinct.options` | the model's pick is `model_choice`: the model decided, instinct wrote the plan |
| C. Fallback: stands in when the model is unavailable or its queue is full | `Mind._instinct_plan(kind="fallback"/"shed")` | `fallback` |
| D. Body reflexes: eat, sleep, shelter, warm up, make room in hand | `sim/actions.py` reflexes (`_reflex` steps) | `body_reflex` |
| E. Deterministic executor: walking, pathfinding, fetching a craft's inputs, carrying out a chosen step | `sim/actions.py` | not a decision. It runs under its step's category. A step the executor turns into another (a build beside a lit fire that feeds it instead) is recorded as `executed_as` and counted in `redirects` |
| F. Routine upkeep: eat, sleep, rest, shelter, store, drop or refuel, adopted without asking the model | `Mind._routine` | `routine` |
| Filler while the model thinks | `Mind._instinct_plan(filler=True)` | `filler` |
| The model's own plan | full or compact prompt | `model_plan` |
| The model's repaired plan, after the simulator's exact reason | bounded repair | `model_repair` |

**Where it shows.**
- **Diagnostics** (`/api/diagnostics`): each world has `drivers`, which holds plan and step counts and shares by category. Each finished step's record carries `provenance`.
- **Scorecard:**
  - strategic decisions by the model, and the share it wrote itself
  - steps from the model's plans, from body reflexes, from upkeep and from heuristic instinct
  - time spent waiting on the model
- **Lab results:** `model_authored_step_share`, `reflex_step_share`, `routine_step_share`, `instinct_step_share`, `model_strategic_share`, `model_authored_strategic_share` and `redirects`, next to `model_step_share`. The report lists them under thinking opportunities.

**Strategic** plans are those that set what to do next: the model's own, menu choices, instinct's and fallback. Upkeep and filler are not strategic. A world with no plans adopted through a mind (an instinct-only Lab arm) reports no strategic share rather than 0%.

A new origin label must be added to `provenance.py`. `tests/test_provenance.py` scans the code and fails on any label that has no category.
