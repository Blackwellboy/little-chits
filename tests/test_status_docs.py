"""Keep the handoff/status authority from silently drifting back to the pre-v2 branch."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_authority_docs_and_research_index_stay_current():
    current = (ROOT / "CURRENT.md").read_text()
    handoff = (ROOT / "HANDOFF.md").read_text()
    research = (ROOT / "docs" / "RESEARCH_PLAN_2026-09-30.md").read_text()

    assert "`main` is canonical" in current
    assert "Continue from `origin/main`" in handoff
    for stale in (
        "Default `main` is **not** the current implementation",
        "Continue from the remote branch, never from `main`",
        "Don't merge PR #6 into `main`",
    ):
        assert stale not in current
        assert stale not in handoff

    numbered = {int(n) for n in re.findall(r"(?m)^\|\s*(\d+)\s*\|", research)}
    assert 73 in numbered and max(numbered) == 73
    assert "73 items" in current
    assert (ROOT / "docs" / "FIXES_2026-09-30.md").exists()
    assert (ROOT / "docs" / "RESEARCH_PLAN_2026-09-30.md").exists()


def test_project_provenance_is_pinned_to_the_dedicated_repo():
    source = (ROOT / "provenance" / "SOURCE.md").read_text()
    assert "canonical implementation and design authority" in source
    assert "single commit" in source and "MIT" in source  # (the public snapshot, and what its history is)
    assert "protected `main`" in source
