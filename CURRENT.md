# LITTLE CHITS — current

> **Public repository, 2026-10-02.** This repository starts from a single-commit snapshot of the private development repository (see `provenance/SOURCE.md`). Pull request and issue numbers below refer to that private history.

`CURRENT_ONLY=YES`

Status: **`main` is the live line.** v2 (PR #6) merged into it, and since then the expansion fixes and warehouse
(#7), the Experiment Lab (#8), the outside review's fixes (#9), BrainTape with lockstep experiments and the loop
detector (#10), action repair, compute accounting, request seeds and TreatmentPack (#11), the station-reach fix
with the InvariantMonitor (#12), the audit batches and Machine-Age/store fixes, strict Lab model arms with
identical-settings enforcement, the first deterministic proposition monitor, and collision-safe future chunk
identity. The live game on the owner's PC runs `main`.

## Authority

- **`main` is canonical.** Branch from it, open a PR into it, merge when CI is green. The branch names and heads
  below this section are history.
- The fix tracker is `docs/FIXES_2026-09-30.md` (two outside audits, checked against the code, with checkboxes).
  The research roadmap is `docs/RESEARCH_PLAN_2026-09-30.md`, with its own Progress section.
- Old draft PR #5 (`feat/day1-skeleton`) is superseded Day-1 lineage: don't build on it.
- Historical: v2 was developed on `claude/dazzling-dijkstra-5nv6xh` (last head `d386a1d`, 2026-09-29) as draft PR
  #6, while `main` held only the initial commit. That is no longer true.

## State

- Python: `tests/` + `plan/acceptance` pass on `main`; the web build (tsc + vite) and vitest (18 tests) pass. CI runs on
  every push and PR.
- `plan/PROGRESS.md`: **41/41 tasks done**, and the frozen plan stays read-only.
- Manual real-GPU checks (2026-09-30, RTX 3090 only, see `docs/MANUAL_CHECKS_2026-09-30.md`): T01, T17, T18 and
  T19 pass; T04 ran (the bench's spread is noted there); T15 is partial (3090 vs 3090); **T03 is open** (needs the
  5090). Don't mark T03 or the 5090 arm of T15 as passed until they are run.
- Live game: World A on instinct and World B on the 3090, while the 5090 is busy with other work (its brain is
  disabled at a dead port on purpose). Play versus is not a controlled comparison: see the tracker, F8 and F13.

## Upgrade status

The evidence audit of `docs/UPGRADE_PLAN.md` is in
[docs/UPGRADE_STATUS_2026-09-29.md](docs/UPGRADE_STATUS_2026-09-29.md).

- **DONE:** production buildings (#1), village projects (#2), research (#3), wants and renown (#6), visible eras
  (#7), outposts (#8), the storyteller (#9), the JEV cascade and the Mind panel.
- **PARTIAL:**
  - more buildings (#4: no dock, walls or stone hall);
  - item verbs (#5);
  - Invention 2.0 (#10);
  - one-token scoring beyond plans (the chief's project choice is done; elections and trades are not).
- The ten ideas of the third pass and the ten of the fourth, with commits, tests and A/B results, are in the status
  doc under "Third pass" and "Fourth pass".

## Codex recovery, resolved 2026-09-29 (history)

The Codex audit session had left its work uncommitted in the local worktree `~/projects/little-chits-audit-fixes`
(branch `codex/audit-fixes-2026-09-28` at `e2cc767`). It was handled in three steps.

1. **Preserved** as branch `wip/codex-audit-fixes-2026-09-29` (`59abd05`), local and pushed. A binary patch and a
   tarball of untracked files were kept on the owner's PC.
2. **Reviewed and carried** into v2 as `d6b8145` (fair twin worlds) and `df894c8` (atomic checkpoints, schema 3,
   provenance, stricter parsing, the supply ledger).
3. **Two defects fixed** that the carried code exposed: `7c8a910` (moving out of a crowded home) and `1a7fef1`
   (history across a restart).

Three other local-only agent branches were preserved and pushed as `wip/*` branches, and all three are now merged:

| Branch | Local | Remote | Merged |
|---|---|---|---|
| production buildings | `claude/production-buildings` | `wip/production-buildings-2026-09-28` | `c15b5ad` |
| village projects, research, wants | `claude/village-projects` | `wip/village-projects-2026-09-28` | `145c5e3`, fixes `cb1b1dd`, `e28bee8` |
| buildings | `claude/buildings` | `wip/buildings-2026-09-28` | `d0ae424` |

## What comes next

F11 furnace ore gate is closed with a 12-seed × 60-day paired A/B; see the fix tracker for the mixed but targeted result.

F30's station-output dip is explained and regression-pinned; F10 recovered almost all of it.

`docs/FIXES_2026-09-30.md` is the authority for remaining work. Most audit validity/ops items are now closed.
Immediate open work is the evidence-based chief decision (F12) and 5090-only checks when that card is free. Research then continues from the roadmap: this line
already has strict Lab model arms, identical-settings enforcement, the proposition monitor and persistent lifetime
dataset; card swaps/GPU energy and the later memory/Validation Chamber/worldview phases remain.

## Non-negotiable invariants

- `plan/` stays read-only to coding agents.
- The simulator is authoritative; brains only propose plans.
- World A and World B differ only by the intended culture flags. The storyteller applies the same random stream in
  both worlds and hands out no knowledge.
- Story, narrator and recorder data flow one way, out of simulation evidence, and never feed back into world
  truth.
- An experiment must never silently fall back to instinct, rewind, be god-mode mutated, or get play-only rescue
  mechanics. An unknown brain waits; a checkpoint with later events refuses to resume.
- New post-plan features need tests. Don't weaken existing gates.
- `main` is canonical: work on a branch, merge by PR with CI green. Never force-push `main`.

## Research layer (2026-09-30)

The plan for the research layer is `docs/RESEARCH_PLAN_2026-09-30.md` (73 items, phases R0-R16). Its first slice, the
Experiment Lab, runs pre-registered, blinded, multi-seed comparisons without a GPU:
`cd server && python -m chits.lab run ../docs/protocols/speech-vs-silence.json --out RUNS --jobs 8`, then
`python -m chits.lab analyze RUNS [--unblind]`.
