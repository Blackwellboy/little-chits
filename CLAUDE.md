# Claude Code

Do not reconstruct Little Chits from old chat context.

Read, in order:

1. [CURRENT.md](CURRENT.md)
2. [HANDOFF.md](HANDOFF.md)
3. [AGENTS.md](AGENTS.md)
4. [plan/PROGRESS.md](plan/PROGRESS.md)
5. [docs/UPGRADE_PLAN.md](docs/UPGRADE_PLAN.md), then [docs/UPGRADE_STATUS_2026-09-29.md](docs/UPGRADE_STATUS_2026-09-29.md)

The frozen build plan is complete (41/41), and `plan/` stays read-only. Post-plan continuation is governed by
CURRENT and HANDOFF plus the existing invariants.

**Before touching Git state on any machine, follow HANDOFF's local-WIP recovery step in every worktree.** The Codex
WIP on the main PC was recovered and carried on 2026-09-29, and the agent branches preserved that day are merged. The
`wip/*` branches (local and remote) stay as history. Preserve any new local work; don't discard it.
