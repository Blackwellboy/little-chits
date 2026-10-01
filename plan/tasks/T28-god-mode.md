# T28 · God mode: drop anything, meddle, and save points

**Why:** half the fun of a sandbox is doing something silly and watching the fallout. Drop an alien spaceship in
the village, a holy book on the beach, a musket in the middle of the market, or a meteor on the library. Then see
what the chits make of it. Save points make it safe: save, meddle, and rewind if it goes wrong.

Everything still goes through the simulator. A dropped object has properties, and chits discover what it
does by picking it up, inspecting it and experimenting, exactly as with anything else.

## Build
1. **Ground items.**
   - `World.ground: Dict[str, Dict[str, int]]` maps a tile key `"x,y"` to items. Persist it, defaulting to `{}`.
   - `drop` now puts the items on the chit's tile instead of deleting them.
   - Piles older than 5 days vanish, except artifacts. Keep a per-pile `"_t"` tick in the same dict;
     `_t` is not an item, so pickup, scene and views ignore it.
   - When a pickup or artifact yields more than the chit can carry, the rest stays on that tile as a pile.
   - **Verb `pickup`**: `{"do":"pickup","what":"<item>"}` (the `what` is optional). It picks up from the
     chit's own tile, or walks to the nearest pile within 20 tiles holding that item, respecting capacity.
     - Aliases: `pick_up`, `grab`, `collect_item`, `loot`.
     - Picking up an artifact calls its `on_pickup` (below).
   - `scene()` lists piles within SIGHT: `- On the ground: 2 wood, 1 alien spaceship at (40,22)` (at most 4).
2. **Artifacts** (`server/chits/sim/artifacts.py`). These are registered as `Item`s in `ITEMS` with icon and
   props, have no recipe, and are never in `all_knowledge_keys`.

   | key | name | props | effect |
   |---|---|---|---|
   | meteorite | meteorite | heavy, scorched, metallic, fell from the sky | picking it up turns it into 10 ore |
   | alien_ship | alien spaceship | huge, humming, impossible metal, warm, glowing symbols | can't be picked up; `inspect` it (target `alien ship`) teaches one recipe nobody in this world knows yet (not in `world.first`, not `inv_`), picked with `world.rng`; once per chit per day |
   | holy_book | holy book | old, leather-bound, full of strange words | inspect: +10 mood; with T21, founds `The Book` for the first reader with no belief |
   | treasure_chest | treasure chest | heavy, locked, rattles | picking it up gives 8 random crafted items |
   | golden_idol | golden idol | gold, gleaming, a watching face | chits within 6 tiles gain +0.05 mood per tick |
   | musket | musket | tool, loud, smoky, dangerous | tool class `weapon`, power 3 (T27 fights) |
   | radio | radio | crackles, voices from nowhere, humming | inspect: like the ship, but at most once per world per day |
   | seed_vault | seed vault | cold, sealed, full of seeds | picking it up gives 30 seeds |
   | time_capsule | time capsule | sealed, old, humming faintly | picking it up places 3 clay tablets on the ground, each holding a recipe the world hasn't discovered |

   - `normalize_item` maps `alien ship`, `spaceship`, `ufo` → alien_ship, and `bible`, `book` → holy_book
     (keep the existing `tablet` aliases).
   - `inspect` on an artifact in the chit's inventory, or on a pile within 2 tiles, triggers its inspect
     effect.
   - Emit `"revelation"`, importance 5, whenever an artifact teaches something:
     `{name} studied the {artifact} and understood how to make {item}`.
3. **God actions:** `POST /api/worlds/{wid}/god` with `{"action", "x", "y", "item", "qty"}`. Every action emits a
   `"miracle"` event (importance 5), and returns `{"ok": true, "event": text}`.
   - `drop`: put `qty` (default 1) of any `ITEMS` key or artifact on `(x,y)`. Text:
     `A {name} appeared out of nowhere at ({x},{y})!`
   - `meteor`: drop a meteorite, and every structure within 1 tile loses 50 durability. Text:
     `A meteor crashed down at ({x},{y})!`
   - `bless`: every chit within 8 tiles gets full hunger, warmth and health. Text: `A warm light blessed the chits
     near ({x},{y})`
   - `smite`: chits within 1 tile lose 30 health (never below 5), structures within 1 tile lose 40 durability,
     and a campfire there is lit. Text: `Lightning struck at ({x},{y})!`
   - `feast`: drop 30 bread.
   - `plague`: a random 20% of chits (`world.rng`) lose 30 health (never below 5). Text: `A sickness spreads
     through {world name}`
   - `storm` / `drought` / `snow`: T08's `set_weather`, if it exists, else 400.

   Unknown actions, unknown items or out-of-map coordinates → 400.
4. **Save points.**
   - Store table `savepoints(id INTEGER PRIMARY KEY, name TEXT, created REAL, tick INTEGER, data TEXT)`.
   - `POST /api/savepoints {"name"}` saves `{wid: world.to_dict()}` for every world and returns `{id, name, tick}`.
   - `GET /api/savepoints` lists them, newest first, without `data`.
   - `POST /api/savepoints/{id}/restore` rebuilds every world with `World.from_dict`, reattaches listeners and
     brains exactly as startup does, broadcasts fresh snapshots, and returns `{"ok": true}`.
   - `DELETE /api/savepoints/{id}`.
5. **Web.**
   - A 🪄 **God** button in the top bar opens a palette. It has tabs for Artifacts, Items (all `ITEMS`,
     searchable) and Acts (meteor, bless, smite, feast, plague, storm…).
   - Pick one, then click the map to target it. The canvas shows a crosshair while a god tool is armed, and
     Esc cancels.
   - A 💾 button saves a named save point and lists save points with Restore and Delete.
   - Ground piles and artifacts are drawn with their icons.
6. **Moments (T11):** `miracle` 90, `revelation` 94.

**Integrity (added after review):**
- Every god action and every save-point restore calls `Runtime.mark_sandbox(reason)` (F1). In an
  `experiment` run they are refused with 409.
- A restore calls `world.fork_epoch("restored save point <name>")` (F3), so replays and the chronicle never
  splice two futures.
- See `plan/acceptance/test_t28b_integrity.py`.

## Done when
`python scripts/plan.py verify T28` passes.
