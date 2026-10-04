# Handoff: work in flight

This file lets anyone, person or agent, pick up the current work without the conversation that produced it. Keep it current: update it in the same PR as any change that moves the queue.

Last updated: 2026-10-04.

## Where things stand

Merged on main today:

| PR | What |
|---|---|
| #82 | A held world well under its limit draws wanderers |
| #83 | A thing a world cannot name no longer stops it; a failed step pauses the game and says why |
| #84 | Settlement detection no longer compares every pair of buildings |
| #85 | Invention engine (F34): staged invention, stations, inventions that travel whole |

Closed: #86. It made `tests/test_village_identity.py` opt-in, which breaks the no-skip rule in AGENTS.md.

Pushed branches, not yet merged, in merge order:

| Branch | What | What it still needs |
|---|---|---|
| `dev/hunger-unreach` | Three starvation fixes (below) | A clean 24-seed A/B, then a PR |
| `dev/zones` | Ten building dead zones fixed (reuse only within reach), town-only buildings, Knowledge entry return position (#78 note). Switch: `builder.NEED_SITING` | Merge main, 24-seed A/B, PR |
| `dev/hoard` | Hoarding (F33, issue #7): a ceiling per good, sinks (mill, kiln, sowing). Switch: `actions.PLENTY` | The same |
| `dev/items` | A real use for every item (F35). Switch: `items.ITEM_USES` | The same |

Being built (branches not pushed yet):

- `dev/harness`: a test harness in `tools/harness/`. It flags preventable deaths (starved with reachable food) and stuck chits (the same failing goal replanned over and over), with an autopsy of each. It also counts how often every mechanism fires and lists the ones that never do.
- `dev/rng-streams`: a separate random stream per system, so a change to one system stops reshuffling the others and A/B noise drops.

## The hunger fix: three bugs that were already on main

Each came to light while chasing a starvation that a feature branch seemed to cause.

1. **The plan chose a store the step had given up on.** The eat step marks a store that is a long way round on foot as unreachable for a day, but the hunger plan ignored the mark and chose it again every tick. Now the plan uses the step's own lookups (`_stockpile_with`, `_farm_ready`). Switch: `instinct.HUNGER_REACH`.
2. **Nothing interrupted a food fetch.** A starving chit sent to fish walked between empty fish tiles until it died, holding fish. Below hunger 10 (`STARVING`) it now eats what it holds. After 40 ticks (`FETCH_PATIENCE`) with nothing, it eats from a store. Switch: `actions.STARVING_FETCH`.
3. **Weather beat hunger.** Sheltering, warming up, sleeping and carrying to the store gave way to food only below hunger 8; every other step gives way below 16. Now all of them give way below 16 (`HUNGRY`). Covered by `STARVING_FETCH`.

**Fix 1 is only safe with fix 2.** On its own it starved a world held at 10 chits (seed 11: 26 deaths): chits no longer sent to an unreachable store went foraging, which is where bug 2 trapped them.

A/B of fixes 1 and 2 against main (60 days, instinct):

| Seeds | Discoveries | Era | Starved per seed |
|---|---|---|---|
| 42 7 99 1-6 11-13 | 71.8 > 74.1 | 8.2 > 8.1 | 0.2 > 0.2 |
| 21-32 | 75.0 > 74.4 | 8.0 > 8.1 | 0 > 0 |

Seed 42 lost two chits with those two fixes; the autopsy traced both to bug 3. The A/B with all three fixes is in progress.

## How to do the next step

**Tests.** Run from `server/`, writing to a file. Piping into `tail` without `pipefail` once hid a failure.

```bash
python -m pytest ../tests ../plan/acceptance -q -p no:cacheprovider > /tmp/suite.txt 2>&1; tail -1 /tmp/suite.txt
```

Web changes also need:

```bash
cd web && npm run build
npx vitest run --root .. --globals plan/acceptance/web tests/web
```

**A/B.** Compare two checkouts: a worktree at `origin/main` as the base, and the branch. Run 60 days, instinct only, 128 map, on two seed sets: the usual set `42 7 99 1 2 3 4 5 6 11 12 13` (it flatters the base) and the fresh set `21-32`. For bigger islands, add the 256 map on seeds 1 2 3 7. Use `tools/harness/` once `dev/harness` merges.

**The bar.** No seed starves more than on main, and discoveries, era and population are about even or better. Explain every starvation with the autopsy before merging.

**Merging.**
1. Push the branch.
2. Open a PR against main.
3. Wait for the `test` check and the Codex review.
4. Fix every valid finding, then merge with a merge commit.

On the maintainer's machine, pushes go through a pre-push sanitizer scan.

**Merge behind a switch, turn it on later.** Any change that alters what a one-village world does has a module switch. `tests/identity_runner.py` turns every switch off (precedent: `projects.MAKE_FIRST`), and a test fails if the switch does nothing. A branch whose A/B isn't settled can merge with its switch off. Turning it on later is a one-line PR.

## Rules that bit us

- Never edit `plan/`, and never delete, skip or weaken tests (AGENTS.md).
- Every new test must fail without its change. Check by reverting the hunk.
- Never `git stash` when several worktrees share a repo: the stash is shared between them.
- A base worktree for an A/B must be checked out at current `origin/main`. One A/B today ran against an old commit by mistake, and its "big gain" was meaningless.
- Seeds can sit on a knife edge. One seed starved 40 chits in a single-revert variant and none in seven others. Judge on 24 seeds, not one.
- The loop-guard tests wait for `paused`, not `loop_error`: the runtime pauses last.

## Open decisions for the owner

- Dual-GPU strict comparison (issue #13): needs the running game stopped.
- Restore the archived long-running worlds: this would replace the current game.
- Try a typed-decision model (Winnow, a Gemma 4 12B decision fine-tune in GGUF) against Gemma 4 12B: needs a download.
- Visual checks still owed in the live UI: skip ahead, real save and load, pack picker, recording meter, a real Docker Desktop run.
