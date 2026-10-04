# LITTLE CHITS — Claude continuation handoff

Read in order:

1. `CLAUDE.md`
2. `CURRENT.md`
3. `AGENTS.md`
4. `README.md`
5. `docs/FIXES_2026-09-30.md` (the open fixes, in order) and `docs/RESEARCH_PLAN_2026-09-30.md` (the roadmap)
6. `plan/PROGRESS.md` (status only; **41/41 are done**)
7. `docs/UPGRADE_PLAN.md`, then `docs/UPGRADE_STATUS_2026-09-29.md` (what of it is really done)
8. recent commits on `main`
9. the tests covering any subsystem you intend to change

## First action on any machine that may hold local work

Before any checkout, pull, rebase, reset or clean, in every worktree (`git worktree list`):

```bash
git status --short --branch
git diff
git diff --cached
git log --oneline --decorate -20
git stash list
```

If there are local edits that aren't on GitHub:

1. Don't discard them.
2. Create a WIP branch from the current local HEAD.
3. Commit the recoverable work, or save a binary-safe patch plus an inventory of untracked files.
4. Compare it against `origin/main`.
5. Only then decide what to carry forward.

This was done on the main PC on 2026-09-29 (see CURRENT, "Codex recovery"). All of the preserved work has since
been merged. The `wip/*` branches on the remote stay as history; nothing on them is waiting.

## Remote continuation point

Continue from `origin/main`. (Until 2026-09-30 this said `claude/dazzling-dijkstra-5nv6xh` at `d386a1d` and "never
`main`": that was before v2 merged. It no longer applies.)

## Work in flight (updated 2026-10-04)

This section lets anyone, person or agent, pick up the current queue from GitHub alone. Update it in the same PR as any change that moves the queue.

**Merged on 2026-10-04:**

| PR | What |
|---|---|
| #82 | Wanderer floor for held worlds |
| #83 | Loop guard: a thing a world cannot name no longer stops it |
| #84 | Fast settlement detection |
| #85 | Invention engine, F34 |

#86 was closed because it made a test opt-in, which AGENTS.md forbids.

**Open, in merge order:**

| Item | What | What it still needs |
|---|---|---|
| PR #88 (`dev/hunger-unreach`) | Two starvation bugs on main: the hunger plan chose stores the eat step had given up on; a food-fetch reflex was never interrupted. Switches `instinct.HUNGER_REACH`, `actions.STARVING_FETCH`. A/B: discoveries 71.8 > 74.1 and 75.0 > 74.4, starvation even. | CI, Codex, merge |
| `dev/harness` | `tools/harness/`: per-seed runs and A/Bs, with preventable deaths, stuck chits, autopsies and fired counters for every mechanism | PR |
| `dev/zones` | Ten building dead zones (reuse only within reach), town-only buildings, #78 note. Switch `builder.NEED_SITING` | Merge main, 24-seed A/B with the harness, PR |
| `dev/hoard` | Hoarding, F33 / issue #7: a ceiling per good, sinks. Switch `actions.PLENTY` | The same |
| `dev/items` | A real use for every item, F35. Switch `items.ITEM_USES` | The same |
| `dev/rng-streams` | A separate random stream per system, to cut A/B noise | Being built |

**Found and not yet fixed:**

- **The model choice prompt hides the chit's body.** On a decision bench of the game's own one-letter choices (216 items), every model tested chose at about chance when the right answer was obvious. Gemma 4 12B picked "experiment" over "eat" at 96% for a chit at hunger 4 with food in hand. The scene shows needs as `Hunger 4 energy 66 ...`, and "hunger" is a fullness meter, so "hunger 4" reads as barely hungry. Putting the needs in plain words just before the options ("You are starving: your belly is nearly empty (fullness 4 of 100). Eat now.") took eat and sleep accuracy from about 20% to 99-100% for Gemma 4 12B, JevK5 4B and Ornith 35B. Next: make this change in `brain/prompt.py`.
- **Sheltering and sleeping give way to food only below hunger 8** (every other step: below 16). This starved two chits on seed 42 with the #88 fixes. Raising it to 16 was tried and reverted: it cost 0.5 era and starved more. It needs a narrower fix.
- **A stuck loop.** The harness found a chit that failed to pick up wood 56 times in a row with full hands while building a stockpile (seed 7, day 27).
- **Tools are never mended.** Tools break, but no chit mended or smelted one in four 60-day instinct runs.

**How to judge a change:**

- Run the harness A/B (`tools/harness/`) against a worktree at current `origin/main`.
- Use 60 days on two seed sets: the usual `42 7 99 1 2 3 4 5 6 11 12 13` (it flatters the base) and the fresh `21-32`. Add the 256 map on seeds 1 2 3 7.
- The bar: no seed starves more than on main without an explanation from the autopsy, and discoveries, era and population are about even or better.
- A change that alters a one-village world gets a module switch, which `tests/identity_runner.py` turns off (precedent: `projects.MAKE_FIRST`). A test must fail if the switch does nothing.
- A branch whose A/B isn't settled can merge with its switch off.

**Gates.** Keep pytest's exit status. A plain `| tail` once hid a failure:

```bash
python -m pytest tests plan/acceptance -q > /tmp/suite.txt 2>&1; s=$?; tail -1 /tmp/suite.txt; test $s -eq 0
```

**Traps that bit us:**

- `git stash` is shared between worktrees.
- An A/B base must be at current `origin/main`. One A/B ran against an old commit, and its gain was meaningless.
- A seed can sit on a knife edge: one single-revert variant starved 40 chits on one seed. Judge on 24 seeds.
- The loop-guard tests wait for `paused`, not `loop_error`.

**Open decisions for the owner:**

- Dual-GPU strict comparison (issue #13).
- Restoring the archived long-running worlds.
- Which decision model to use. JevK5 4B is 2.5x faster than Gemma 4 12B, with similar agreement with a 35B reference. JevK5 9B and Winnow 12B are being benched.
- Live-UI checks still owed: skip ahead, save and load, pack picker, recording meter, Docker Desktop.

## Continuation job

1. Prove the local working tree and branch state, and preserve any WIP.
2. Run the normal gates at the continuation head:
   - `pytest tests plan/acceptance`
   - `cd web && npm run build`
   - `npx vitest run --root .. --globals plan/acceptance/web tests/web`
3. Take the next open item from `docs/FIXES_2026-09-30.md` (or, once those are done, the research plan). Build
   it the same way the third pass was built:
   - Build it on a scratch branch.
   - Give each piece a test that fails without it (switch the check off and watch it fail).
   - Have its culture rules reviewed independently. The village-projects review found five knowledge leaks that
     the tests had missed.
   - A/B it against the head before merging.
4. Don't edit the frozen `plan/` contracts to represent post-plan work.
5. Re-run the full gates, tick the tracker, then update `CURRENT.md` and this file.

## How balance changes were judged

`T10` is chaotic per seed, so behaviour changes were judged with a 12-seed, 30-day instinct A/B on the T10 setup
(128 map, 18 chits). It runs a base checkout and a new one side by side and compares these per seed:

- discoveries
- era
- population and its low point
- starvations
- goods produced
- spam counts
- homes
- stored brick, charcoal, copper and iron

The harness lives on the owner's PC (`ab2.sh` + `sweep3.py`, not in the repo). An earlier copy in `/tmp`
was lost when WSL was shut down for a disk compaction. Rebuild it from this description if it is gone.

Results that matter for the next person:

- **Audit + move-in fix vs base, 12 seeds × 30 days:**
  - discoveries 22.9 → 22.4
  - era 5.6 → 5.4
  - population 58.8 → 58.7
  - starvations 0.3 → 0.0
  - homes 22.8 → 16.4 (the removed homeless side effect; see `7c8a910`)
- **Production buildings vs audit, 12 seeds × 30 days:**
  - goods produced at stations 0 → 388 per village
  - discoveries 22.4 → 22.3
  - era 5.4 → 5.5
  - population 58.7 → 59.2
  - starvations 0.0 → 0.2 (2 in one seed)
  - stored charcoal 5.8 → 35.4, brick 100 → 134, copper 1.6 → 3.2
  - no extra spam
- **Production buildings vs audit, 8 seeds × 60 days:**
  - goods produced 0 → 1160
  - discoveries 27.2 → 27.4
  - era 6.0 → 6.1
  - starvations 1.0 → 0.4
  - neither arm reaches iron in 60 instinct-only days
- **Village projects + buildings (second pass) vs `2ff1cd6`:**
  - 12 seeds × 30 days: discoveries 22.3 → 37.6, era 5.5 → 6.4, starvations 0.2 → 0.0, population 59.2 → 55.0
    (slower growth, not deaths).
  - 8 × 60 days: discoveries 27.4 → 44.2, era 6.1 → 6.9, population 59.0 → 59.1.
  - no speech, 6 × 30 days: discoveries 25.5 → 36.0.
  - About 10 projects are done and 7–11 useful buildings stand per village.
- **Ten ideas (third pass) vs `53e4b11`:**
  - direct, 12 × 30: discoveries 37.6 → 37.9, era 6.42 → 6.42, population 55.0 → 56.8, stored food +21%.
  - direct, 8 × 60: discoveries 44.2 → 47.5, era 6.9 → 6.9, population 59.1 → 60.0.
  - no speech, 12 × 30: discoveries 34.0 → 33.6, era 5.83 → 5.58. With food first off, it matches the base.
  - no speech, 8 × 60: discoveries 39.1 → 39.8, era 6.4 → 6.4, population 59.8 → 59.8; the day-30 gap is gone.
  - The sweep has extra columns: `outposts` and `forgot`. `sweep_abl.py` switches single features off (`nofood`,
    `nolore`, `nooutpost`, `noobit`, `foodlow=X`) to pin a change on one of them.
- **Ten more ideas (fourth pass) vs `811498d`:**
  - direct, 12 × 30: 37.9 → 39.0, 6.4 → 6.2, 56.8 → 56.4, not counted, 0.5 → 0.8, 8.1 → 8.2 (discoveries, era, population, starvations, copper, useful).
  - no speech, 12 × 30: 33.6 → 34.2, 5.6 → 5.4, 52.3 → 51.7, not counted, 2.3 → 4.2, 7.9 → 7.8.
  - direct, 8 × 60: 46.2 → 55.8, 6.9 → 7.0, 59.9 → 58.5, not counted, 0.4 → 6.5, 13.9 → 13.6.
  - no speech, 8 × 60: 39.8 → 43.8, 6.4 → 6.5, 59.8 → 59.6, not counted, 0.8 → 9.5, 13.8 → 13.5.
  - Run the A/B from a frozen worktree (`git worktree add --detach ~/projects/lc-snap <commit>`): sims import the
    code when they start, so editing the working tree mid-run mixes versions.
- **Instinct only:** the A/B has no model in the loop. What models do with the `work`, `study` and `upgrade` verbs
  has only been seen live.

## Live game notes (main PC)

- The live game runs from `~/projects/little-chits` on :8010:
  - start: `scripts/desktop.sh start 8010`
  - stop: `scripts/desktop.sh stop 8010`
  - The stop saves first.
  - `start` also starts or restarts the model servers through `~/start-gpus.sh`. When the cards are busy with
    other work, restart only the game: `scripts/desktop.sh stop 8010`, then from the repo root
    `setsid nohup make run PORT=8010 >>data/launcher.log 2>&1 </dev/null &`.
- The first start on schema 3 migrates `server/data/chits.sqlite` in place (about 5 s on the 206 MB save). A
  backup taken before that first start was kept on the owner's PC.
- Brain settings (`server/data/brains.json`) and model launch flags (`~/start-gpus.sh`) live outside git.
  Copy `brains.example.json` and `scripts/start-gpus.example.sh` to make your own.

## Manual validation debt

Don't call v2 fully hardware-qualified until the real-GPU checks marked 🖐 in `plan/PROGRESS.md` (T01, T03, T04,
T15, T17, T18, T19) are run and recorded. The 3090-only results are in `docs/MANUAL_CHECKS_2026-09-30.md`: T03
and the 5090 arm of T15 are still open. A coding continuation can prepare those checks, but must not fabricate
their outcome, and must not start or retune the 3090 or 5090 serving lanes for them without the owner's go-ahead.

## Merge boundary

`main` is canonical (v2 merged into it as PR #6). Work on a branch and merge by PR once CI is green. PR #5 is
superseded history: don't build on it or merge it.
