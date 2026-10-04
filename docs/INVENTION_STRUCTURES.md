# Inventions that are buildings: why they are not built yet, and what it would take

F34 (Invention 2.0) stage 3 has two halves. The first is done: `invent` honours an optional `"at"` station, some
rules of `sim/invent.py` need one, and an invention made that way needs the station to be made again
(`tests/test_invent_stations.py`). The second half, an invention that is a **structure** (a world-local design with a
size and one effect), is **not built**. This note says why, and lists what would have to change.

## Why not

A world-local *item* is cheap because of T20: every item lookup already goes through `world.item()` /
`world.catalog`, so an invention is one more entry in one world's catalogue and no other world can see it.

Designs never got that treatment. `items.DESIGNS` is a module-level table that code indexes directly, and a
building's behaviour is not in its `Design` entry at all: it is spread over tables and `if` tests keyed by the
design's **name** (`buildings.HOME_CAP`, `WARM_HOMES`, `EFFECT_RADIUS`, `REUSE_WITHIN`, `actions.STORE_CAP`,
`Structure.stations()`, `structures_near(x, y, r, "well")`, ...). `sim/packs.py` left designs out of content packs
for the same reason.

There are two ways to add an invented design, and neither is sound as a side effect of this change:

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

**138** occurrences in 21 files. Each must become `world.design(key)` (and each needs a `world` in scope; `agent.py`,
`story/*` and the module-level tables do not have one).

| file (under `server/chits/`) | occurrences | lines |
|---|---|---|
| `app.py` | 1 | 167 |
| `brain/builder.py` | 10 | 64, 71, 81, 101, 102, 143, 195, 206, 212, 255 |
| `brain/civic.py` | 5 | 59, 68, 114, 174, 385 |
| `brain/instinct.py` | 21 | 568, 578, 603, 670, 692, 710, 724, 725, 733, 741, 752, 819, 820, 856, 903, 920, 1028, 1034, 1065 |
| `brain/outposts.py` | 1 | 68 |
| `brain/pioneers.py` | 1 | 30 |
| `brain/prompt.py` | 8 | 366, 381, 382, 456, 687, 705 |
| `brain/surplus.py` | 1 | 137 |
| `brain/voyages.py` | 1 | 67 |
| `diag.py` | 2 | 482, 564 |
| `runtime.py` | 1 | 1052 |
| `sim/actions.py` | 29 | 614, 801, 1065, 1159, 1279, 1313, 1314, 1336, 1355, 1602, 1958, 2155, 2178, 2206, 2208, 2210, 2212, 2221, 2234, 2293, 2323, 2695, 2697, 2852, 2856, 3239 |
| `sim/agent.py` | 1 | 373 |
| `sim/buildings.py` | 19 | 169, 170, 186, 199, 205, 206, 208, 260, 261, 270, 272, 277, 279, 281, 352, 366, 379, 504, 1023 |
| `sim/hall.py` | 1 | 30 |
| `sim/projects.py` | 15 | 245, 416, 523, 536, 646, 670, 679, 683, 685, 940, 985, 995, 999, 1006, 1057 |
| `sim/wants.py` | 1 | 89 |
| `sim/world.py` | 8 | 176, 889, 1299, 1331, 1348, 1473, 1661, 1665 |
| `story/divergence.py` | 1 | 29 |
| `story/recap.py` | 2 | 44, 74 |
| `views.py` | 9 | 16, 38, 57, 134, 158, 283, 291, 342 |

(Line numbers are those of the commit that added this note; `grep -n 'DESIGNS\[' -r server/chits` gives today's.)

### 2. Other reads of the shared table

Membership, iteration and `.get`: `story/recap.py` 43, `diag.py` 211 and 559, `sim/projects.py` 481, 645 and 681,
`sim/actions.py` 1152 and 2571 (`_knowledge_key`: what `teach` and `write` accept), `sim/hall.py` 29,
`sim/world.py` 1476 (`design_prereqs_met` over every design, each tick a chit learns), `lab/treatment.py` 96,
`views.py` 276, `brain/civic.py` 171, `brain/instinct.py` 1031, `sim/packs.py` 145 and 303, and
`items.all_knowledge_keys()` / `items.normalize_design()` (13 call sites of `normalize_design`), which the plan's
locked tests pin to the base tables.

### 3. Behaviour keyed by the design's name

This is the larger problem. A `Design` entry only says what a building costs. What it *does* is decided by its name:

- 135 comparisons of the form `s.design == "..."` / `s.design in (...)` across `server/chits/`.
- 64 calls of `structures_near(x, y, r, "<design>")`.
- The name-keyed tables: `buildings.HOME_CAP`, `WARM_HOMES`, `REUSE_WITHIN`, `EFFECT_RADIUS`, `_FX`, `CITY_ONLY`,
  `TOWN_CENTRE`, `POWERED`, `REUSE_CAPPED`, `GREAT_WORKS`, `UPGRADES`; `actions.STORE_CAP`; `items.STORES`,
  `HOME_STORES`, `LIBRARIES`; `settlements.CIVIC`; and `Structure.stations()` (`sim/world.py` 169), which
  special-cases the campfire and the kiln by name.

An invented "storehouse" would have to be recognised as a store by every one of those `in STORES` tests, an invented
"shelter" as a home by `HOME_CAP` and `in_home`, an invented "oven" as a station by `stations()`. So an invented
design cannot carry its effect by name. It needs an **effect field**.

### 4. Outside the simulator

- The web client paints buildings by design key (`web/src/render/buildings.ts`, `PAINTERS[design]`; `WorldView.ts`
  reads `design` 31 times). An unknown key needs a generic painter and a size from the snapshot.
- `views.structure_view`, `views.encyclopedia` (the design branch), `/api/knowledge` and the Knowledge tab list
  designs from `DESIGNS`.
- Saves: `world.to_dict` would have to persist the invented designs and `from_dict` re-register them before any
  structure is restored (a structure of an unknown design is a `KeyError` in `Structure` helpers).
- `tests/test_review_step2a.py::test_every_design_has_a_planner_that_can_choose_it` requires every design to have a
  planner. Invented designs would be model-only (`MODEL_ONLY` there is empty today, on purpose).

## The shape of a sound version

1. `Catalog.designs` and `Catalog.design(key)` (world-local first, then `DESIGNS`), `World.design()`, and a mechanical
   pass replacing the 137 direct indexes. No behaviour change; one PR; the whole suite is its test.
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

3. Only then the invention rule: a purpose that names shelter, store, heat, water or watch, and a bag that is
   building-scale. `invent` takes at most 4 pieces and `_experiment_bag` at most 6, so "at least N material units"
   needs a second input path (materials delivered to a site, as `build` does), not a bigger bag. The strength of
   the effect would come from the same material table as items (`invent.strength`).
4. A generic painter in the web client, the save fields, and a line in the guide.

Until step 1 is done, `invent` makes items only, and a purpose like "a shelter" is judged as an item (it is refused
unless the parts can do something an item can do, and the feedback says what they could make).
