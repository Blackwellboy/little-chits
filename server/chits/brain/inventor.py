"""An "invent" option for a chit that chooses with one token (F34).

In choose/cascade mode instinct drafts the options and the model answers with a letter. Instinct never invents, so a
chit that only ever chooses could never invent anything: the verb was out of its reach. `option()` drafts at most one
concrete invention from what the chit carries, straight from the rule table the simulator judges by (sim/invent.py),
so a small model can pick it with one letter.

It is offered only to a chit whose mind is a model. An instinct-only world never calls this (Instinct.options is the
choose path's alone) and the gate below refuses it anyway, so a world without a model keeps exactly the random streams
and events it had: nothing here draws a random number or touches the world.
"""

from __future__ import annotations

from itertools import combinations_with_replacement
from typing import Any, Dict, List, Optional, Tuple

from ..sim import artifacts as ART
from ..sim.agent import BASE_CAPACITY, Agent
from ..sim.invent import RULES, effect_words, readings, verdict
from ..sim.items import normalize_design, normalize_item

INSTINCT = "instinct"  # (brain.mind.INSTINCT: the brain id of a chit with no model)
PART_KINDS = 6  # how many kinds of carried things are tried as parts
BAG_SIZES = (2, 3)  # an option is a small thing: two or three pieces
LOW_HEALTH, LOW_MOOD = 80.0, 40.0  # below these a remedy, or something for joy, is worth offering

# what a chit would say it is for: each is understood by the judge as exactly that purpose (option() checks)
PURPOSE_TEXT = {
    "fishing": "to catch fish", "digging": "to dig stone and ore", "cutting": "to cut wood", "carrying": "to carry more",
    "warmth": "to keep warm", "defence": "a weapon against wolves", "farming": "a hoe to till the field",
    "light": "a light for the night", "speed": "to travel fast", "healing": "a remedy to heal", "joy": "a toy for joy"}
# what each rule's thing is called (after the material it is mostly made of)
NOUN = {"net": "Net", "fish_spear": "Fish Spear", "fish_trap": "Fish Trap", "forged_blade": "Cleaver", "hafted_blade": "Blade",
        "hand_blade": "Hand Blade", "forged_pick": "Mattock", "pick": "Mattock", "forged_weapon": "Mace", "club": "Club",
        "sling": "Sling", "hoe": "Hoe", "tonic": "Tonic", "poultice": "Poultice", "bandage": "Bandage", "wheels": "Rollers",
        "runners": "Runners", "sandals": "Sandals", "handcart": "Barrow", "pannier": "Pannier", "sack": "Sack",
        "garment": "Wrap", "mat": "Mat", "lamp": "Lamp", "torch": "Torch", "cooked_dish": "Hot Dish", "dish": "Dish",
        "ornament": "Charm"}
assert set(NOUN) == {r.key for r in RULES}


def model_driven(a: Agent) -> bool:
    return getattr(a, "brain", INSTINCT) != INSTINCT


def wanted(world, a: Agent) -> List[str]:
    """The purposes a new thing would answer for this chit now, the most useful first: what it has no tool or thing
    for. (Food is not one: cooking is found by experiment. Joy and healing only when it is low.)"""
    eff = (lambda kind: world.invention_effect(a, kind)) if world.catalog.items else (lambda kind: 0.0)
    warm = any(n > 0 and (it := world.item(k)) and "wearable" in it.props and "warm" in it.props for k, n in a.inventory.items())
    out = []
    if not a.best_tool("spear"):
        out.append("fishing")
    if not a.best_tool("pick"):
        out.append("digging")
    if not a.best_tool("axe"):
        out.append("cutting")
    if a.capacity() <= BASE_CAPACITY:
        out.append("carrying")
    if not warm and not eff("warmth"):
        out.append("warmth")
    if getattr(world, "animals", None) and not (a.best_tool("weapon") or a.best_tool("spear")):
        out.append("defence")
    if a.knows_design("farm") and not a.has("plough") and not eff("farming"):
        out.append("farming")
    if not a.best_tool("light"):
        out.append("light")
    if not eff("speed"):
        out.append("speed")
    if a.health < LOW_HEALTH and not eff("heal"):
        out.append("healing")
    if a.mood < LOW_MOOD and not eff("mood"):
        out.append("joy")
    return out


def parts(world, a: Agent) -> Dict[str, int]:
    """What the chit could put into an invention: its load, not its tools, its containers, a found artifact or an
    invention that is working for it."""
    out: Dict[str, int] = {}
    for k in sorted(a.inventory):
        n, it = a.inventory[k], world.item(k)
        if n <= 0 or it is None or it.tool or it.carry_bonus or ART.is_artifact(k):
            continue
        if world.catalog.items and world.invention_carried(k):
            continue
        out[k] = n
        if len(out) >= PART_KINDS:
            break
    return out


def _bags(have: Dict[str, int]):
    for size in BAG_SIZES:
        for combo in combinations_with_replacement(sorted(have), size):
            bag: Dict[str, int] = {}
            for k in combo:
                bag[k] = bag.get(k, 0) + 1
            if all(have[k] >= n for k, n in bag.items()):
                yield bag


def _name(world, a: Agent, bag: Dict[str, int], rule_key: str) -> Optional[str]:
    from ..sim.actions import sanitize_name

    main = max(sorted(bag), key=lambda k: bag[k])
    for cand in (f"{world.item_name(main).title()} {NOUN[rule_key]}", f"{a.name}'s {NOUN[rule_key]}"):
        name = sanitize_name(cand)
        if name and name == cand and not (normalize_item(name) or normalize_design(name) or world.invention_by_name(name)
                                          or world.catalog.pack_key(name)):
            return name
    return None


def option(world, a: Agent) -> Optional[Dict[str, Any]]:
    """One invention this chit could make now from what it carries, as a plan a model can pick: the first purpose it
    has a use for that some two or three of its things can serve. None for a chit without a model, a child, or when
    nothing it carries makes anything it lacks."""
    if not model_driven(a) or a.is_child(world.tick):
        return None
    want = wanted(world, a)
    have = parts(world, a)
    if not want or not have:
        return None
    here = world.stations_at(a.x, a.y)
    found: Dict[str, Tuple[Dict[str, int], Any, dict]] = {}
    for bag in _bags(have):
        for pid, (rule, effect) in readings(bag, world.catalog, here).items():
            if pid in want and pid not in found:
                found[pid] = (bag, rule, effect)
    for pid in want:
        if pid not in found:
            continue
        bag, rule, effect = found[pid]
        if any(inv.get("inputs") == bag and inv.get("purpose") == pid and f"recipe:{k}" in a.knows
               for k, inv in list(world.inventions.items()) + list(world.foreign.items())):
            continue  # it knows that one already (its own world's or one a traveller taught): it can simply make it
        v = verdict(bag, PURPOSE_TEXT[pid], world.catalog, here)
        name = _name(world, a, bag, rule.key)
        if not v["ok"] or v["purpose"] != pid or name is None:
            continue
        does = "; ".join(effect_words(v["effect"]))
        step = {"do": "invent", "with": [k for k in sorted(bag) for _ in range(bag[k])], "name": name,
                "purpose": PURPOSE_TEXT[pid]}
        if rule.station:  # drafted beside a station: made there, not as the weaker thing it would be anywhere else
            step["at"] = rule.station
        return {"goal": f"invent a {name} ({rule.what}: {does})",
                "thought": f"What I carry could make something new {PURPOSE_TEXT[pid]}.",
                "steps": [step]}
    return None
