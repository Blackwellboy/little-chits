"""TreatmentPack (research plan item 46): what an arm's founders are told at the start, and nothing else.

A pack is data: its sources (each with a citation, edition and licence), its claims (each citing sources, with a
category), the practices it teaches (recipes and designs the simulator already has), which founders receive it, a
scope note and the reviewers' notes. The linter refuses a pack that could touch anything but what founders know:
physics, inventories, flags and the world stay the arm's own, so a difference between arms is the treatment's.

    {"id": "fire-keepers", "version": "1", "title": "...", "scope_note": "...",
     "sources": [{"id": "s1", "citation": "...", "edition": "...", "licence": "CC-BY-4.0"}],
     "claims": [{"id": "c1", "text": "...", "category": "practice", "sources": ["s1"]}],
     "practices": [{"knowledge": "recipe:sharp_stone", "sources": ["s1"]}],
     "founders": {"share": 0.5},
     "reviewer_notes": "..."}
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List

FIELDS = {"id", "version", "title", "scope_note", "sources", "claims", "practices", "founders", "reviewer_notes"}
REQUIRED = ("id", "version", "title", "scope_note", "sources")
CATEGORIES = ("practice", "belief", "norm", "value", "history", "story", "cosmology", "warning")
CLAIM_CHARS = 280  # a claim is one remembered sentence or two, not a document
TOKENS_PER_CHAR = 0.25  # the rough rule for English (the report's token counts are estimates)


class TreatmentError(ValueError):
    pass


def lint(pack: Dict[str, Any]) -> List[Dict[str, str]]:
    """Every problem, each {"level": "error"|"warning", "where", "problem"}. A pack with an error is refused."""
    from ..sim.items import DESIGNS, RECIPES

    out: List[Dict[str, str]] = []

    def err(where, problem, level="error"):
        out.append({"level": level, "where": where, "problem": problem})

    if not isinstance(pack, dict):
        return [{"level": "error", "where": "pack", "problem": "a pack is a JSON object"}]
    for k in sorted(set(pack) - FIELDS):
        err(k, "not a pack field: a treatment only changes what founders know (physics, inventories, flags and the "
               "world stay the arm's own)")
    for k in REQUIRED:
        v = pack.get(k)
        if not (v if k == "sources" else str(v or "").strip()):
            err(k, "missing")
    src_ids: List[str] = []
    for i, s in enumerate(pack.get("sources") or []):
        where = f"sources[{i}]"
        if not isinstance(s, dict) or not s.get("id"):
            err(where, "a source needs an id")
            continue
        src_ids.append(s["id"])
        for k in ("citation", "licence"):
            if not str(s.get(k) or "").strip():
                err(f"{where} {s['id']}", f"no {k}")
        if not str(s.get("edition") or "").strip():
            err(f"{where} {s['id']}", "no edition", "warning")
    for sid in {x for x in src_ids if src_ids.count(x) > 1}:
        err("sources", f"source id {sid!r} is used twice")
    cited = set()

    def cites(where, item):
        ids = item.get("sources") or []
        if not ids:
            err(where, "cites no source")
        for sid in ids:
            if sid not in src_ids:
                err(where, f"cites unknown source {sid!r}")
            cited.add(sid)

    claim_ids: List[str] = []
    for i, c in enumerate(pack.get("claims") or []):
        where = f"claims[{i}]"
        if not isinstance(c, dict) or not c.get("id") or not str(c.get("text") or "").strip():
            err(where, "a claim needs an id and text")
            continue
        claim_ids.append(c["id"])
        where += f" {c['id']}"
        if c.get("category") not in CATEGORIES:
            err(where, f"category {c.get('category')!r} is not one of {', '.join(CATEGORIES)}")
        if len(c["text"]) > CLAIM_CHARS:
            err(where, f"{len(c['text'])} characters: keep a claim under {CLAIM_CHARS}")
        cites(where, c)
    for cid in {x for x in claim_ids if claim_ids.count(x) > 1}:
        err("claims", f"claim id {cid!r} is used twice")
    for i, p in enumerate(pack.get("practices") or []):
        where = f"practices[{i}]"
        k = str((p or {}).get("knowledge") or "") if isinstance(p, dict) else ""
        kind, _, key = k.partition(":")
        if kind == "recipe" and key in RECIPES or kind == "design" and key in DESIGNS:
            cites(f"{where} {k}", p)
        else:
            err(where, f"{k or '(nothing)'} is not a recipe or design the simulator has ('recipe:<key>' or "
                       f"'design:<key>'): a treatment teaches, it never invents physics")
    if not pack.get("claims") and not pack.get("practices"):
        err("pack", "tells the founders nothing (no claims, no practices)")
    f = pack.get("founders", {"share": 1.0})
    share = f.get("share", 1.0) if isinstance(f, dict) else None
    if isinstance(f, dict) and set(f) - {"share"}:
        err("founders", f"only 'share' is known, not {', '.join(sorted(set(f) - {'share'}))}")
    if not isinstance(share, (int, float)) or isinstance(share, bool) or not 0 < share <= 1:
        err("founders", "share is the fraction of founders told, above 0 and at most 1")
    for sid in src_ids:
        if sid not in cited:
            err(f"sources {sid}", "cited by nothing", "warning")
    return out


def check(pack: Dict[str, Any]) -> Dict[str, Any]:
    errors = [p for p in lint(pack) if p["level"] == "error"]
    if errors:
        raise TreatmentError(f"treatment {pack.get('id', '?')!r}: " + "; ".join(f"{e['where']}: {e['problem']}" for e in errors))
    return pack


def fingerprint(pack: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(pack, sort_keys=True).encode()).hexdigest()[:16]


def coverage(pack: Dict[str, Any]) -> Dict[str, Any]:
    """What the pack holds and roughly what it adds to a told founder's memory, for the pre-registration."""
    claims = pack.get("claims") or []
    chars = sum(len(c.get("text", "")) for c in claims)
    cats: Dict[str, int] = {}
    for c in claims:
        cats[c.get("category", "?")] = cats.get(c.get("category", "?"), 0) + 1
    cited = {s for item in claims + (pack.get("practices") or []) for s in item.get("sources") or []}
    return {"id": pack.get("id"), "version": pack.get("version"), "fingerprint": fingerprint(pack),
            "claims": len(claims), "by_category": cats, "practices": len(pack.get("practices") or []),
            "sources": len(pack.get("sources") or []), "sources_cited": len(cited),
            "founder_share": (pack.get("founders") or {}).get("share", 1.0),
            "est_tokens_per_founder": round(chars * TOKENS_PER_CHAR)}


def apply(world, pack: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """Tell the chosen founders, before the first tick. Which founders is fixed by the seed and the pack, so the
    same seed tells the same chits in every arm that carries this pack."""
    check(pack)
    tag = f"treatment:{pack['id']}@{pack['version']}"
    founders = sorted(world.agents.values(), key=lambda a: a.id)
    share = (pack.get("founders") or {}).get("share", 1.0)
    n = max(1, round(len(founders) * share))
    told = random.Random(f"{seed}|{pack['id']}|{pack['version']}").sample(founders, min(n, len(founders)))
    for a in told:
        for p in pack.get("practices") or []:
            if world.rules.allows_knowledge(p["knowledge"]):  # (as World.learned: nothing the rules rule out)
                a.learn(p["knowledge"], "taught", world.tick, source=tag)
        for c in pack.get("claims") or []:
            a.remember(world.tick, c["text"], 3, "teaching")
    return {"pack": tag, "fingerprint": fingerprint(pack), "told": sorted(a.id for a in told), "of": len(founders)}
