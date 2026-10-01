# T25 · Trade, markets and the invention of money

**Why:** barter is where economies start, and money is one of the great emergent inventions. It's never
declared: it's whatever everyone ends up trading through. Will World A's money be copper while World B's is
bread? That's a post.

## Build
1. **Value** (`server/chits/sim/items.py`): `base_value(key) -> float`, memoised.
   - Gatherables: 1.0, except ore 2.0 and fish 1.5.
   - Recipe outputs: `(sum(base_value(i) * n for inputs) / qty) * 1.5`, plus 0.5 if the recipe needs a
     station.
   - Unknown keys: 1.0.
2. **Personal value** (`World.value_for(a, key) -> float`): `base_value(key)`, multiplied by each that
   applies:
   - ×2.5 for food (`ITEMS[key].food > 0`) when `a.hunger < 50`
   - ×2.0 for a tool when the chit has no tool of that class (`a.best_tool(cls) is None`)
   - ×0.5 when the chit already carries ≥ 10 of it
3. **Verb `trade`** (both worlds; barter needs no words):
   `{"do":"trade","to":"<name>","give":{"berries":3},"get":{"stone_axe":1}}`.
   - `give` and `get` may also be a string (quantity 1) or a list of names. Aliases: `barter`, `swap`,
     `exchange`.
   - Checks, each failing with a clear message: the partner exists; the trader has `give`; the partner has
     `get`.
   - Approach within 1 tile, then take 4 ticks.
   - The partner **accepts** if all of these hold:
     - `Σ value_for(partner, give) ≥ threshold × Σ value_for(partner, get)`, where the threshold is 0.9,
       or 0.75 within 6 tiles of a functional `market`
     - the partner's affinity toward the trader is ≥ -20
     - the partner is not sleeping

     Otherwise fail with `{partner} didn't want that deal`, and the trader's affinity toward the partner
     drops by 1.
   - On acceptance:
     - swap the items (respecting capacity; if either side can't carry the result, fail and change nothing)
     - both `like(+2)` each other
     - emit `"trade"`, importance 2: `{a} traded {give words} to {b} for {get words}`
     - call `world.record_trade(a, b, give, get)`
4. **Trade log.** `World.trades` is a list of `{"tick","a","b","give","get"}`. Keep the last 500 and persist
   the last 200. `record_trade` appends to it.
5. **Money emerges.** `World.update_money()` runs in `_new_day`. It looks at trades from the last 3 days:
   - For each item, count the trades it appears in (on either side) and the distinct chits involved.
   - An item that isn't food, appears in ≥ 40% of those trades (with at least 8 trades in the window), and
     involves ≥ 4 distinct chits is the world's currency. Take the most frequent if several qualify.
   - If it differs from `World.currency` (default `""`, persisted), set it and emit `"money"`, importance 5:
     `{item name} has become money in {world name}: most trades now go through it`.
6. **Market** design: `{"wood": 8, "stone": 4, "cord": 2}`, work 30, size 2×2, prereq `("recipe", "basket")`,
   blurb `a place to meet and trade`.
7. **Instinct.** In `_communal`, with probability `0.1 + 0.2 * sociability`, trade when all of these hold:
   - the chit has ≥ 8 of some non-tool item
   - a chit within 6 tiles lacks it and has either food while this chit's hunger is < 60, or a tool class
     this chit lacks
   - the deal passes the partner's acceptance test above
8. **Prompt and views.**
   - `verb_guide` gains a trade line.
   - `scene()` shows `- Money here: {item name}` when there is a currency.
   - `stats()` has `"trades"` (count in the last day) and `"currency"`. The Stats tab shows both.
9. **Moments (T11):** `money` scores 93.

## Done when
`python scripts/plan.py verify T25` passes.
