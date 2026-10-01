# T27 · Rivalry, theft and the first guards

**Why:** scarcity makes conflict, and conflict makes institutions. A hungry chit steals from a stockpile. The
owners post a guard. Four guards become the island's first militia. Keeping it lawful and non-lethal makes it
interesting rather than grim: chits get hurt and hold grudges, but nobody is killed in a fight.

## Build
1. **Verb `steal`** (both worlds): `{"do":"steal","target":"<stockpile id>","what":"<item>","qty":3}` takes up to
   3 (at most `qty`) of an item from a stockpile.
   - Aliases: `rob`, `pilfer`, `raid`.
   - Stealing from a stockpile the chit founded is just `take`; fail with a message containing `own`.
   - Walk to the stockpile, then take 5 ticks. It is **caught** if any awake chit is within 4 tiles of the
     stockpile and either is `guarding` (see below) or has job `guard` (T24).
     - Caught: the thief gets nothing, loses 10 health, and the catcher's and founder's affinity toward the
       thief drops by 20. Emit `"caught"`, importance 3: `{guard} caught {thief} stealing {item}`. Then fail.
     - Not caught: move the items. The founder's affinity toward the thief drops by 25, and so does every
       awake chit within 6 tiles who saw it. Emit `"theft"`, importance 3: `{thief} stole {n} {item} from the
       stockpile`.
2. **Verb `guard`**: `{"do":"guard","target":"<structure id>"}` stands within 2 tiles of it for 60 ticks
   (`qty` overrides, up to 240), with activity `"guarding"`.
   - Aliases: `protect`, `watch`, `defend`.
   - Each full shift adds `a.bump("guarded")`.
3. **Verb `fight`**: `{"do":"fight","to":"<name>"}`.
   - Aliases: `attack`, `hit`, `brawl`.
   - Approach within 1 tile. Each side's strength is `10 + 8 × (holding a spear) + 12 × (holding a tool of
     class "weapon")`. The winner is chosen with `world.rng`, weighted by strength.
   - The loser loses 20 health and the winner loses 5, but **nobody's health drops below 5 from a fight**. Both lose 10
     mood, and each one's affinity toward the other drops by 30.
   - Emit `"fight"`, importance 3: `{a} and {b} fought; {winner} came out on top`.
   - Fighting a chit that is guarding the fighter's target stockpile counts as a raid (data `raid: true`).
4. **Guards and militia.**
   - T24's `JOBS` gains `guard`. The auto rule: `stats["guarded"] >= 3` → guard.
   - In `_new_day`, count the chits with job `guard`. When the count first reaches 4, and again each time it
     has doubled since the last event, emit `"militia"`, importance 4: `{world name} now keeps a guard of {n}`.
   - `stats()["guards"]` is that count.
5. **Instinct.**
   - A chit with `hunger < 20`, no food carried, and no free food it can reach may steal food from the nearest
     stockpile founded by someone with affinity toward it `< 10`.
   - A chit with job `guard` spends its `_progress` turn guarding the nearest stockpile with probability
     0.6.
   - Instinct never starts fights.
6. **Prompt.**
   - `verb_guide` gains `steal`, `guard` and `fight` lines.
   - `scene()` lists `guarding` next to nearby chits who are guarding.
   - Memories record thefts, fights and grudges, so a model can hold a grudge in its own words.
7. **Moments (T11):** `militia` 80, `theft` 55, `fight` 60.

**Honesty (added after review):** the militia event marks a threshold we authored (4 guards). The guarding
and stealing that produce it are the chits' own choices.

## Done when
`python scripts/plan.py verify T27` passes.
