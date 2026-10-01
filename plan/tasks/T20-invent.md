# T20 · Open invention: each world grows its own tech tree

**Why:** today every world discovers the same fixed recipe table, so given enough time the twin worlds converge.
Real divergence needs chits that *imagine new things*. A chit proposes a name and a purpose, and the world
judges it by physical law (the items' properties). World A might invent a fishing net while World B invents
a sling, a drum and a fur-less "reed cloak". They give them different names, they spread differently, and
they are different civilisations.

The rule that keeps it honest: **cognition proposes, the simulator decides.** The model can't just declare
"I invented a laser". The inputs must have the properties the purpose needs.

## Build
1. **`server/chits/sim/invent.py`.**
   - `PURPOSES`: an ordered list of tuples `(purpose_id, keywords, required, effect)`.
     - `required` is a list of property sets.
     - Each set must be matched by at least one property of at least one input item. The same input may
       satisfy several sets.

     | purpose_id | keywords (substring match on the lowercased purpose text) | required property sets | effect |
     |---|---|---|---|
     | `fishing` | fish, catch, net, trap, hook | {stringy, binding, flexible} and {sturdy, long, pointed, sharp} | `{"tool": "spear", "tool_power": 1.2}` |
     | `cutting` | cut, chop, saw, blade, knife | {sharp} and {sturdy, long, hard} | `{"tool": "axe", "tool_power": 1.5}` |
     | `digging` | dig, mine, quarry, break rock, hoe | {hard, metal} and {sturdy, long} | `{"tool": "pick", "tool_power": 1.5}` |
     | `carrying` | carry, bag, sack, sling, pack, hold | {flexible, woven, stringy, container} | `{"carry_bonus": 5}` |
     | `warmth` | warm, cloak, coat, cloth, blanket, wrap | {flexible, soft, woven, strong} | `{"warmth": 0.5}` |
     | `light` | light, torch, lamp, glow | {flammable, burns very hot} and {sturdy, long, container, fired} | `{"tool": "light", "tool_power": 0.5}` |
     | `food` | eat, food, meal, stew, snack, dish | every input has `edible` (checked specially, see below) | `{"food": round(sum of input food × 1.15)}` |
     | `joy` | music, drum, flute, song, art, toy, ornament, jewel, decoration, paint, game | none | `{"mood": 8}` |

   - `judge(bag: Dict[str, int], purpose_text: str) -> Tuple[bool, Optional[str], dict, str]` returns
     `(ok, purpose_id, effect, feedback)`.
     - The bag must hold 2–4 items in total, with at most 3 distinct kinds. Otherwise `ok=False` and the
       feedback mentions `2` and `4`.
     - Choose the **first** purpose whose keyword appears in the lowercased purpose text. If none matches,
       return `(False, None, {}, feedback)`. The feedback must list the purposes the world understands, in
       plain words that include `catching fish`, `cutting`, `digging`, `carrying`, `keeping warm`, `light`,
       `food` and `joy`.
     - For `food`: every input item must have the `edible` property. Otherwise the feedback contains
       `edible`.
     - For other purposes: take the first required set that no input property matches. The feedback is
       `It didn't work for <purpose_id> — it seemed to need something <p1> or <p2>` (listing that set's
       properties, sorted, joined with ` or `).
     - On success: `(True, purpose_id, effect, "It works!")`.
     - Input properties come from `ITEMS[k].props`. Invented items are in `ITEMS` too (step 2), so inventions
       can build on inventions.
2. **World-local catalogue** (not the global tables). Base physics (`ITEMS`, `RECIPES`) stays immutable and
   shared. Inventions live only in their own world, so isolation is structural rather than something every
   lookup has to remember.
   - `World.catalog` is a `Catalog` (new, in `server/chits/sim/items.py`) with `item(key) -> Optional[Item]`
     and `recipe(key) -> Optional[Recipe]`. Both check the world's own entries first, then fall back to the
     base tables. `World.item()`/`World.recipe()` are shortcuts for these.
   - `register_invention(world, key, name, inputs, props, effect) -> Recipe` adds an `Item(key, name, props,
     food=…, tool=…, tool_power=…, carry_bonus=…, icon="💡")` and a `Recipe(key, inputs, None, 1, 8)` to
     **that world's** catalogue only.
   - Keys look like `inv_<world id lowercased>_<n>`.
   - Every agent gets a transient `a.catalog` pointing at its world's catalogue. It is set when the world
     creates, restores or receives an agent, and is not persisted. `Agent` methods that look up items
     (`capacity`, `load`, `add`, `best_tool`, …) use `self.catalog.item(k)` when it's set, else `ITEMS`.
   - Replace direct `ITEMS[...]`/`RECIPES[...]` lookups in `actions.py`, `world.py`, `prompt.py` and
     `views.py` with `world.item(...)`/`world.recipe(...)` wherever an invention key could appear.
   - `match_recipe` and `all_knowledge_keys()` only ever see the base tables.
   - The props of the new item are `("invented", "for " + purpose_id)` plus up to 3 of the inputs'
     properties: the input keys sorted, each item's props in order, de-duplicated, first 3.
   - **Wording:** this is invention *within authored affordances*. A model picks the inputs, the name and
     the purpose; the world judges it against a fixed list of purposes. A future task can replace the purpose
     buckets with composable affordances (material + shape + mechanism).
3. **Verb `invent`.**
   - Step shape: `{"do":"invent","with":["fiber","fiber","wood"],"name":"Fishnet","purpose":"catch fish"}`.
   - Remove the old alias `invent → experiment`. Add aliases `devise`, `innovate` and `imagine` → `invent`.
   - In `parse.normalize_step`, for `invent`: keep `with` (list; `what`/`items`/`ingredients` map to it like
     experiment), `name` (and `call`/`called`) and `purpose` (also from `for`, `use`, `goal`).
   - `_do_invent(world, a, step, s)`:
     - Build the bag with `_experiment_bag`. Any unknown item → failure (`aren't real items`). Not carrying
       the bag → failure (`not carrying`).
     - `name = sanitize_name(step name)` (T05). Missing → failure containing `name`.
     - Work 10 ticks (`_work(a, a.skill_speed("crafting"), 10.0)`), activity `"inventing"`, emote 💡.
     - Call `judge`. On failure: consume **nothing**, `a.remember(...)` the feedback (importance 3), and fail
       with the feedback. The honest feedback is what a good model learns from.
     - On success:
       - If this world already has an invention with the **same purpose and the same bag**, re-use it: learn
         it with `world.learned(a, "recipe:<key>", "discovered")`, consume the inputs, give 1 of the item,
         and return `DONE`. No new invention is created.
       - Otherwise, create it:
         - `key = f"inv_{world.id.lower()}_{len(world.inventions) + 1}"`
         - `register_invention(...)`
         - store `world.inventions[key] = {"key","name","inputs","purpose","purpose_text","effect","props","by","by_name","tick"}`
         - consume the inputs and give 1 of the new item
         - `world.learned(a, "recipe:" + key, "discovered")`
         - emit `"invention"`, importance 5, text `{a.name} invented the {name} ({purpose_id}) from {inputs in words} — nothing like it exists anywhere else`,
           data `{"key", "name", "purpose", "inputs"}`
         - `a.bump("inventions")`
       - Note `s["note"] = f"Invented the {name}"`.
   - Allowed in **both** cultures.
4. **Using inventions.**
   - `craft` accepts an invention by key, or by its name in *this* world (case-insensitive), through a new
     `World.invention_by_name(text) -> Optional[str]`. The same lookup is used by `teach`, `write`, `give`,
     `drop`, `store` and `take` wherever an item or knowledge name is resolved. Resolve with the world lookup
     first, then fall back to `normalize_item` / `_knowledge_key`.
   - A `warmth` effect: while the chit carries the item, weather/cold warmth loss is multiplied by `0.5`.
   - A `mood` effect: while carried, `+0.02` mood per tick (clamped as usual).
   - `learned()` names invention recipes with their local name (`world.item(key).name`).
5. **Persistence.** `to_dict` includes `inventions`. `from_dict` restores it (default `{}`) **and rebuilds
   the world's catalogue from it**, so a restarted server knows the items again.
6. **Prompt.**
   - `verb_guide` gains:
     `{"do":"invent","with":["item","item"],"name":"<your name for it>","purpose":"<what it is for>"}  (imagine something new from 2-4 carried items; the world decides if their properties suit the purpose)`
   - `scene()` lists the world's inventions this chit knows on one line:
     `- Inventions you know: Fishnet (2 plant fiber + wood, for fishing); …` (at most 6).
7. **Views and web.**
   - `views.snapshot` includes `"inventions": list(world.inventions.values())`.
   - The Knowledge tab gets an **Inventions** section per world: name, purpose, inventor and day.
8. Moments (T11): add the `invention` event kind with score 92.

## Done when
`python scripts/plan.py verify T20` passes. 🖐 Then run a model for a few in-game days and check that the
inventions are ones *it* came up with.
