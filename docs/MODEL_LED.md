# Model-led play

**Model-led** is a way to play: the model supplies the intelligence, and the chit keeps its body. Switch it on with:
- 🧠 **Model-led** in the Brains panel
- `POST /api/model-led {"on": true}`
- `"model_led": true` in `POST /api/reset` for a new game

The game keeps the choice across restarts, and it is recorded in the run manifest and in diagnostics.

| | Standard play | Model-led | Model-only (diagnostic) | Experiment (Lab) |
|---|---|---|---|---|
| Heuristic strategic plans for a model's chits | yes | **no** | no | no |
| Filler while the model thinks | yes | **no**: the chit waits, shown as "waiting for its mind" | no | no |
| Instinct standing in when the model is slow or down | yes | **no**: the chit finishes its own plan, then waits ("its mind is unavailable") | no | no |
| Routine upkeep without asking (a `focus` brain) | yes | **no** | no | no |
| A pioneer's duty | yes | **no** | no | no |
| The brain's own prompt style (a cascade's menu is its architecture) | yes | yes | no: full prompt only | yes |
| Body reflexes: eat, sleep, shelter, warm up, make room | yes | **yes** | no | yes |
| The deterministic executor (walking, fetching inputs, carrying out a step) | yes | yes | yes | yes |
| Bounded repair (the simulator's exact reason, once) | yes | yes | yes | only when the protocol declares it |

**What changes when you switch it on.**
- Every model-driven chit drops the plans instinct made for it. Its reflex steps, and its model's own plans and menu choices, stay.
- A chit that comes under a model later is cleaned the same way, whether through a new assignment or by arriving where a model drives.
- Diagnostics show when the mode began and how many instinct steps were dropped (`model_led`). They also show `mind_unavailable_pct`, the share of a model's chit-time spent with its mind down.

**What it is not.**
- It is not a controlled experiment. Play is play. Model comparisons go through the Lab, whose strict contract already gives a model's chits no instinct stand-in.
- It is not model-only. Model-only also takes away the body's reflexes, to show what a model does entirely on its own. Model-led keeps the body.

**Who drove the world.** docs/PROVENANCE.md explains how plans and steps are counted by origin: the model's own plans, its menu choices, its repairs, body reflexes, upkeep and heuristic instinct. Under model-led, instinct's share should be zero. The harness checks this: `tools/harness/run.py SEED --mind scripted --model-led`.
