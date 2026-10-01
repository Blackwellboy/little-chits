"""Blind labels: each arm gets a hidden label (A, B, ...) for the whole experiment, drawn from the protocol's
assign_seed; the order the arms run in rotates with each seed so every arm takes every position. Which label is which
arm is sealed in a separate file; the manifest carries only its hash, so a changed seal is caught when unblinding."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Dict, List

from .spec import LABELS, ExperimentSpec


def labels(spec: ExperimentSpec) -> Dict[str, str]:
    """label -> arm name."""
    arms = [a.name for a in spec.arms]
    order = list(arms)
    random.Random(f"assign:{spec.assign_seed}:{spec.name}").shuffle(order)
    return {LABELS[i]: name for i, name in enumerate(order)}


def run_order(spec: ExperimentSpec, seed_index: int) -> List[str]:
    """The labels in the order they run for one seed: a rotation, so over len(arms) seeds each label takes each slot."""
    ls = sorted(labels(spec))
    k = seed_index % len(ls)
    return ls[k:] + ls[:k]


def _digest(mapping: Dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest()


def seal(spec: ExperimentSpec, out: Path) -> str:
    """Write the sealed mapping and return its hash (for the manifest)."""
    mapping = labels(spec)
    d = Path(out) / "sealed"
    d.mkdir(parents=True, exist_ok=True)
    (d / "assignment.json").write_text(json.dumps(mapping, indent=2, sort_keys=True))
    return _digest(mapping)


def unblind(out: Path) -> Dict[str, str]:
    """label -> arm name, after checking the seal against the manifest's hash."""
    out = Path(out)
    manifest = json.loads((out / "manifest.json").read_text())
    mapping = json.loads((out / "sealed" / "assignment.json").read_text())
    if _digest(mapping) != manifest["assignment_sha256"]:
        raise ValueError("the sealed assignment doesn't match the manifest: it was changed after the run began")
    return mapping
