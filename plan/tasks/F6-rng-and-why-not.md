# F6 · Independent random streams, and "why didn't this happen?"

**Why:** twin worlds share a seed, but one extra dice roll in World A (a fight, an experiment) shifts every
later roll: the weather, births, regrowth. Then environmental luck snowballs from call order rather than from
policy. Separate streams keep the environment identical until the chits themselves change it. And when
nobody builds a kiln, we need to know why: nobody knew it, it was unaffordable, nobody chose it, or the model
was down.

## Build
1. **Streams.**
   - `World.rng_for(name) -> random.Random` returns a per-world stream seeded from
     `zlib.crc32(f"{seed}:{name}".encode())`, created lazily and cached.
   - Named streams: `regrow`, `births`, `weather`, `sites`, `agents`, `combat`, `animals`, `misc`.
   - Replace every `self.rng` use in `world.py`, and every `world.rng` use in `actions.py` and later tasks,
     with the right stream. `World.rng` stays as an alias of `rng_for("misc")` for old code.
   - Persist each stream's state in `to_dict` as `"rng_state": {name: list(state)}`, and restore it in
     `from_dict`, so a restored world continues the same sequences.
2. **Opportunities** (`diag.opportunities(world) -> dict`, included in `/api/diagnostics` as
   `worlds[id].opportunities`):
   - For each design not yet built in the world: `known_by` (chits that know it), `affordable_by` (knowers
     carrying, or with a stockpile within 20 tiles holding, all its materials), `sites_started`,
     `sites_abandoned`.
   - For each recipe not yet discovered: `inputs_handled_by` (chits familiar with every input), `tried_by`
     (chits whose `failed_experiments` include a combination of exactly those inputs).
   - The text report lists the 5 most "ready but not done" gaps, e.g.
     `kiln: known by 6, affordable by 2, never started`.

## Done when
`python scripts/plan.py verify F6` passes.
