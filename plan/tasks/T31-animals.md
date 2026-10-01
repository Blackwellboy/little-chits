# T31 · Animals: deer to hunt, sheep to tame, wolves in the dark

**Why:** a living island has other living things. Hunting gives a second food chain, taming sheep gives wool,
cloth and warm cloaks (and a reason to build pens), and wolves on winter nights make fire and shelter matter
for real.

## Build
1. **State.** `World.animals: Dict[str, dict]`, keyed by `_new_id("animal")`. Each value is
   `{"id","kind","x","y","hp","tame","pen"}`. Persist it, defaulting to `{}`.
2. **Spawning** (in `World.__init__` for new worlds, and daily in `_new_day`):
   - deer: `max(2, w*h // 1500)`, on grass or forest tiles
   - sheep: `max(1, w*h // 3000)`, on grass
   - wolves: 0 in spring and summer; in autumn and winter, up to `max(1, w*h // 6000)`, spawned on forest
     tiles at least 15 tiles from every chit
   - Daily, if wild deer or sheep are below half their target, add 10% of the target (at least 1).
   - Wolves leave (are removed) when spring starts.
3. **Movement** every 4 ticks (use `self.rng`):
   - Wild deer and sheep take a random step. Deer step *away* from any chit within 3 tiles.
   - Tame sheep random-walk inside their pen's cells.
   - Wolves at night step toward the nearest chit within 10 tiles, unless that chit or the wolf is within 4
     tiles of a lit campfire; in that case they step away. By day, wolves random-walk.
4. **Wolf attacks.** At night, a wolf within 1 tile of a chit that is not `in_home` attacks: every 10 ticks
   the chit loses 6 health. Attacks never kill; health stays above 10.
   - Emit `"wolf"`, importance 3, once per chit per night: `A wolf attacked {name} in the dark!`. The chit
     also gets a memory.
5. **Items and recipes.**
   - `meat`: edible, raw, bloody; food 25.
   - `cooked_meat`: edible, hot, filling; food 50. Recipe: `meat` at a fire.
   - `wool`: soft, warm, fluffy.
   - `cloth`: soft, woven, warm. Recipe: 2 wool at a workshop.
   - `cloak`: wearable, warm, soft. Recipe: 2 cloth + cord at a workshop.
   - Carrying an item with both `wearable` and `warm` halves cold warmth loss.
6. **Verb `hunt`**: `{"do":"hunt","what":"deer|wolf"}`, with alias `chase`.
   - It needs a spear or a `weapon` tool; otherwise fail with a message containing `spear`.
   - Approach the nearest animal of that kind within 20 tiles. Each attempt takes 6 ticks and succeeds with
     probability `0.35 + 0.15 × best tool power` (`world.rng`), for at most 8 attempts.
   - Deer give 3 meat. Wolves give nothing but are removed.
   - Emit `"hunt"`, importance 2 (3 for a wolf).
7. **Pens and taming.**
   - Design `pen`: `{"wood": 6, "cord": 2}`, work 20, size 2×2, prereq `("recipe","cord")`, blurb
     `a fenced pen for tame animals`.
   - Pens have `storage` like a stockpile, and `take` works on them.
   - **Verb `tame`**: `{"do":"tame"}`.
     - It needs grain or berries, and a functional pen within 12 tiles.
     - Approach a wild sheep within 15 tiles, spend 1 grain/berries, and succeed with probability 0.5 (up to 4
       tries).
     - On success, set `tame=True`, `pen=<pen id>`, and move the sheep into the pen.
     - Emit `"tamed"`, importance 3 (4 for the world's first: `{name} tamed the first sheep`).
   - Daily, each tame sheep adds 1 wool to its pen's storage.
8. **Prompt, transport and web.**
   - `scene()` lists animals within SIGHT on one line: `- Animals: 2 deer N, a sheep E, a WOLF 4 tiles W!`.
   - `verb_guide` gains `hunt` and `tame`.
   - `views.snapshot` includes `animals`. `Runtime.frame` includes animals (compact `[id, kind, x, y, tame]`)
     every 4 ticks.
   - Web: small procedural sprites for deer, sheep and wolf (wolves with glowing eyes at night).
9. **Instinct.**
   - Hunt when hungry, holding a spear, with a deer within 12 tiles and no berries.
   - Tame a sheep when a pen exists and the chit has grain.
   - Build a pen once cord is known and wild sheep are near.

## Done when
`python scripts/plan.py verify T31` passes.
