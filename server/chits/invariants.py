"""InvariantMonitor (research plan item 42, first slice): what must never happen, checked as the world runs.

Hard invariants stop an experiment: a result from a run that broke one isn't a result. Soft ones are recorded
beside it. The live game only reports them (a long-running world may hold records from before a check existed).

Hard:
- negative_stock: a chit or a store holds less than nothing.
- unproven_worked: knowledge marked as proven by use with no tick it was proven on (a "learned" claim nothing backs).
- unknown_provenance: knowledge that came by no known way.
- foreign_mind (experiment contract): a chit thinking with a brain its world wasn't given (cross-world leakage).
- stand_in (experiment contract): a model's chit acting on an instinct plan (the contract says it waits).
Soft:
- loops: the same step failing for the same reason again and again (diag.step_failed).

Checks for the worldview engine (conversion only after exposure, no inherited beliefs, no narrator feedback) come
with it (research plan R8); treatments are kept to founder knowledge by lab/treatment.lint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import diag
from .sim.agent import KNOW_STATUS

INSTINCT = "instinct"
KNOWN_HOW = set(KNOW_STATUS) | {"raised"}  # (a child raised by its parents: told, like the default)
STAND_INS = ("instinct", "instinct-filler", "instinct-fallback", "instinct-routine", "instinct-duty")


class InvariantBroken(RuntimeError):
    def __init__(self, broken: List[Dict[str, Any]]):
        self.broken = broken
        super().__init__("; ".join(f"{b['kind']}: {b['what']}" for b in broken[:5]))


def check(world, contract: str = "play", world_brain: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def broke(kind, level, what, **kw):
        out.append({"kind": kind, "level": level, "tick": world.tick, "what": what, **kw})

    for a in world.agents.values():
        for k, n in a.inventory.items():
            if n < 0:
                broke("negative_stock", "hard", f"{a.name} holds {n} {k}", agent=a.id)
        for key, k in a.knows.items():
            if k.get("how") not in KNOWN_HOW:
                broke("unknown_provenance", "hard", f"{a.name} knows {key} by {k.get('how')!r}", agent=a.id)
            if k.get("status") == "worked" and k.get("worked_tick") is None:
                broke("unproven_worked", "hard", f"{a.name}'s {key} is marked proven with no tick", agent=a.id)
        if contract == "experiment":
            if world_brain is not None and a.brain != world_brain:
                broke("foreign_mind", "hard", f"{a.name} thinks with {a.brain!r} in a world given {world_brain!r}",
                      agent=a.id)
            if a.brain != INSTINCT and (a.plan_source or "") in STAND_INS and a.plan:
                broke("stand_in", "hard", f"{a.name} ({a.brain}) is acting on a {a.plan_source} plan", agent=a.id)
    for s in world.structures.values():
        for k, n in s.storage.items():
            if n < 0:
                broke("negative_stock", "hard", f"{s.design} {s.id} holds {n} {k}", structure=s.id)
    d = diag.of(world)
    if d.loops:
        broke("loops", "soft", ", ".join(f"{n} by {who}" for who, n in sorted(d.loops.items())))
    return out


def enforce(world, contract: str = "experiment", world_brain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Check, and stop on a hard break. Returns the soft ones."""
    found = check(world, contract, world_brain)
    hard = [b for b in found if b["level"] == "hard"]
    if hard:
        raise InvariantBroken(hard)
    return found
