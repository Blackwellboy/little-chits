"""Food security: how many days the stores would feed the chits who eat from them.

The village's project used to run whatever the stores held: in 30-day runs the villages busy with projects had
more starving chits and slower growth. Now a chit that sees the stores around it running low puts the project aside
and fills them first, and a model is told the same thing in its scene. Each chit judges by what it can see (the
stockpiles and the chits within STORE_SIGHT tiles), so this works the same in a world whose chits can't talk. A
village with no stockpile yet has no stores to run low: its chits forage as they always did.
"""

from __future__ import annotations

from typing import Optional

FOOD_PER_DAY = 45.0  # hunger an adult burns in a day (0.22 a tick awake, less asleep)
FOOD_LOW = 3.0  # days of food in store below which the project waits and chits fill the stores
STORE_SIGHT = 25


def _food_in(world, piles) -> float:
    total = 0.0
    for p in piles:
        for k, n in p.storage.items():
            it = world.item(k)
            if n > 0 and it is not None and it.food > 0:
                total += n * it.food
    return total


def food_days(world, a=None) -> Optional[float]:
    """Days of food in store: the whole village's (a=None, for the observer), or the stores a chit can see, shared
    by the chits around them. None where there are no stores at all."""
    if a is None:
        piles = [s for s in world.structures.values() if s.design in ("stockpile", "warehouse", "outpost") and s.functional]
        mouths = len(world.agents)
    else:
        # the village's stockpiles, not an outpost camp's store (a camp worker saw 0 days by 10 ore and 200 bread
        # at home, and filled the camp with berries to rot)
        piles = [s for s in world.structures_near(a.x, a.y, STORE_SIGHT, "stockpile") if s.functional
                 and s.design in ("stockpile", "warehouse")]
        mouths = sum(1 for o in world.agents.values() if max(abs(o.x - a.x), abs(o.y - a.y)) <= STORE_SIGHT)
    if not piles:
        return None
    return round(_food_in(world, piles) / (max(1, mouths) * FOOD_PER_DAY), 1)


def short(world, a) -> bool:
    days = food_days(world, a)
    return days is not None and days < FOOD_LOW


def scene_line(world, a) -> Optional[str]:
    """What a chit sees of the stores around it (for its scene)."""
    days = food_days(world, a)
    if days is None or days >= 10:
        return None
    return (f"The stores near you hold about {days:g} days of food for the chits around"
            + (": too little, fill them before anything else." if days < FOOD_LOW else "."))
