# T24 · Jobs: a division of labour

**Why:** on instinct, everyone does a bit of everything, so the island fills with half-used buildings. Real
towns specialise. With jobs, you get farmers who keep the fields, builders who keep the roofs on, and a scholar
who spends her life at the library. They're also great story material: "the island's first fisher".

## Build
1. `JOBS = ("farmer", "builder", "crafter", "gatherer", "fisher", "scholar", "explorer")` in
   `server/chits/sim/agent.py`.
   - Add `Agent.job: str = ""` and `Agent.job_source: str = ""` (`"auto"` or `"chosen"`). Persist both;
     missing fields load as `""`.
2. **Automatic jobs.** `World.assign_jobs()` runs in `_new_day`. For each adult (not `is_child`) whose
   `job_source != "chosen"`:
   - Map skills to jobs: `farming`→farmer, `building`→builder, `crafting`→crafter, `gathering`→gatherer.
   - If the top skill is ≥ 1.0 **and** at least 1.3× the second-highest, the job is its mapping. Otherwise
     the job is `""`.
   - `fisher` overrides `gatherer` when `a.stats.get("fish", 0) >= 10`.
   - `scholar` overrides everything when `a.stats.get("read", 0) + a.stats.get("wrote", 0) >= 3`.
   - Set `job_source = "auto"`.
3. **Chosen jobs.** `parse_plan` returns `"job"` when the reply has `"job"` (or `"role"`, `"profession"`)
   matching a JOBS entry, case-insensitive; otherwise `""`. When a model plan carries a job, the mind sets
   `a.job`, `a.job_source = "chosen"`.
4. **Event.** When a chit's job changes to a non-empty job, emit `"job"`, importance 2:
   `{name} is now a {job}`. If it's the first chit in the world with that job, use importance 3:
   `{name} became the island's first {job}`.
5. **Instinct.** In `_progress`, multiply an option's weight by 2.5 when it matches the job:
   - **farmer:** goals containing `farm`, `harvest`, `plant` or `bread`
   - **builder:** `build`, `help with`, `mend`, `restore`, `road`
   - **crafter:** `make`, `craft`, `bake`
   - **gatherer:** `collect`, `store food`
   - **fisher:** `fish`
   - **scholar:** `experiment`, `read`, `record`, `study`, `figure out`
   - **explorer:** `explore`

   Also, in `_maintain`, builders skip the random gate (they always maintain when something is worn).
6. **Prompt, views and web.**
   - `scene()`: `You work as a {job}.` on the YOU line when set. `verb_guide` says a plan may include
     `"job":"<one of …>"`.
   - `views.agent_detail` includes `job`, and `stats()` includes `"jobs": {job: count}`.
   - The People tab shows the job instead of the inferred role when set. The Stats tab lists job counts.

**Honesty (added after review):** jobs are a specialisation *mechanic*. They're inferred from practice or
declared by a model, then they bias instinct. Don't describe them as "the civilisation invented division of
labour".
- The UI keeps them distinct: **Role** (inferred from behaviour, an analytics label) and **Job** (the
  mechanic, marked `auto` or `chosen`).

## Done when
`python scripts/plan.py verify T24` passes.
