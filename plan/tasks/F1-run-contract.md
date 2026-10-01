# F1 · Play vs Experiment: a run contract

**Why:** "the model is slow, so instinct takes over" is right for *playing*. It's wrong for an *experiment*: if
the 3090 world is 27% instinct and the 5090 world 2%, a scoreboard compares mixtures of policies, not models.
Each game declares which contract it runs under, and the experiment contract is strict.

## Build
1. **Contract.**
   - `Runtime.contract` is `"play"` (default) or `"experiment"`. It is stored in store meta `contract`, set by
     `reset(..., contract=...)` and by `/api/reset {"contract": ...}` (anything else → 400).
   - `Runtime.run_id` is a new `uuid4().hex` on every reset, stored in meta.
2. **Experiment rules.** In experiment runs:
   - `Mind.strict = True`. A model-driven chit never gets an instinct plan: no filler while thinking, no
     fallback when its brain is unhealthy. With no plan it waits: activity `"waiting for its mind"`,
     `plan_source = "waiting"`. Reflexes (body) still run and are counted as reflexes.
   - Pacing is forced on (`pace_to_brain = True`), and `/api/control {"pace_to_brain": false}` → 409.
   - These return 409 with a message containing `experiment`:
     - changing a world's brain (`POST /api/worlds/{wid}/brain`)
     - editing or deleting a brain that a world uses (`POST /api/brains` with its id, `DELETE /api/brains/{id}`)
   - Contact (T30) must be off: `reset(contract="experiment", contact=True)` → `ValueError` (400 via the API).
3. **Sandbox mark.** `Runtime.mark_sandbox(reason)` permanently sets meta `sandbox_modified = true`, adds the
   reason to meta `sandbox_reasons` (a JSON list), and updates the manifest. Later god-mode and restore code
   calls it. In an experiment, anything that would mark the sandbox is refused instead (409).
4. **Run manifest.** On every reset, write `data/runs/<run_id>/manifest.json`:
   `{"run_id", "created", "contract", "mode", "seed", "size", "chits", "worlds": {wid: {"culture", "flags",
   "brain": {"id", "base_url", "model", "temperature", "max_tokens", "max_concurrency", "json_mode",
   "disable_thinking"} | "instinct"}}, "prompt_version", "source_commit", "pacing", "contact", "sandbox_modified"}`.
   - `prompt_version` is `brain.prompt.PROMPT_VERSION`, a new constant string. Bump it whenever the prompt
     text changes.
   - `source_commit` is `git rev-parse --short HEAD`, or `"unknown"`.
   - `GET /api/run` returns the current manifest.
5. **Fail-closed loading.** If a stored snapshot can't be restored:
   - **play:** copy it to a `quarantine(world_id, saved, data, error)` table, emit a `"notice"` event (importance
     4, `An unreadable save of {world} was set aside; a fresh world was started`), then start fresh.
   - **experiment:** raise `RuntimeError` naming the world. Never silently replace the subject of an
     experiment.
6. **Web.**
   - New game has a **🧪 Experiment (strict)** checkbox, explained in one line.
   - The top bar shows a 🧪 badge in experiment runs, and a 🪄 "modified" badge when the sandbox is marked.

## Done when
`python scripts/plan.py verify F1` passes.
