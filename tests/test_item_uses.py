"""The item pipeline: everything that can be made or found has a use, and a way to get it."""

from chits.sim.items import ACTION_USES, DESIGNS, ITEMS, RECIPES
from chits.sim.actions import GATHER_RULES
from chits.sim.artifacts import ARTIFACTS  # registers them in ITEMS, whatever order the tests run in

# Artifacts only arrive by god mode, and what they do is found on pickup and inspection (artifacts.on_pickup /
# on_inspect), so the made-or-found pipeline below is about everything else.
PIPELINE = [k for k in ITEMS if k not in ARTIFACTS]


def uses_of(k):
    it = ITEMS[k]
    uses = [f"recipe {r.key}" for r in RECIPES.values() if any(i == k for i, _ in r.inputs)]
    uses += [f"build {d.key}" for d in DESIGNS.values() if any(m == k for m, _ in d.materials)]
    uses += [f"idea for {d.key}" for d in DESIGNS.values() if ("item", k) in d.prereqs]
    if it.food:
        uses.append("food")
    if it.tool:
        uses.append(f"tool {it.tool}")
    if it.carry_bonus:
        uses.append("carrying")
    if "wearable" in it.props:
        uses.append("wearable")
    if k in ACTION_USES:
        uses.append(ACTION_USES[k])
    return uses


def test_every_item_has_a_use():
    dead = [k for k in PIPELINE if not uses_of(k)]
    assert not dead, f"items nobody can do anything with: {dead}"


def test_every_item_can_be_obtained():
    made = {r.key for r in RECIPES.values()}
    obtainable = set(GATHER_RULES) | made | {"meat", "wool", "grain"}  # hunting, tame sheep, harvesting farms
    missing = [k for k in PIPELINE if k not in obtainable]
    assert not missing, f"items with no way to get them: {missing}"


def test_every_recipe_input_and_station_exists():
    for r in RECIPES.values():
        for k, _ in r.inputs:
            assert k in ITEMS, (r.key, k)
        if r.station:
            assert any(d.station == r.station for d in DESIGNS.values()) or r.station == "fire", (r.key, r.station)
