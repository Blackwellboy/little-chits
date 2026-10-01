"""Trimming model-written text to a length limit without leaving it mid-phrase."""

from __future__ import annotations

_DANGLING = ("and", "or", "but", "the", "a", "an", "of", "to", "with", "for", "so", "that", "which")


def clause_cut(text: str) -> str:
    """Text already cut to a length limit, trimmed back to its last clause (or at least word) boundary, so it
    doesn't end mid-phrase ("...ensuring long-term food security and")."""
    cut = max(text.rfind(p) for p in (".", ";", ",", " —", ":"))
    if cut >= len(text) * 0.6:
        return text[:cut].rstrip(" ,;:—")
    words = text.rsplit(" ", 1)[0] if " " in text else text
    while " " in words and words.rsplit(" ", 1)[-1].lower() in _DANGLING:
        words = words.rsplit(" ", 1)[0]
    return words.rstrip(" ,;:—")
