# Inventions that are buildings: built as variants, and what a world-local design would still take

F34 (Invention 2.0) stage 3 has two halves. The first is done: `invent` honours an optional `"at"` station, some
rules of `sim/invent.py` need one, and an invention made that way needs the station to be made again
(`tests/test_invent_stations.py`). The second half, an invention that is a **structure**, is now built **as a
variant** of a design the world already has (`sim/ideas.py`, `tests/test_invented_buildings.py`). A fully world-local
design (a new size, a new effect) is still **not built**; this note says why, and lists what it would take.

## What is built: an invented building is a named variant

An invention whose name ends in a building ("Wind Hall", "Ash's Tower") or whose purpose starts with one ("a granary
for...") is a **building idea**, kept in `world.building_ideas` (saved only when there is one, so other saves are
unchanged). Keyword rules on its name and purpose choose what it is for (shelter, storage, warmth, food, learning,
worship, defence, trade, making, light), and that chooses its **base**: the most advanced design of that kind that
somebody in this world already knows (shelter: two-storey house, brick house, longhouse, then hut; a shrine only where
the world has religion). If no kind it names has a known base, it is judged as an item, as before.

- Its parts must be building materials. They say what it is built from, scaled up until it takes at least as many
  pieces as the base; a base material none of them is (a brick house's bricks) is still needed. Never cheaper.
- The inventor learns `idea:<key>`. Teaching, writing and reading pass it on like any other knowledge, and whoever
  helps build one learns it. The parts are kept: they were only the model of it.
- `build` takes the idea's name (or key) from a chit that knows it. The structure it puts up has the **base's**
  design, so every rule keyed by a design's name (homes, stores, stations, radii, upkeep, ages) treats it as that
  building, unchanged. Two optional structure fields, `idea` and `title`, say what it is; the site needs the idea's
  materials. Its completion says "Ash built the first Wind Hall, Rible's idea".
- Model prompts list the ideas a chit knows among what it can build, by name (what it is a kind of only when the chit
  knows that building too). Instinct never invents, but a chit that knows an idea builds it in place of its base one
  time in two when it carries enough for both (`ideas.INSTINCT_SHARE`, by a hash: nothing random is drawn).
- The map draws the base's sprite a shade warmer with a pennant on the roof, its name on hover and in the inspector;
  the Knowledge panel lists each world's building ideas with their inventors.
- `ideas.INVENTED_BUILDINGS` switches it off (`tests/identity_runner.py` does). Nothing is ever added to `DESIGNS`.

## Why a world-local design is still not built

A world-local *item* is cheap because of T20: every item lookup already goes through `world.item()` /
`world.catalog`, so an invention is one more entry in one world's catalogue and no other world can see it.

Designs never got that treatment. `items.DESIGNS` is a module-level table that code indexes directly, and a
building's behaviour is not in its `Design` entry at all: it is spread over tables and `if` tests keyed by the
design's **name** (`buildings.HOME_CAP`, `WARM_HOMES`, `EFFECT_RADIUS`, `REUSE_WITHIN`, `actions.STORE_CAP`,
`Structure.stations()`, `structures_near(x, y, r, "well")`, ...). `sim/packs.py` left designs out of content packs
for the same reason. A variant sidesteps all of that by being its base; a building that does something no base does
cannot.

There are two ways to add a new design, and neither is sound as a side effect of a feature:

1. **Put it in `DESIGNS`.** Twin worlds share that table, so World A's invented building would exist in World B.
   That breaks the invariant that the worlds differ only by culture flags, and T20's rule that inventions never leak
   into the shared tables. Not acceptable.
2. **Route every design lookup through the catalogue** (`world.design(key)`), as T20 did for items. That is the
   right change, but it is a refactor of the whole simulator and both brains, not a feature: the counts are below.
   Done partly, it fails in the worst way: a structure whose design one code path cannot find raises `KeyError`
   inside the world tick (`DESIGNS[st.design]` is the idiom everywhere), which stops a world.

## Every lookup site that would have to change

Counted on this branch by `tests/test_invent_stations.py` (the test fails if the numbers here go stale).

### 1. Direct indexing of the shared table: `DESIGNS[...]`

**153** occurrences in 22 files. Each must become `world.design(key)` (and each needs a `world` in scope; `agent.py`,
`story/*` and the module-level tables do not have one).

| file (under `server/chits/`) | occurrences | lines |
|---|---|---|
| `app.py` | 2 | 167, 216 |
| `brain/builder.py` | 12 | 64, 71, 83, 103, 104, 145, 260, 393, 408, 414, 470, 477 |
| `brain/civic.py` | 5 | 59, 68, 114, 174, 385 |
| `brain/instinct.py` | 22 | 547, 809, 819, 848, 915, 937, 956, 970, 971, 979, 987, 998, 1065, 1066, 1102, 1149, 1166, 1274, 1280, 1311 |
| `brain/outposts.py` | 1 | 68 |
| `brain/pioneers.py` | 1 | 30 |
| `brain/prompt.py` | 7 | 417, 418, 493, 736, 755 |
| `brain/surplus.py` | 1 | 139 |
| `brain/voyages.py` | 1 | 67 |
| `diag.py` | 2 | 580, 662 |
| `runtime.py` | 1 | 1154 |
| `sim/actions.py` | 33 | 792, 1005, 1270, 1364, 1484, 1518, 1519, 1541, 1560, 1698, 1836, 1906, 2219, 2443, 2459, 2495, 2530, 2532, 2534, 2536, 2548, 2643, 2710, 3136, 3139, 3141, 3296, 3300, 3714, 3732 |
| `sim/agent.py` | 1 | 374 |
| `sim/buildings.py` | 21 | 183, 184, 200, 213, 219, 220, 222, 274, 275, 287, 289, 294, 296, 298, 369, 384, 397, 522, 965, 966, 1063 |
| `sim/hall.py` | 1 | 30 |
| `sim/ideas.py` | 5 | 112, 113, 183, 203, 229 |
| `sim/projects.py` | 15 | 245, 417, 524, 537, 647, 671, 680, 684, 686, 941, 986, 996, 1000, 1007, 1058 |
| `sim/wants.py` | 1 | 89 |
| `sim/world.py` | 8 | 254, 1055, 1488, 1517, 1534, 1677, 1868, 1872 |
| `story/divergence.py` | 1 | 29 |
| `story/recap.py` | 2 | 44, 74 |
| `views.py` | 10 | 18, 44, 49, 73, 152, 176, 302, 310, 361 |

(Line numbers are those of the commit that last changed this table; `grep -n 'DESIGNS\[' -r server/chits` gives today's.
`sim/ideas.py` is the variants' own module: it reads the base's entry, which is always in the shared table.)

### 2. Other reads of the shared table

Membership, iteration and `.get`: `story/recap.py` 43, `diag.py` 211 and 559, `sim/projects.py` 481, 645 and 681,
`sim/actions.py` 1152 and 2571 (`_knowledge_key`: what `teach` and `write` accept), `sim/hall.py` 29,
`sim/world.py` 1476 (`design_prereqs_met` over every design, each tick a chit learns), `lab/treatment.py` 96,
`views.py` 276, `brain/civic.py` 171, `brain/instinct.py` 1031, `sim/packs.py` 145 and 303, and
`items.all_knowledge_keys()` / `items.normalize_design()` (13 call sites of `normalize_design`), which the plan's
locked tests pin to the base tables. (Line numbers as of the commit that added this note.)

### 3. Behaviour keyed by the design's name

This is the larger problem. A `Design` entry only says what a building costs. What it *does* is decided by its name:

- 135 comparisons of the form `s.design == "..."` / `s.design in (...)` across `server/chits/`.
- 64 calls of `structures_near(x, y, r, "<design>")`.
- The name-keyed tables: `buildings.HOME_CAP`, `WARM_HOMES`, `REUSE_WITHIN`, `EFFECT_RADIUS`, `_FX`, `CITY_ONLY`,
  `TOWN_CENTRE`, `POWERED`, `REUSE_CAPPED`, `GREAT_WORKS`, `UPGRADES`; `actions.STORE_CAP`; `items.STORES`,
  `HOME_STORES`, `LIBRARIES`; `settlements.CIVIC`; and `Structure.stations()` (`sim/world.py`), which
  special-cases the campfire and the kiln by name.

An invented "storehouse" would have to be recognised as a store by every one of those `in STORES` tests, an invented
"shelter" as a home by `HOME_CAP` and `in_home`, an invented "oven" as a station by `stations()`. So an invented
design cannot carry its effect by name. It needs an **effect field**. (A variant carries its base's name in
`Structure.design`, which is why it needs none of this.)

### 4. Outside the simulator

- The web client paints buildings by design key (`web/src/render/buildings.ts`, `PAINTERS[design]`; `WorldView.ts`
  reads `design` 31 times). An unknown key needs a generic painter and a size from the snapshot. (A variant is
  painted as its base.)
- `views.structure_view`, `views.encyclopedia` (the design branch), `/api/knowledge` and the Knowledge tab list
  designs from `DESIGNS`. (Variants have their own list: `/api/ideas`.)
- Saves: `world.to_dict` would have to persist the invented designs and `from_dict` re-register them before any
  structure is restored (a structure of an unknown design is a `KeyError` in `Structure` helpers). A variant's save
  is only its record and two optional structure fields; a save whose idea is lost still loads, as the base.
- `tests/test_review_step2a.py::test_every_design_has_a_planner_that_can_choose_it` requires every design to have a
  planner. Invented designs would be model-only (`MODEL_ONLY` there is empty today, on purpose).

## What a fully world-local design would still need

1. `Catalog.designs` and `Catalog.design(key)` (world-local first, then `DESIGNS`), `World.design()`, and a mechanical
   pass replacing the direct indexes above. No behaviour change; one PR; the whole suite is its test.
2. Add `Design.effect: Optional[Tuple[str, float]]` and make the name-keyed tables fall back to it, one effect at a
   time, each behind its own test. The short list the simulator already implements, and where each lives:

   | effect | today's owner | what an invented design would set |
   |---|---|---|
   | shelter (a home for N) | `buildings.HOME_CAP`, `world.in_home`, `WARM_HOMES` | capacity, warm or not |
   | store room | `items.STORES`, `actions.store_cap` | capacity |
   | a station | `Design.station`, `Structure.stations()` | one of `STATIONS` |
   | warmth radius | `world.near_fire` (campfire only, needs fuel) | radius |
   | growth bonus | `buildings.WELL_RADIUS` and the farm tick | radius, share |
   | watch radius | `buildings.TOWER_RADIUS`, `animals` | radius |

3. The invention rule is half there: `ideas.is_building` and `ideas.archetype` already tell a building from an item
   and say what it is for. A new design would take its effect from that purpose, its size from its materials, and
   its **strength** from the same material table as items (`invent.strength`), where a variant takes all three from
   its base. `invent` takes at most 4 pieces and `_experiment_bag` at most 6, which is why a variant's parts are
   scaled up rather than delivered: a design whose strength came from its materials would want them delivered to a
   site, as `build` does.
4. A generic painter in the web client, the save fields, and a line in the guide.

Until step 1 is done, an invented building can only be a variant: it does what its base does, and a purpose no known
base serves is judged as an item (it is refused unless the parts can do something an item can do, and the feedback
says what they could make).
