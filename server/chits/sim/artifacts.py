"""Artifacts (T28): strange objects a god can drop into the world. They are ordinary items with properties;
chits find out what they do by picking them up, inspecting them and experimenting, like anything else."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .items import ITEMS, RECIPES, Item

ARTIFACTS: Dict[str, Item] = {
    i.key: i
    for i in [
        Item("meteorite", "meteorite", ("heavy", "scorched", "metallic", "fell from the sky"), weight=4, icon="☄️"),
        Item("alien_ship", "alien spaceship", ("huge", "humming", "impossible metal", "warm", "glowing symbols"),
             weight=99, icon="🛸"),
        Item("holy_book", "holy book", ("old", "leather-bound", "full of strange words"), icon="📖"),
        Item("treasure_chest", "treasure chest", ("heavy", "locked", "rattles"), weight=3, icon="🧰"),
        Item("golden_idol", "golden idol", ("gold", "gleaming", "a watching face"), weight=2, icon="🗿"),
        Item("musket", "musket", ("tool", "loud", "smoky", "dangerous"), tool="weapon", tool_power=3.0, icon="🔫"),
        Item("radio", "radio", ("crackles", "voices from nowhere", "humming"), icon="📻"),
        Item("seed_vault", "seed vault", ("cold", "sealed", "full of seeds"), weight=3, icon="🧊"),
        Item("time_capsule", "time capsule", ("sealed", "old", "humming faintly"), weight=2, icon="⏳"),
    ]
}
ITEMS.update(ARTIFACTS)  # items like any other (but never recipes, never knowledge)

UNCARRIABLE = {"alien_ship"}
TEACHERS = {"alien_ship", "radio"}


def is_artifact(key: Optional[str]) -> bool:
    return bool(key) and key in ARTIFACTS


def undiscovered(world, a=None) -> List[str]:
    """Base recipes nobody in this world has discovered yet (and this chit doesn't know)."""
    return [k for k in sorted(RECIPES) if f"recipe:{k}" not in world.first and not k.startswith("inv_")
            and (a is None or not a.knows_recipe(k))]


def on_pickup(world, a, key: str, tile: str) -> Optional[str]:
    """What happens when an artifact is picked up. Returns a note, or an error string starting with '!'."""
    here = world.ground.setdefault(tile, {"_t": world.tick})
    if key in UNCARRIABLE:
        return "!it's far too big to pick up — maybe inspect it"
    if key == "meteorite":
        _give(world, a, tile, "ore", 10)
        return "The meteorite crumbled into rich ore"
    if key == "seed_vault":
        _give(world, a, tile, "seeds", 30)
        return "The vault cracked open: seeds, so many seeds"
    if key == "treasure_chest":
        crafted = [k for k in sorted(RECIPES) if not k.startswith("inv_")]
        got: Dict[str, int] = {}
        for _ in range(8):
            k = world.rng_for("artifacts").choice(crafted)
            got[k] = got.get(k, 0) + 1
        for k, n in got.items():
            _give(world, a, tile, k, n)
        world.notice_items(a)
        return "The chest held " + ", ".join(f"{n} {world.item_name(k)}" for k, n in got.items())
    if key == "time_capsule":
        from .world import Tablet

        x, y = (int(v) for v in tile.split(","))
        pool = undiscovered(world)
        for k in world.rng_for("artifacts").sample(pool, min(3, len(pool))):
            tid = world._new_id("tablet")
            r = RECIPES[k]
            world.tablets[tid] = Tablet(tid, f"recipe:{k}", "", "someone long ago", world.tick, x, y, None,
                                        world.catalog.describe(r))
        return "The capsule opened: inside were old clay tablets covered in writing"
    return None  # an ordinary item: it goes into the inventory


def _give(world, a, tile: str, key: str, n: int) -> None:
    got = a.add(key, n)
    if got < n:
        pile = world.ground.setdefault(tile, {"_t": world.tick})
        pile[key] = pile.get(key, 0) + (n - got)


def on_inspect(world, a, key: str, s: Dict[str, Any]) -> Optional[str]:
    """Studying an artifact. Returns a note, or None if it has no inspect effect."""
    if key in TEACHERS:
        day = world.tick // 240
        uses = world.artifact_uses
        slot = f"{key}:{a.id}" if key == "alien_ship" else key
        if uses.get(slot) == day:
            return ("It hummed, but showed me nothing new today" if key == "alien_ship"
                    else "Only crackling today")
        pool = undiscovered(world, a)
        if not pool:
            return "It showed me things I already knew"
        uses[slot] = day
        k = world.rng_for("artifacts").choice(pool)
        world.learned(a, f"recipe:{k}", "inspected")
        art = ARTIFACTS[key].name
        world.emit("revelation", f"{a.name} studied the {art} and understood how to make {world.item_name(k)}", 5,
                   a.id, a.x, a.y, artifact=key, knowledge=f"recipe:{k}")
        return f"Studied the {art} and understood how to make {world.item_name(k)}"
    if key == "holy_book":
        if not world.rules.religion:  # (a world without religion: only a strange old book, sim/rules.py)
            return "Read the strange words of an old book; they meant nothing in particular"
        a.mood = min(100.0, a.mood + 10)
        if hasattr(world, "found_belief") and not a.belief:
            existing = next((bid for bid, b in world.beliefs.items() if b["name"] == "The Book"), None)
            if existing is None:
                world.found_belief(a, "The Book", "The words in the holy book came from beyond the sky")
            else:
                world.convert(a, existing, "read")
        return "Read the strange words of the holy book and felt moved"
    return None


def idol_positions(world) -> List[tuple]:
    out = []
    for tile, pile in world.ground.items():
        if pile.get("golden_idol"):
            x, y = tile.split(",")
            out.append((int(x), int(y)))
    for a in world.agents.values():
        if a.inventory.get("golden_idol"):
            out.append((a.x, a.y))
    return out
