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

RULES_VERSION = 2  # 2: invention, library_hints, lore_rescue, storyteller, wanderers

# name -> (default: the behaviour before the rule existed, label, what switching it off means)
RULES: Dict[str, Dict[str, Any]] = {
    "religion": {
        "default": True,
        "label": "Religion & belief can emerge",
        "off": "No faith can be founded, joined, inherited, preached, prayed to or read from a tablet. Shrines "
               "can't be imagined, taught or built, and prompts say nothing of belief. (Switching it on does not "
               "make the belief system research-ready: see docs/RESEARCH_READINESS.md, gates C and D.)",
    },
    "invention": {
        "default": True,
        "label": "Chits can invent new things",
        "off": "No named inventions: the invent verb is refused and never offered. Discovering the world's own "
               "recipes by experimenting stays: that is nature, not invention.",
    },
    "library_hints": {
        "default": True,
        "label": "Libraries may hint at undiscovered technology",
        "off": "Studying at a library still trains scholars, but the village's scholars never get an idea of a "
               "recipe nobody knows. Every discovery is the chits' own.",
    },
    "lore_rescue": {
        "default": True,
        "label": "Protect endangered knowledge",
        "off": "No nudge for the last old chit who knows how to make something: no reminder in its prompt and no "
               "instinct plan to teach or write it down. Knowledge can die out on its own (and is still recorded "
               "when it does). A printing press the chits built still prints what it prints: that is their own "
               "technology, not a rescue.",
    },
    "storyteller": {
        "default": True,
        "label": "The storyteller may stir things up",
        "off": "No play-mode storyteller events: hard winters, droughts, sickness, fires, a wolf pack, a "
               "meteorite, a stranger, a bumper harvest. Experiments never have them anyway.",
    },
    "wanderers": {
        "default": True,
        "label": "Wanderers may join a village",
        "off": "No newcomers wander in to a shrinking village: a village that dies out stays dead. Experiments "
               "never have them anyway.",
    },
}

# knowledge that only means something where religion exists (World.learned refuses it when religion is off)
RELIGIOUS_KNOWLEDGE = frozenset({"design:shrine"})
VERB_RULE = {"pray": "religion", "preach": "religion", "invent": "invention"}  # verbs that exist only under a rule
_REFUSAL = {"religion": "there is no religion in this world, so nobody can {verb}",
            "invention": "nobody in this world invents new things (they can still experiment)"}


def refusal(verb: str) -> str:
    """The simulator's exact reason when a verb its world's rules rule out is tried."""
    return _REFUSAL[VERB_RULE[verb]].format(verb=verb)


@dataclass(frozen=True)
class WorldRules:
    religion: bool = True
    invention: bool = True
    library_hints: bool = True
    lore_rescue: bool = True
    storyteller: bool = True
    wanderers: bool = True
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
        rule = VERB_RULE.get(verb)
        return rule is None or getattr(self, rule)


LEGACY = WorldRules()


# Presets for the New Game screen: rules, and whether to play model-led (docs/MODEL_LED.md). Research Clean takes out
# the shared mechanics that blur a causal claim (docs/WORLD_RULES.md says what each removes); the Lab stays the
# authority for published studies.
PRESETS: Dict[str, Dict[str, Any]] = {
    "standard": {"label": "Standard", "rules": {}, "model_led": False,
                 "about": "Little Chits as intended: every system on; instinct helps a model's chits when it is slow."},
    "model_led": {"label": "Model-led", "rules": {}, "model_led": True,
                  "about": "The model supplies the intelligence; the chit keeps its body (reflexes) and nothing "
                           "hidden stands in for the model."},
    "research_clean": {"label": "Research Clean",
                       "rules": {"religion": False, "library_hints": False, "lore_rescue": False,
                                 "storyteller": False, "wanderers": False},
                       "model_led": True,
                       "about": "Fewer hidden mechanics: no religion, no library hints, no rescue of dying knowledge, "
                                "no storyteller and no wanderers; model-led. Closer to a clean test, but play is "
                                "still not a controlled experiment: use the Lab for that."},
    "sandbox": {"label": "Sandbox", "rules": {}, "model_led": False,
                "about": "Everything on, for fun rather than for claims. (Contact between islands is chosen with the "
                         "game mode.)"},
}


def describe() -> Dict[str, Any]:
    """Every rule with its default, label and meaning, and the presets, for the API and the New Game screen."""
    return {"version": RULES_VERSION, "rules": {k: dict(v) for k, v in RULES.items()},
            "presets": {k: dict(v) for k, v in PRESETS.items()}}
