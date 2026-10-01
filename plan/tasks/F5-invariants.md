# F5 · Invariants: nothing duplicated, nothing lost, nothing negative

**Why:** a simpler simulation is easier to trust, but only if cheap, permanent checks back it. These tests
catch duplicated items, double deliveries, negative stock, a parser that lets garbage reach the world, runaway
long runs, and story code leaking back into what chits see.

## Build
Make every test in `plan/acceptance/test_f5_invariants.py` pass by fixing the simulation, not by weakening
behaviour. In particular:
- **Conservation:** `store`, `take`, `craft`, delivering to sites and save/restore conserve every countable
  item (inventories + storage + ground).
- **Failures:** failed actions consume nothing, unless a spec says they do.
- **Idempotency:** two chits delivering the last material to a site can't both be debited for it.
  `complete_structure` on an already-complete structure does nothing (no second "built" event, no second
  home assignment).
- **Parser:** output only contains known verbs, `qty` is an int in 1..99 (clamp it), there are at most 6
  steps, and no nested dicts in step values (drop them, or turn them into strings).
- **Long run:** the population stays within 8..60 over 40 days, structures don't explode, ruins don't pile up,
  no value is negative, and few adults sit idle with no plan.
- **One-way data path:** nothing under `server/chits/brain/` imports `chits.story`. Add that rule to `AGENTS.md`.

## Done when
`python scripts/plan.py verify F5` passes.
