"""An experiment's protocol: what is compared, over which seeds, for how long, with which matched interventions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from ..sim.world import CULTURE_FLAGS

INTERVENTIONS = ("drought", "storm", "snow", "rain", "hard_winter", "ore_shortage")
LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# R1 item 71: fields that can change what a model decides or whether a request succeeds must match across
# model arms. Identity/routing (id, label, model, base_url, api_key) may differ because those are the treatment.
FAIR_MODEL_FIELDS = (
    "max_concurrency", "timeout", "temperature", "max_tokens", "json_mode", "disable_thinking",
    "extra_body", "prompt_style", "escalate_below", "escalate_share", "focus", "escalate_to",
)
# how a mind is built: what an architecture comparison (compare: "architecture") lets arms differ in, declared; every
# other fair-comparison field (sampling, tokens, timeouts, concurrency) must still match (docs/TWO_LEVEL.md)
ARCHITECTURE_FIELDS = ("prompt_style", "escalate_below", "escalate_share", "escalate_to")
# a model's own sampling (its card's temperature and sampler settings): what sampling: "native" lets differ, declared
SAMPLING_FIELDS = ("temperature", "extra_body")


class SpecError(ValueError):
    pass


@dataclass
class Arm:
    name: str
    culture: str = "direct"
    brain: str = "instinct"  # anything else is a model arm (refused without the owner's go-ahead)
    flags: Dict[str, bool] = field(default_factory=dict)  # capability flags over the culture's own
    treatment: str = ""  # a TreatmentPack id from the protocol's `treatments` (lab/treatment.py)
    # bounded action repair for this arm's model (research plan item 40): a step of its own that fails is answered,
    # once, with the simulator's exact reason, in a full brain's next prompt and in a choosing brain's next choice
    # scene (mind.choice_repair). Off by default, as every experiment ran before it could be declared
    repair: bool = False


@dataclass
class Intervention:
    day: int  # applied at the start of this day (1 = the first day), identically in every arm
    kind: str
    days: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentSpec:
    name: str
    arms: List[Arm]
    seeds: List[int]
    days: int
    size: int = 128
    population: int = 18
    contract: str = "experiment"
    blind: bool = True
    assign_seed: int = 0
    sample_every: int = 1  # days between the rows of each run's daily table
    metrics: List[str] = field(default_factory=list)  # the metrics the report leads with (all are recorded)
    events: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # time-to-event: name -> {"metric", "at_least"}
    interventions: List[Intervention] = field(default_factory=list)
    allow_models: bool = False
    brains: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # exact sealed BrainConfig dictionaries, keyed by id
    treatments: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # pack id -> the pack (inlined on load)
    notes: str = ""
    # paired card swaps (research item 72): model brain id -> its server on the other card. On every other seed
    # (the 2nd, 4th, ...) each model runs there instead, so a card's own effect cancels out over the pairs.
    card_swap: Dict[str, str] = field(default_factory=dict)
    # a diagnostic, never a comparison: every arm runs without the body's reflexes, and a model arm without anything
    # from instinct (the full prompt, no menu): what the model does on its own. Recorded in the manifest.
    model_only: bool = False
    # the world rules every arm's worlds are made with (sim/rules.py, docs/WORLD_RULES.md): {} is the legacy set. In
    # the fingerprint whenever it is set, and written out in full in the manifest
    rules: Dict[str, Any] = field(default_factory=dict)
    # "models" (the arms differ in the model only: research item 71) or "architecture" (they may also differ in how
    # the mind is built: prompt style and escalation, ARCHITECTURE_FIELDS). Declared, in the fingerprint when set
    compare: str = "models"
    # "matched" (every model arm samples alike: research item 71) or "native" (each brain its own card's temperature
    # and sampler settings, sealed per brain; for models whose makers ask for very different sampling). Declared
    sampling: str = "matched"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExperimentSpec":
        d = dict(d)
        known = set(cls.__dataclass_fields__)
        extra = set(d) - known
        if extra:
            raise SpecError(f"unknown protocol fields: {', '.join(sorted(extra))}")
        try:
            d["arms"] = [a if isinstance(a, Arm) else Arm(**a) for a in d.get("arms", [])]
            d["interventions"] = [i if isinstance(i, Intervention) else Intervention(**i) for i in d.get("interventions", [])]
            spec = cls(**d)
        except TypeError as e:
            raise SpecError(str(e)) from None
        spec.validate()
        return spec

    @classmethod
    def load(cls, path) -> "ExperimentSpec":
        text = Path(path).read_text()
        if str(path).endswith((".yaml", ".yml")):
            try:
                import yaml
            except ImportError:  # PyYAML is optional: a JSON protocol always works
                raise SpecError("reading YAML needs PyYAML (pip install pyyaml), or write the protocol as JSON") from None
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        # a pack may be named by a path (from the protocol's folder): it is read in, so the protocol's fingerprint
        # covers the pack's content and a changed pack can't resume an old run
        if isinstance(data, dict) and isinstance(data.get("treatments"), dict):
            base = Path(path).parent
            try:
                data["treatments"] = {k: json.loads((base / v).read_text()) if isinstance(v, str) else v
                                      for k, v in data["treatments"].items()}
            except (OSError, ValueError) as e:
                raise SpecError(f"reading a treatment pack: {e}") from None
        return cls.from_dict(data)

    def validate(self) -> None:
        if not self.name or not str(self.name).strip():
            raise SpecError("an experiment needs a name")
        if len(self.arms) < 2:
            raise SpecError("an experiment compares at least two arms")
        if len(self.arms) > len(LABELS):
            raise SpecError(f"at most {len(LABELS)} arms")
        names = [a.name for a in self.arms]
        if len(set(names)) != len(names):
            raise SpecError("arm names must be unique")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise SpecError("seeds must be a non-empty list without repeats")
        if self.days < 1 or self.sample_every < 1:
            raise SpecError("days and sample_every must be at least 1")
        if self.size < 32 or self.population < 2:
            raise SpecError("the island must be at least 32 tiles and hold at least 2 chits")
        if self.contract not in ("experiment", "play"):
            raise SpecError("contract is 'experiment' or 'play'")
        from ..brain.llm import BrainConfig

        brain_fields = set(BrainConfig.__dataclass_fields__)
        for bid, raw in self.brains.items():
            if not isinstance(raw, dict):
                raise SpecError(f"brain {bid!r}: config must be an object")
            extra = set(raw) - brain_fields
            if extra:
                raise SpecError(f"brain {bid!r}: unknown fields {', '.join(sorted(extra))}")
            if raw.get("id") != bid:
                raise SpecError(f"brain {bid!r}: config id must be {bid!r}")
            try:
                cfg = BrainConfig(**raw)
            except TypeError as e:
                raise SpecError(f"brain {bid!r}: {e}") from None
            if not cfg.base_url:
                raise SpecError(f"brain {bid!r}: base_url is required")
            if cfg.api_key and not cfg.api_key.startswith("env:"):
                raise SpecError(f"brain {bid!r}: put API keys in an environment variable and use api_key='env:NAME'")
            if not cfg.enabled:
                raise SpecError(f"brain {bid!r}: a lab brain must be enabled")

        for a in self.arms:
            if a.brain != "instinct" and a.brain not in self.brains:
                raise SpecError(f"arm {a.name}: no sealed brain config {a.brain!r} in protocol.brains")
        model_ids = sorted({a.brain for a in self.arms if a.brain != "instinct"})
        # a planner (escalate_to) writes plans for its arm: it matches that arm's brain in everything but how a mind is
        # built (a planner always gets the full prompt), in either kind of comparison, one model arm or several
        same = [f for f in FAIR_MODEL_FIELDS if f not in ARCHITECTURE_FIELDS
                and (getattr(self, "sampling", "matched") != "native" or f not in SAMPLING_FIELDS)]
        for m in model_ids:
            esc = str(self.brains[m].get("escalate_to") or "")
            if esc in self.brains and esc != m:
                pc, mc = BrainConfig(**self.brains[esc]), BrainConfig(**self.brains[m])
                diff = sorted(f for f in same if getattr(pc, f) != getattr(mc, f))
                if diff:
                    raise SpecError(f"planner {esc!r} must match brain {m!r} in {', '.join(diff)} (Codex on #144)")
        if len(model_ids) > 1:
            configs = {bid: BrainConfig(**self.brains[bid]) for bid in model_ids}
            ref_id = model_ids[0]
            ref = configs[ref_id]
            mismatches = []
            fair = [f for f in FAIR_MODEL_FIELDS if (self.compare != "architecture" or f not in ARCHITECTURE_FIELDS)
                    and (self.sampling != "native" or f not in SAMPLING_FIELDS)]
            for bid in model_ids[1:]:
                cfg = configs[bid]
                for field_name in fair:
                    if getattr(cfg, field_name) != getattr(ref, field_name):
                        mismatches.append(field_name)
            if mismatches:
                names = ", ".join(sorted(set(mismatches)))
                raise SpecError(
                    f"model arms must use identical comparison settings; differ in: {names}. "
                    "Only model identity/routing may differ (research item 71)"
                    + ("." if self.compare == "architecture" else
                       ", unless the protocol declares compare: \"architecture\" (then prompt style and escalation may).")
                )
        for a in self.arms:
            if a.culture not in CULTURE_FLAGS:
                raise SpecError(f"arm {a.name}: unknown culture {a.culture!r} (one of {', '.join(CULTURE_FLAGS)})")
            bad = set(a.flags) - {"say", "teach", "write"}
            if bad:
                raise SpecError(f"arm {a.name}: unknown flags {', '.join(sorted(bad))}")
            if not isinstance(a.repair, bool):
                raise SpecError(f"arm {a.name}: repair is true or false")
            if a.repair and a.brain == "instinct":
                raise SpecError(f"arm {a.name}: repair answers a model's failed step; an instinct arm has no model")
            if a.brain != "instinct" and not self.allow_models:
                raise SpecError(f"arm {a.name} thinks with a model: set allow_models (and the owner's go-ahead)")
        for i in self.interventions:
            if i.kind not in INTERVENTIONS:
                raise SpecError(f"unknown intervention {i.kind!r} (one of {', '.join(INTERVENTIONS)})")
            if not 1 <= i.day <= self.days:
                raise SpecError(f"intervention {i.kind} on day {i.day} is outside the run (1-{self.days})")
        from . import treatment as T

        for pid, pack in self.treatments.items():
            if not isinstance(pack, dict) or pack.get("id") != pid:
                raise SpecError(f"treatment {pid!r}: the pack's own id must be {pid!r}")
            try:
                T.check(pack)
            except T.TreatmentError as e:
                raise SpecError(str(e)) from None
        for a in self.arms:
            if a.treatment and a.treatment not in self.treatments:
                raise SpecError(f"arm {a.name}: no treatment {a.treatment!r} in the protocol's treatments")
        for name, ev in self.events.items():
            if "metric" not in ev or "at_least" not in ev:
                raise SpecError(f"event {name}: needs 'metric' and 'at_least'")
        if self.compare not in ("models", "architecture"):
            raise SpecError('compare is "models" or "architecture"')
        if self.sampling not in ("matched", "native"):
            raise SpecError('sampling is "matched" or "native"')
        if not isinstance(self.model_only, bool):
            raise SpecError("model_only is true or false")
        rules = self.world_rules()
        for pid, pack in self.treatments.items():  # (nothing in an experiment is dropped quietly: a pack the rules
            for p in pack.get("practices") or []:  # rule out is refused, not half-applied)
                if not rules.allows_knowledge(str(p.get("knowledge", ""))):
                    raise SpecError(f"treatment {pid!r} teaches {p.get('knowledge')}, which these world rules rule out")
        for bid, cfg in self.brains.items():  # a two-level mind (docs/TWO_LEVEL.md)
            esc = cfg.get("escalate_to") or ""
            if not esc:
                continue
            if esc == bid or esc not in self.brains:
                raise SpecError(f"brain {bid!r}: escalate_to names another brain in protocol.brains, not {esc!r}")
            if cfg.get("prompt_style") != "cascade":
                raise SpecError(f"brain {bid!r}: escalate_to is for a cascade brain (its escalations go to the planner)")
            if self.brains[esc].get("escalate_to"):
                raise SpecError(f"brain {esc!r}: a planner doesn't escalate further")
            if not self.brains[esc].get("model"):  # (so its identity is known, and redacted when blind)
                raise SpecError(f"brain {esc!r}: a planner names its model")
            if esc in self.card_swap:
                raise SpecError(f"brain {esc!r}: a planner stays on its own server (card_swap is for the arms' brains)")
        if self.card_swap:
            if len(model_ids) < 2 or set(self.card_swap) != set(model_ids):
                raise SpecError(f"card_swap names the other server of every model brain ({', '.join(model_ids) or 'none'}),"
                                " and needs at least two")
            if not all(isinstance(u, str) and u.strip() for u in self.card_swap.values()):
                raise SpecError("card_swap: each model's other server is a base URL")

    def world_rules(self):
        from ..sim.rules import WorldRules

        if not isinstance(self.rules, dict):
            raise SpecError("rules is an object of world rules (docs/WORLD_RULES.md)")
        try:
            return WorldRules.from_dict(self.rules or None)
        except ValueError as e:
            raise SpecError(f"rules: {e}") from None

    def brain_for(self, brain_id: str, seed_index: int) -> Dict[str, Any]:
        """The sealed config a model arm runs with on this seed: on a card-swapped seed, its other server."""
        cfg = dict(self.brains[brain_id])
        if self.swapped(seed_index):
            cfg["base_url"] = self.card_swap[brain_id]
        return cfg

    def swapped(self, seed_index: int) -> bool:
        return bool(self.card_swap) and seed_index % 2 == 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        """The protocol's identity: resuming or analysing a run under a changed protocol is refused. An option added
        later counts only when it is used, so a protocol written before it keeps its fingerprint."""
        d = self.to_dict()
        for k, default in LATER_OPTIONS.items():
            if d.get(k) == default:
                d.pop(k, None)
        for arm in d.get("arms") or []:  # (an arm's options added later count only when used, likewise)
            for k, default in ARM_LATER_OPTIONS.items():
                if arm.get(k) == default:
                    arm.pop(k, None)
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


ARM_LATER_OPTIONS: Dict[str, Any] = {"repair": False}  # arm options added after protocols were sealed
LATER_OPTIONS: Dict[str, Any] = {"card_swap": {}, "model_only": False, "rules": {}, "compare": "models",
                                 "sampling": "matched"}  # options added after protocols were sealed, at their "off" value
