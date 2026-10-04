"""The physical laws of the world: items, their properties, recipes and structure designs.

Chits are never handed this table. They see item *properties* and must discover
which combinations work by experimenting, watching, inspecting or being taught.
Nothing here is a tech tree the agent can browse; it's the chemistry of the world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    props: Tuple[str, ...]
    food: float = 0.0  # hunger restored when eaten
    tool: Optional[str] = None  # tool class this item provides
    tool_power: float = 0.0
    carry_bonus: int = 0
    weight: int = 1
    icon: str = ""


ITEMS: Dict[str, Item] = {
    i.key: i
    for i in [
        # raw materials
        Item("wood", "wood", ("sturdy", "long", "flammable"), icon="🪵"),
        Item("stone", "stone", ("hard", "heavy", "can be chipped"), icon="🪨"),
        Item("fiber", "plant fiber", ("flexible", "stringy", "light"), icon="🌾"),
        Item("berries", "berries", ("edible", "sweet", "soft"), food=18, icon="🫐"),
        Item("clay", "clay", ("moldable", "wet", "hardens in heat"), icon="🟫"),
        Item("sand", "sand", ("fine", "gritty", "melts in great heat"), icon="⏳"),
        Item("ore", "copper ore", ("heavy", "metallic streaks", "melts in great heat"), weight=2, icon="🟠"),
        Item("iron_ore", "iron ore", ("heavy", "rust-red streaks", "melts in great heat"), weight=2, icon="🟤"),
        Item("fish", "fish", ("edible", "raw", "slippery"), food=22, icon="🐟"),
        Item("seeds", "seeds", ("small", "alive", "can be planted"), icon="🌱"),
        Item("grain", "grain", ("edible", "dry", "can be ground or baked"), food=12, icon="🌾"),
        # crafted
        Item("sharp_stone", "sharp stone", ("sharp", "hard", "small"), icon="🔪"),
        Item("cord", "cord", ("strong", "binding", "flexible"), icon="🧵"),
        Item("stone_axe", "stone axe", ("tool", "cuts wood"), tool="axe", tool_power=2.0, icon="🪓"),
        Item("stone_pick", "stone pick", ("tool", "breaks rock"), tool="pick", tool_power=2.0, icon="⛏️"),
        Item("spear", "spear", ("tool", "pointed", "reaches into water"), tool="spear", tool_power=1.0, icon="🔱"),
        Item("basket", "basket", ("container", "woven"), carry_bonus=8, icon="🧺"),
        Item("cooked_fish", "cooked fish", ("edible", "hot", "filling"), food=40, icon="🍖"),
        Item("bread", "bread", ("edible", "baked", "very filling"), food=55, icon="🍞"),
        Item("berry_tart", "berry tart", ("edible", "baked", "delicious"), food=50, icon="🥧"),
        Item("brick", "brick", ("hard", "fired", "stackable"), icon="🧱"),
        Item("pot", "clay pot", ("container", "fired", "holds food"), carry_bonus=4, icon="🏺"),
        Item("charcoal", "charcoal", ("black", "burns very hot"), icon="⚫"),
        Item("clay_tablet", "clay tablet", ("flat", "can be inscribed"), icon="📜"),
        Item("copper", "copper", ("metal", "shiny", "malleable", "conducts heat"), icon="🥉"),
        Item("glass", "glass", ("clear", "brittle", "smooth"), icon="🔮"),
        Item("copper_axe", "copper axe", ("tool", "cuts wood", "metal"), tool="axe", tool_power=3.0, icon="🪓"),
        Item("copper_pick", "copper pick", ("tool", "breaks rock", "metal"), tool="pick", tool_power=3.0, icon="⛏️"),
        Item("lantern", "lantern", ("light", "warm", "portable"), tool="light", tool_power=1.0, icon="🏮"),
        # animals (T31)
        Item("meat", "meat", ("edible", "raw", "bloody"), food=25, icon="🥩"),
        Item("cooked_meat", "cooked meat", ("edible", "hot", "filling"), food=50, icon="🍖"),
        Item("wool", "wool", ("soft", "warm", "fluffy"), icon="🧶"),
        Item("cloth", "cloth", ("soft", "woven", "warm"), icon="🧣"),
        Item("cloak", "cloak", ("wearable", "warm", "soft"), icon="🧥"),
        # the long ladder (T22): iron, machines, lightning, and a rocket
        Item("iron", "iron", ("metal", "hard", "dark", "holds an edge"), icon="🔩"),
        Item("iron_axe", "iron axe", ("tool", "cuts wood", "metal"), tool="axe", tool_power=4.0, icon="🪓"),
        Item("iron_pick", "iron pick", ("tool", "breaks rock", "metal"), tool="pick", tool_power=4.0, icon="⛏️"),
        Item("plough", "plough", ("tool", "tills soil", "metal", "farming"), icon="🟁"),
        Item("wheel", "wheel", ("round", "rolls", "sturdy"), icon="☸️"),
        Item("cart", "cart", ("container", "rolls", "large"), carry_bonus=16, weight=3, icon="🛒"),
        # transport (issue #9): a sled before the cart, a wagon after it
        Item("sled", "sled", ("container", "slides", "wooden"), carry_bonus=10, weight=2, icon="🛷"),
        Item("wagon", "wagon", ("container", "rolls", "hauls"), carry_bonus=28, weight=4, icon="🐂"),
        Item("paper", "paper", ("thin", "flat", "can be inscribed", "light"), icon="📄"),
        Item("steel", "steel", ("metal", "very hard", "springy"), icon="🔗"),
        Item("gear", "gear", ("toothed", "precise", "metal"), icon="⚙️"),
        Item("engine", "steam engine", ("hot", "powerful", "turns wheels"), weight=3, icon="🚂"),
        Item("wire", "copper wire", ("thin", "metal", "conducts lightning"), icon="〰️"),
        Item("magnet", "magnet", ("metal", "pulls iron", "invisible force"), icon="🧲"),
        Item("dynamo", "dynamo", ("spins", "makes lightning", "humming"), weight=2, icon="⚡"),
        Item("lightbulb", "light bulb", ("glass", "glows with lightning"), tool="light", tool_power=2.0, icon="💡"),
        Item("fuel", "rocket fuel", ("volatile", "burns violently"), icon="🛢️"),
        Item("alloy", "alloy", ("light", "strong", "heat-proof", "metal"), icon="🪙"),
        Item("rocket_part", "rocket section", ("huge", "shaped", "heat-proof"), weight=4, icon="🚀"),
        # a mill's work (sim/buildings.py)
        Item("flour", "flour", ("fine", "powdery", "can be baked"), icon="🥣"),
        Item("loaf", "loaf", ("edible", "baked", "soft", "very filling"), food=75, icon="🥖"),
        # town life
        Item("ale", "ale", ("drink", "brewed", "cheering"), food=8, icon="🍺"),
        Item("clothes", "warm clothes", ("wearable", "warm", "woven"), icon="👕"),
    ]
}

STATIONS = ("fire", "workshop", "kiln", "furnace", "forge", "factory", "mill", "loom")
# the ores (issue #4): one kind of deposit tile, whose metal is fixed by its place and the world's seed (World.ore_item)
ORE_KINDS = ("ore", "iron_ore")
IRON_ORE_SHARE = 65  # percent of deposits that are iron: iron is the commoner ore

STORES = ("stockpile", "warehouse", "outpost")  # what holds a village's goods: its stockpiles and warehouses, and the
# store at each outpost camp
HOME_STORES = ("stockpile", "warehouse")  # ...of which these stand in the village
LIBRARIES = ("library", "great_library")  # where tablets are shelved, read, written and studied: a great library is a
# library too (the press shelved there what nobody could then read; review 2026-10-04, F32)


@dataclass(frozen=True)
class Recipe:
    key: str  # output item
    inputs: Tuple[Tuple[str, int], ...]
    station: Optional[str] = None
    qty: int = 1
    work: int = 6  # ticks

    @property
    def input_bag(self) -> FrozenSet[Tuple[str, int]]:
        return frozenset(self.inputs)

    def describe(self) -> str:
        parts = " + ".join(f"{n} {ITEMS[k].name}" if n > 1 else ITEMS[k].name for k, n in self.inputs)
        at = f" at a {self.station}" if self.station else ""
        return f"{parts}{at} -> {ITEMS[self.key].name}"


def _r(key: str, inputs: Dict[str, int], station: Optional[str] = None, qty: int = 1, work: int = 6) -> Recipe:
    return Recipe(key, tuple(sorted(inputs.items())), station, qty, work)


RECIPES: Dict[str, Recipe] = {
    r.key: r
    for r in [
        _r("sharp_stone", {"stone": 2}, work=4),
        _r("cord", {"fiber": 2}, work=4),
        _r("stone_axe", {"wood": 1, "sharp_stone": 1, "cord": 1}, work=8),
        _r("stone_pick", {"wood": 1, "stone": 1, "cord": 1}, work=8),
        _r("spear", {"wood": 1, "sharp_stone": 1}, work=6),
        _r("basket", {"cord": 1, "fiber": 2}, work=8),
        _r("cooked_fish", {"fish": 1}, station="fire", work=4),
        _r("bread", {"grain": 2}, station="fire", work=6),
        _r("berry_tart", {"berries": 2, "grain": 1}, station="fire", work=6),
        _r("pot", {"clay": 1}, station="kiln", work=8),
        _r("brick", {"clay": 1, "sand": 1}, station="kiln", qty=2, work=8),
        _r("charcoal", {"wood": 1}, station="kiln", qty=2, work=6),
        _r("clay_tablet", {"clay": 1, "sharp_stone": 1}, work=6),
        _r("copper", {"ore": 1, "charcoal": 1}, station="furnace", work=10),
        _r("glass", {"sand": 2}, station="furnace", work=10),
        _r("copper_axe", {"copper": 1, "wood": 1}, station="workshop", work=10),
        _r("copper_pick", {"copper": 1, "wood": 1, "cord": 1}, station="workshop", work=10),
        _r("lantern", {"glass": 1, "copper": 1}, station="workshop", work=10),
        _r("cooked_meat", {"meat": 1}, station="fire", work=4),
        _r("cloth", {"wool": 2}, station="workshop", work=8),
        _r("cloak", {"cloth": 2, "cord": 1}, station="workshop", work=10),
        _r("iron", {"iron_ore": 2, "charcoal": 2}, station="furnace", work=12),
        _r("iron_axe", {"iron": 1, "wood": 1}, station="workshop", work=10),
        _r("iron_pick", {"iron": 1, "wood": 1, "cord": 1}, station="workshop", work=10),
        _r("plough", {"iron": 2, "wood": 1}, station="workshop", work=12),
        _r("wheel", {"wood": 2, "iron": 1}, station="workshop", work=10),
        _r("cart", {"wheel": 2, "wood": 2}, station="workshop", work=12),
        _r("sled", {"wood": 2, "cord": 1}, work=6),
        _r("wagon", {"cart": 1, "wheel": 2, "iron": 1}, station="workshop", work=16),
        _r("paper", {"fiber": 3}, station="workshop", qty=2, work=8),
        _r("steel", {"iron": 2, "charcoal": 1}, station="forge", work=14),
        _r("gear", {"steel": 1}, station="workshop", qty=2, work=10),
        _r("engine", {"steel": 2, "gear": 2, "pot": 1}, station="forge", work=20),
        _r("wire", {"copper": 1}, station="factory", qty=3, work=8),
        _r("magnet", {"iron": 1, "wire": 1}, station="factory", work=10),
        _r("dynamo", {"magnet": 1, "wire": 2, "engine": 1}, station="factory", work=20),
        _r("lightbulb", {"glass": 1, "wire": 1}, station="factory", work=8),
        _r("fuel", {"charcoal": 2, "pot": 1}, station="factory", work=10),
        _r("alloy", {"steel": 1, "copper": 1}, station="factory", work=12),
        _r("rocket_part", {"alloy": 2, "engine": 1}, station="factory", work=24),
        _r("flour", {"grain": 1}, station="mill", work=4),
        _r("loaf", {"flour": 2}, station="fire", work=6),
        _r("ale", {"grain": 2, "berries": 1}, station="workshop", qty=2, work=6),
        _r("clothes", {"fiber": 4, "cord": 1}, station="loom", work=8),
    ]
}

# Everyone starts knowing these "obvious" facts (like how to knap a flake).
STARTING_RECIPES: Tuple[str, ...] = ()


# uses that live in the actions rather than in a recipe or a design (tests/test_item_uses.py checks that every item
# has at least one use, so nothing can be discovered that the chits can't do anything with; and, F35, that each use
# named here is proved by a test that runs the code doing it)
ACTION_USES: Dict[str, str] = {
    "clay_tablet": "write knowledge on it (at a library it lasts)",
    "paper": "write knowledge on it",
    "seeds": "plant them in a farm",
    "ale": "drink it at the tavern in the evening (more cheer than without)",
    "clothes": "wear them: a warm thing to wear halves the cold",
    "grain": "eat it, or bake bread at a fire",
    "plough": "carry it while harvesting a farm to double the base grain yield",
    "wood": "feed a campfire with it, or mend what is built of it",
    "charcoal": "feed a campfire with it: it burns far longer than wood",
    "stone": "mend what is built of it",
    "fiber": "mend what is built of it (a hut's thatch)",
    "clay": "mend what is built of it (a kiln)",
    "cord": "mend what is built with it (re-lash a stockpile, a bridge, a pen)",
    "brick": "mend what is built of it",
    "sharp_stone": "carry it while gathering plant fiber: it cuts two at a stroke",
}
# ...of which these are a second use of something gathered or made for something else: no reason for a station to make
# it in bulk before anything needs it (actions._useful; a kiln would turn the wood into charcoal before copper is known)
ITEM_USES = True  # F35's item uses and fixes (fuel, mending, a sharp stone, meal cheer, arms wear and defence, lights,
# the plough kept in hand). False restores the behaviour before them, for tests/identity_runner.py, which compares a
# one-village world with the tree before step 2b day by day (as projects.MAKE_FIRST does). Read at call time.
SIDE_USES: Tuple[str, ...] = ("wood", "charcoal", "stone", "fiber", "clay", "cord", "brick", "sharp_stone")

FUEL_VALUE: Dict[str, int] = {"wood": 35, "charcoal": 60}  # what one piece adds to a campfire's fuel (of 100)
# what a building may be mended with, when it is one of the building's own materials: plain building stuff, never the
# metal, glass, tablets or machines in it (the first material of a design always mends it, as before)
MEND_WITH: Tuple[str, ...] = ("wood", "stone", "fiber", "clay", "cord", "brick")
SHARP_FIBER = 2  # plant fiber cut per stroke with a sharp stone in hand (1 by hand)


def hand_tool(it: "Optional[Item]") -> bool:
    """A thing kept in hand and used as it is: any tool class, and a tool with none (the plough, which works by being
    carried at harvest: stored with the rest of a load it never doubled anything)."""
    return it is not None and bool(it.tool or (ITEM_USES and "tool" in it.props))


def match_recipe(bag: Dict[str, int], station: Optional[str]) -> Optional[Recipe]:
    """Return the recipe whose exact multiset of inputs matches ``bag`` at ``station``.

    A recipe that needs no station also works at any station (you can knap stone next to a fire).
    """
    key = frozenset((k, v) for k, v in bag.items() if v > 0)
    for r in RECIPES.values():
        if r.input_bag == key and (r.station is None or r.station == station):
            return r
    return None


@dataclass(frozen=True)
class Design:
    key: str
    name: str
    materials: Tuple[Tuple[str, int], ...]
    work: int
    # knowledge a chit needs before it can *imagine* this design:
    # ("item", k) = has handled item k; ("recipe", k) = knows recipe k; ("design", k)
    prereqs: Tuple[Tuple[str, str], ...] = ()
    size: Tuple[int, int] = (1, 1)
    station: Optional[str] = None
    blurb: str = ""
    decay_per_day: float = 4.0
    min_pop: int = 0  # a great work needs a great many hands (T22)

    @property
    def material_map(self) -> Dict[str, int]:
        return dict(self.materials)


def _d(key, name, materials, work, prereqs=(), size=(1, 1), station=None, blurb="", decay=4.0, min_pop=0) -> Design:
    return Design(key, name, tuple(materials.items()), work, tuple(prereqs), size, station, blurb, decay, min_pop)


DESIGNS: Dict[str, Design] = {
    d.key: d
    for d in [
        _d("campfire", "campfire", {"wood": 3, "stone": 2}, 10, (), station="fire",
           blurb="warmth and light at night; cook food here; burns wood as fuel (or charcoal, which lasts longer)", decay=0.0),
        _d("hut", "hut", {"wood": 8, "fiber": 4}, 30, (), size=(2, 2),
           blurb="a home: sleep here to recover faster and stay warm; families need one"),
        _d("stockpile", "stockpile", {"wood": 6, "cord": 1}, 14, (("recipe", "cord"),),
           blurb="shared storage anyone can put things into or take from"),
        _d("warehouse", "warehouse", {"wood": 16, "stone": 10, "cord": 4}, 40, (("design", "stockpile"), ("recipe", "cord")),
           size=(2, 2), blurb="a big roofed store that holds four times what a stockpile does (a stockpile can be "
                              "rebuilt into one: upgrade)", min_pop=12),
        _d("farm", "farm plot", {"wood": 3, "seeds": 3}, 20, (("item", "seeds"),), size=(2, 2),
           blurb="plant seeds, wait, harvest grain (nothing grows in winter)"),
        _d("workshop", "workshop", {"wood": 10, "stone": 6, "cord": 2}, 40,
           (("recipe", "stone_axe"), ("recipe", "stone_pick")), size=(2, 2), station="workshop",
           blurb="a workbench for fine crafting"),
        _d("kiln", "kiln", {"clay": 8, "stone": 4}, 35, (("item", "clay"), ("design", "campfire")),
           station="kiln", blurb="an enclosed fire, far hotter than a campfire"),
        _d("furnace", "furnace", {"brick": 6, "stone": 6}, 50, (("recipe", "brick"), ("item", "ore")),
           station="furnace", blurb="a roaring brick furnace hot enough to melt rock and sand"),
        _d("road", "road", {"stone": 1}, 3, (("recipe", "stone_pick"),),
           blurb="a paved tile; walking on roads is much faster", decay=0.5),
        _d("brick_house", "brick house", {"brick": 12, "wood": 4}, 60, (("recipe", "brick"), ("design", "hut")),
           size=(2, 2), blurb="a warm, sturdy home for up to five", decay=1.0),
        _d("library", "library", {"brick": 10, "wood": 6, "clay_tablet": 2}, 70, (("recipe", "clay_tablet"),),
           size=(2, 2), blurb="holds inscribed tablets so knowledge outlives its writers; read here to learn",
           decay=1.0),
        _d("forge", "forge", {"brick": 10, "iron": 4, "stone": 6}, 80, (("recipe", "iron"),), size=(2, 2), station="forge",
           blurb="a blast forge hotter than any furnace, for steel and engines", decay=1.0),
        _d("factory", "factory", {"brick": 20, "steel": 8, "engine": 2}, 150, (("recipe", "engine"),), size=(3, 3),
           station="factory", blurb="machines that make machines", decay=1.0, min_pop=20),
        _d("launch_pad", "launch pad", {"brick": 40, "steel": 20, "rocket_part": 6, "fuel": 10, "dynamo": 2}, 400,
           (("recipe", "rocket_part"), ("recipe", "fuel"), ("recipe", "dynamo")), size=(3, 3),
           blurb="a tower and a rocket: the island's reach for the sky", decay=0.3, min_pop=40),
        _d("pen", "pen", {"wood": 6, "cord": 2}, 20, (("recipe", "cord"),), size=(2, 2),
           blurb="a fenced pen for tame animals"),
        _d("boat", "boat", {"wood": 10, "cord": 4}, 40, (("recipe", "cord"), ("recipe", "stone_axe")),
           blurb="a boat to cross the sea"),
        _d("market", "market", {"wood": 8, "stone": 4, "cord": 2}, 30, (("recipe", "basket"),), size=(2, 2),
           blurb="a place to meet and trade"),
        _d("shrine", "shrine", {"stone": 6, "wood": 2}, 25, (("belief", "any"),),
           blurb="a sacred place; chits come here to pray", decay=0.5),
        _d("monument", "monument", {"stone": 16, "copper": 4}, 90, (("recipe", "copper"),), size=(2, 2),
           blurb="a great shared work that lifts the spirits of everyone nearby", decay=0.3),
        # great works: a whole village's labour for a season, each with something it really does (sim/buildings.py)
        _d("great_library", "great library", {"brick": 20, "wood": 12, "stone": 10, "clay_tablet": 4}, 160,
           (("design", "library"), ("recipe", "clay_tablet")), size=(3, 3),
           blurb="a great work: a hall of tablets where every hour of study goes twice as far", decay=0.3, min_pop=25),
        _d("lighthouse", "lighthouse", {"stone": 20, "wood": 10, "glass": 4, "copper": 2}, 140,
           (("design", "boat"), ("recipe", "glass")), size=(2, 2),
           blurb="a great work on the shore: its light guides boats, and voyages take half the time", decay=0.3, min_pop=20),
        _d("aqueduct", "aqueduct", {"stone": 30, "brick": 12, "iron": 2}, 180, (("recipe", "iron"), ("design", "well")),
           size=(3, 2), blurb="a great work: water carried to the fields; farms near it grow faster and keep growing "
                              "through a drought", decay=0.3, min_pop=25),
        # bigger homes, a bridge and buildings that do something: what each one does is in sim/buildings.py
        _d("longhouse", "longhouse", {"wood": 16, "cord": 4, "stone": 6}, 55, (("design", "hut"), ("recipe", "cord")),
           size=(3, 2), blurb="a long timber hall, a home for a big family of up to 6 (a hut can be rebuilt into one: "
                              "upgrade)", decay=2.0),
        _d("two_storey_house", "two-storey house", {"brick": 16, "wood": 8, "glass": 4}, 90,
           (("design", "brick_house"), ("recipe", "glass")), size=(2, 2),
           blurb="a tall brick house with glass windows, home for up to 8 and warm in any weather (a brick house or "
                 "longhouse can be rebuilt into one: upgrade)", decay=0.8),
        _d("bridge", "bridge", {"wood": 10, "cord": 3}, 30, (("recipe", "cord"), ("recipe", "stone_axe")),
           blurb="planks over 1-3 tiles of river or shallow water: walk across it, and sand, clay or ore on the far "
                 "bank come within reach (built at the nearest narrow crossing)", decay=1.5),
        _d("well", "well", {"stone": 10, "wood": 2, "cord": 2}, 30, (("recipe", "cord"), ("design", "farm")),
           blurb="fresh water: chits sleeping near it recover faster, and farms within 6 tiles grow a third faster",
           decay=0.5),
        _d("granary", "granary", {"wood": 10, "stone": 6, "cord": 2}, 40, (("design", "stockpile"), ("item", "grain")),
           size=(2, 2), blurb="a dry raised store-house: food in stockpiles within 10 tiles no longer rots (elsewhere "
                              "about 2% of stored food spoils each day, unless the stockpile holds clay pots)",
           decay=1.0),
        _d("mill", "mill", {"stone": 10, "wood": 8, "cord": 2}, 50, (("item", "grain"), ("recipe", "stone_pick")),
           size=(2, 2), station="mill",
           blurb="a millstone that grinds grain; what it grinds bakes into bread far more filling than plain bread",
           decay=1.0),
        _d("smithy", "smithy", {"brick": 8, "stone": 6, "wood": 4}, 55, (("recipe", "copper"), ("design", "workshop")),
           size=(2, 2), station="workshop",
           blurb="an anvil and bellows: it works as a workshop, and metal tools are made there twice as fast",
           decay=1.0),
        _d("watchtower", "watchtower", {"wood": 12, "stone": 6, "cord": 2}, 40, (("recipe", "spear"), ("recipe", "cord")),
           blurb="a lookout: wolves that come within 12 tiles are spotted and driven off, and bite no one there",
           decay=1.0),
        _d("school", "school", {"wood": 10, "stone": 6, "clay_tablet": 1}, 50, (("recipe", "clay_tablet"),),
           size=(2, 2), blurb="children within 8 tiles learn what the grown-ups around it know how to make, far "
                              "faster than by watching", decay=1.0),
        _d("mine", "mine", {"wood": 8, "stone": 6, "cord": 2}, 40, (("recipe", "copper"),), size=(2, 2),
           blurb="dug into rock or hills: a seam that gives copper and iron ore again every day (dig it with a pick)", decay=1.5),
        _d("sand_pit", "sand pit", {"wood": 4, "stone": 2}, 20, (("recipe", "brick"),), size=(2, 2),
           blurb="dug by a shore or riverbank: a pit that gives sand back every day, for bricks and glass", decay=1.5),
        _d("outpost", "outpost camp", {"wood": 8, "stone": 4, "cord": 2}, 30, (("design", "stockpile"), ("recipe", "cord")),
           size=(2, 2), blurb="a camp beside far ore, sand or clay: its store holds what is gathered there, chits sleep "
                              "there on long trips, and haulers carry it home", decay=1.5),
        _d("bell_tower", "bell tower", {"brick": 8, "wood": 6, "copper": 4}, 70, (("recipe", "copper"),),
           blurb="its bell rings every morning: everyone within 20 tiles gathers for a moment, lifting spirits and "
                 "friendships (and hearing the chief's plan)", decay=0.5, min_pop=10),
        # towns: a hall at the heart of a big village makes it a town; its square is where everyone meets
        _d("palisade", "palisade", {"wood": 30, "stone": 10, "cord": 6}, 80, (("design", "town_hall"), ("design", "watchtower")),
           size=(2, 2), blurb="a timber wall and gate round a town: no wolf bites anyone within 22 tiles of its gate",
           decay=1.0),
        _d("town_hall", "town hall", {"brick": 16, "wood": 10, "stone": 10, "glass": 2}, 120,
           (("recipe", "clay_tablet"), ("recipe", "brick"), ("recipe", "glass")), size=(3, 2),
           blurb="the heart of a town: a village of 20 or more with a hall becomes a town, its market, library, school "
                 "and other public buildings go up around it, and its busiest paths get paved into streets",
           decay=0.5, min_pop=20),
        _d("plaza", "plaza", {"stone": 12}, 20, (("design", "town_hall"),), size=(3, 3),
           blurb="a paved town square beside the hall: everyone within 12 tiles gathers there in the evening, which "
                 "lifts spirits and makes neighbours friends", decay=0.3),
        # town life: each needs the idea of a town hall, so nothing changes until a world has towns
        _d("tavern", "tavern", {"wood": 12, "brick": 6, "stone": 4}, 50, (("recipe", "ale"), ("design", "town_hall")),
           size=(2, 2), blurb="ale and company: in the evening everyone within 10 tiles drops in, and with ale from the "
                              "stores nearby spirits lift three times as much and friendships grow"),
        _d("bakery", "bakery", {"brick": 10, "stone": 4, "wood": 4}, 40, (("design", "mill"), ("design", "town_hall")),
           size=(2, 2), station="fire", blurb="a baker's oven: bread, loaves and tarts baked here come out two for one"),
        _d("healer", "healer's house", {"wood": 10, "stone": 6, "pot": 2}, 40, (("recipe", "pot"), ("design", "town_hall")),
           size=(2, 2), blurb="a place to mend: the hurt and sick within 10 tiles heal three times as fast, and the badly "
                              "hurt go there to rest"),
        _d("tailor", "tailor", {"wood": 8, "stone": 4, "cord": 4}, 35, (("recipe", "cord"), ("design", "town_hall")),
           size=(2, 2), station="loom", blurb="a loom and a cutting table: warm clothes are woven here from plant fiber "
                                              "and cord, and a warm thing to wear halves the cold"),
        _d("park", "park", {"wood": 4, "stone": 4, "seeds": 6}, 25, (("design", "town_hall"),), size=(2, 2),
           blurb="trees, flowers and a bench: everyone within 6 tiles is in better spirits, as by a monument", decay=1.0),
        _d("apartment", "apartment block", {"brick": 24, "wood": 8, "glass": 6, "iron": 2}, 140,
           (("design", "two_storey_house"), ("recipe", "iron"), ("design", "town_hall")), size=(2, 2),
           blurb="a tall brick block of flats: a home for up to 12 on the ground of one house (a crowded two-storey "
                 "house can be rebuilt as one)"),
        # cities: what only a city can raise (the build itself checks), and a harbour for a town on the coast
        _d("university", "university", {"brick": 30, "stone": 20, "glass": 6, "paper": 8}, 160,
           (("design", "library"), ("recipe", "paper"), ("design", "town_hall")), size=(3, 3),
           blurb="a city's university: grown-ups within 20 tiles learn from each other what any of them has made "
                 "work, so what one knows doesn't die with them (only a city can build one)", decay=0.4),
        _d("theatre", "theatre", {"wood": 20, "brick": 12, "stone": 8, "glass": 2}, 120,
           (("design", "town_hall"), ("recipe", "glass")), size=(3, 2),
           blurb="a city's theatre: a show every evening lifts the spirits of everyone within 15 tiles and brings them "
                 "together (only a city can build one)", decay=0.5),
        _d("harbour", "harbour", {"wood": 20, "stone": 12, "cord": 6}, 80, (("design", "boat"), ("design", "town_hall")),
           size=(2, 2), blurb="quays and fishing boats for a town by the water: fish caught within 12 tiles come in "
                              "twice as many"),
        # the Machine Age: what an engine, gears and paper are for (issue #12: after the forge nothing new stood)
        _d("steam_pump", "steam pump", {"brick": 8, "steel": 2, "engine": 1}, 60, (("recipe", "engine"), ("design", "well")),
           size=(2, 2), blurb="an engine that lifts water to the fields: farms within 10 tiles grow half as fast again, "
                              "even through a drought"),
        _d("sawmill", "sawmill", {"brick": 6, "steel": 2, "engine": 1, "wood": 8}, 60, (("recipe", "engine"),), size=(2, 2),
           blurb="an engine-driven saw: every log cut within 12 tiles gives twice the wood"),
        _d("printing_press", "printing press", {"wood": 6, "iron": 2, "gear": 2, "paper": 4}, 50,
           (("recipe", "gear"), ("recipe", "paper"), ("design", "library")), size=(2, 2),
           blurb="type and a press: each day it prints, on a sheet of paper from the stores, a recipe only one or two "
                 "chits still know, and shelves it in the nearest library"),
        # the Electric Age
        _d("power_station", "power station", {"brick": 16, "steel": 4, "dynamo": 1, "wire": 4}, 90, (("recipe", "dynamo"),),
           size=(2, 2), blurb="humming dynamos: work at every workshop, kiln, furnace, forge, mill and factory within "
                              "20 tiles goes half as fast again"),
        _d("street_lamp", "street lamp", {"iron": 1, "lightbulb": 1, "wire": 1}, 10, (("recipe", "lightbulb"),),
           blurb="an electric light on an iron post: no wolf bites anyone within 6 tiles of it", decay=1.0),
    ]
}

STARTING_DESIGNS: Tuple[str, ...] = ("campfire", "hut")

# Which resource a tile yields and what (if any) tool is required / helps.
GATHER_RULES: Dict[str, Dict[str, object]] = {
    "wood": {"tool": "axe", "requires": False, "work": 5},
    "stone": {"tool": "pick", "requires": False, "work": 6},
    "ore": {"tool": "pick", "requires": True, "work": 8},
    "iron_ore": {"tool": "pick", "requires": True, "work": 8},
    "fiber": {"tool": None, "requires": False, "work": 3},
    "berries": {"tool": None, "requires": False, "work": 3},
    "clay": {"tool": None, "requires": False, "work": 4},
    "sand": {"tool": None, "requires": False, "work": 3},
    "fish": {"tool": "spear", "requires": True, "work": 7},
    "seeds": {"tool": None, "requires": False, "work": 4},
}

GATHERABLE = tuple(GATHER_RULES.keys())


def item_name(key: str, catalog: "Optional[Catalog]" = None) -> str:
    it = catalog.item(key) if catalog is not None else ITEMS.get(key)
    return it.name if it else key.replace("_", " ")


_VALUE: Dict[str, float] = {}


def base_value(key: str) -> float:
    """What a thing is worth, roughly: raw goods ~1, crafted goods the value of their inputs x1.5 (T25)."""
    if key in _VALUE:
        return _VALUE[key]
    if key in GATHER_RULES:
        v = {"ore": 2.0, "iron_ore": 2.0, "fish": 1.5}.get(key, 1.0)
    elif key in RECIPES:
        r = RECIPES[key]
        _VALUE[key] = 1.0  # guard against cycles while computing
        v = sum(base_value(i) * n for i, n in r.inputs) / r.qty * 1.5 + (0.5 if r.station else 0.0)
    else:
        v = 1.0
    _VALUE[key] = v
    return v


class Catalog:
    """One world's view of the item and recipe tables: its own inventions first, then the shared base physics.
    Inventions (T20) never leak into ITEMS/RECIPES, so another world simply cannot see them."""

    def __init__(self) -> None:
        self.items: Dict[str, Item] = {}
        self.recipes: Dict[str, Recipe] = {}
        # a content pack's items and recipes (sim/packs.py): part of this world's physics from tick 0, found by
        # experiment like the base recipes. Empty without a pack, and then every lookup below is the base one.
        self.pack_items: Dict[str, Item] = {}
        self.pack_recipes: Dict[str, Recipe] = {}
        self._pack_value: Dict[str, float] = {}

    def item(self, key: str) -> Optional[Item]:
        return self.items.get(key) or ITEMS.get(key) or self.pack_items.get(key)

    def recipe(self, key: str) -> Optional[Recipe]:
        return self.recipes.get(key) or RECIPES.get(key) or self.pack_recipes.get(key)

    def match(self, bag: Dict[str, int], station: Optional[str]) -> Optional[Recipe]:
        """What an experiment with `bag` at `station` makes in this world: the base physics, then the pack's.
        (Inventions are not found by experiment: they are made by the invent action.)"""
        r = match_recipe(bag, station)
        if r is None and self.pack_recipes:
            key = frozenset((k, v) for k, v in bag.items() if v > 0)
            for p in self.pack_recipes.values():
                if p.input_bag == key and (p.station is None or p.station == station):
                    return p
        return r

    def physics(self) -> List[Recipe]:
        """Every recipe an experiment can find here: the base ones, then the pack's."""
        return list(RECIPES.values()) + list(self.pack_recipes.values())

    def pack_key(self, raw: object) -> Optional[str]:
        """Free text -> one of the pack's items, by key or name ("honeycomb", "Honeycombs", "a honeycomb")."""
        if not self.pack_items or raw is None:
            return None
        s = " ".join(str(raw).strip().lower().replace("-", " ").replace("_", " ").split())
        for p in ("a ", "an ", "the "):
            if s.startswith(p) and s[len(p):]:
                s = s[len(p):]
        for cand in (s, s[:-1] if s.endswith("s") else s):
            for k, it in self.pack_items.items():
                if cand in (k.replace("_", " "), it.name.replace("-", " ")):
                    return k
        return None

    def value(self, key: str) -> float:
        """What a thing is worth in this world: base_value, with the pack's items worked out from their recipes the
        same way (kept here, so a pack never writes into the shared table)."""
        r = self.pack_recipes.get(key)
        if r is None or key in ITEMS:
            return base_value(key)
        if key not in self._pack_value:
            self._pack_value[key] = 1.0  # guard against cycles while computing
            self._pack_value[key] = (sum(self.value(i) * n for i, n in r.inputs) / r.qty * 1.5
                                     + (0.5 if r.station else 0.0))
        return self._pack_value[key]

    def describe(self, r: Recipe) -> str:
        parts = " + ".join(f"{n} {item_name(k, self)}" if n > 1 else item_name(k, self) for k, n in r.inputs)
        at = f" at a {r.station}" if r.station else ""
        return f"{parts}{at} -> {item_name(r.key, self)}"


BASE = Catalog()  # the base tables, for code with no world at hand


def normalize_item(raw: object) -> Optional[str]:
    """Map free-form model text ('Stone Axe', 'axes', 'copper-ore') to an item key."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("-", " ").replace("_", " ")
    if not s:
        return None
    aliases = {
        "logs": "wood", "log": "wood", "timber": "wood", "sticks": "wood", "stick": "wood", "branch": "wood",
        "rock": "stone", "rocks": "stone", "stones": "stone", "pebble": "stone", "flint": "stone",
        "fibre": "fiber", "fibers": "fiber", "grass": "fiber", "plant fibre": "fiber", "reeds": "fiber",
        "berry": "berries", "food": "berries", "fruit": "berries",
        "copper ore": "ore", "ores": "ore", "metal ore": "ore", "iron ore": "iron_ore", "iron ores": "iron_ore",
        "seed": "seeds", "wheat": "grain", "rope": "cord", "string": "cord", "twine": "cord",
        "blade": "sharp_stone", "flake": "sharp_stone", "stone blade": "sharp_stone", "sharp stones": "sharp_stone",
        "axe": "stone_axe", "pick": "stone_pick", "pickaxe": "stone_pick", "stone pickaxe": "stone_pick",
        "bricks": "brick", "tablet": "clay_tablet", "tablets": "clay_tablet", "pots": "pot", "clay pot": "pot",
        "alien ship": "alien_ship", "spaceship": "alien_ship", "ufo": "alien_ship", "bible": "holy_book", "book": "holy_book",
        "fishes": "fish", "cooked fish": "cooked_fish", "tart": "berry_tart", "pie": "berry_tart",
    }
    if s in aliases:
        return aliases[s]
    key = s.replace(" ", "_")
    if key in ITEMS:
        return key
    for k, it in ITEMS.items():
        if it.name == s:
            return k
    if key.endswith("s") and key[:-1] in ITEMS:
        return key[:-1]
    return None


def normalize_design(raw: object) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("-", " ").replace("_", " ")
    aliases = {
        "fire": "campfire", "camp fire": "campfire", "bonfire": "campfire", "fire pit": "campfire",
        "shelter": "hut", "house": "hut", "home": "hut", "cabin": "hut",
        "storage": "stockpile", "store": "stockpile", "storehouse": "warehouse", "depot": "warehouse",
        "farm plot": "farm", "field": "farm", "garden": "farm", "workbench": "workshop",
        "oven": "kiln", "smelter": "furnace", "path": "road", "rocket": "launch_pad", "launch pad": "launch_pad",
        "spaceport": "launch_pad", "works": "factory",
        "brick home": "brick_house", "statue": "monument", "archive": "library",
        "long house": "longhouse", "hall": "longhouse", "great hall": "longhouse",
        "two story house": "two_storey_house", "two storey": "two_storey_house", "two story": "two_storey_house",
        "townhouse": "two_storey_house", "tall house": "two_storey_house",
        "footbridge": "bridge", "barn": "granary", "grain store": "granary", "windmill": "mill",
        "millstone": "mill", "smith": "smithy", "blacksmith": "smithy", "anvil": "smithy", "tower": "watchtower",
        "lookout": "watchtower", "watch tower": "watchtower", "schoolhouse": "school", "bell": "bell_tower",
        "belltower": "bell_tower", "bell tower": "bell_tower",
    }
    if s in aliases:
        return aliases[s]
    key = s.replace(" ", "_")
    return key if key in DESIGNS else None


def all_knowledge_keys() -> List[str]:
    return [f"recipe:{k}" for k in RECIPES] + [f"design:{k}" for k in DESIGNS]
