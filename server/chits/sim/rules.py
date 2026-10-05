"""World rules: what kinds of civilisation a world allows (docs/WORLD_RULES.md).

A world's rules are chosen when it is made (New Game, a Lab protocol, the harness) and never change while it runs:
a frozen, versioned record, saved with the world and in every manifest. Each rule's default is how worlds behaved
before rules existed, so an old save (schema 2, no rules) loads with every rule at its default and plays as it did.

Adding a rule: give it a default that keeps today's behaviour, bump RULES_VERSION, and gate every path the rule
covers (with a test that the path is closed). A record from a newer version is refused, never reinterpreted.

The twin worlds of one game share their rules: World A and World B still differ only in CULTURE_FLAGS (AGENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

RULES_VERSION = 1

# name -> (default: the behaviour before the rule existed, label, what switching it off means)
RULES: Dict[str, Dict[str, Any]] = {
    "religion": {
        "default": True,
        "label": "Religion & belief can emerge",
        "off": "No faith can be founded, joined, inherited, preached, prayed to or read from a tablet. Shrines "
               "can't be imagined, taught or built, and prompts say nothing of belief. (Switching it on does not "
               "make the belief system research-ready: see docs/RESEARCH_READINESS.md, gates C and D.)",
    },
}

# knowledge that only means something where religion exists (World.learned refuses it when religion is off)
RELIGIOUS_KNOWLEDGE = frozenset({"design:shrine"})
RELIGIOUS_VERBS = frozenset({"pray", "preach"})


@dataclass(frozen=True)
class WorldRules:
    religion: bool = True
    version: int = RULES_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self.version, **{k: getattr(self, k) for k in RULES}}

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "WorldRules":
        """A saved or requested rule set. None (a world from before rules) is the legacy set. A newer version, an
        unknown rule or a value that isn't true/false is refused: a world's rules are never guessed."""
        if d is None:
            return cls()
        if not isinstance(d, dict):
            raise ValueError("world rules must be an object")
        v = d.get("version", RULES_VERSION)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ValueError(f"world rules version {v!r} is not a version")
        if v > RULES_VERSION:
            raise ValueError(f"world rules version {v} is newer than this build ({RULES_VERSION})")
        unknown = set(d) - {"version", *RULES}
        if unknown:
            raise ValueError(f"unknown world rules: {', '.join(sorted(unknown))}")
        vals = {}
        for k, spec in RULES.items():
            x = d.get(k, spec["default"])
            if not isinstance(x, bool):
                raise ValueError(f"world rule {k} must be true or false, not {x!r}")
            vals[k] = x
        return cls(**vals)  # (a record from an older version comes forward as this version: missing rules default)

    def changed(self) -> Dict[str, bool]:
        """The rules that differ from their defaults."""
        return {k: getattr(self, k) for k, spec in RULES.items() if getattr(self, k) != spec["default"]}

    def allows_knowledge(self, knowledge: str) -> bool:
        return self.religion or knowledge not in RELIGIOUS_KNOWLEDGE

    def allows_verb(self, verb: str) -> bool:
        return self.religion or verb not in RELIGIOUS_VERBS


LEGACY = WorldRules()


def describe() -> Dict[str, Any]:
    """Every rule with its default, label and meaning, for the API and the New Game screen."""
    return {"version": RULES_VERSION, "rules": {k: dict(v) for k, v in RULES.items()}}
