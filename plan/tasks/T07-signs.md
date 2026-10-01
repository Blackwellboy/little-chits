# T07 · Signs: leave marks in the world (stigmergy in both worlds)

**Why:** World B can't talk, but it can *mark the land*. Watching whether the silent world invents its own sign
language is the heart of the experiment, and very postable.

## Build
1. **Verb** `mark`: `{"do":"mark","what":"<symbol>"}`.
   - Symbols: `food, wood, stone, clay, ore, fish, danger, home, build, meet`. Accept a few aliases
     (`berries`→food, `warning`→danger, `gather`→meet).
   - Unknown symbol → failure string mentioning the valid symbols.
   - Costs **1 wood**, which is consumed. With no wood, fail with a message mentioning wood.
   - Takes 4 ticks and places a sign on the chit's current tile. One sign per tile; a new one replaces the
     old one.
   - Allowed in **both** cultures.
2. **World.**
   - `World.signs: Dict[str, dict]`, keyed by sign id (`g1`, `g2`… via `_new_id("sign")`). Each value is
     `{"id","x","y","symbol","author","author_name","tick"}`.
   - Signs older than 3 days (720 ticks) are removed. Check at least every 60 ticks.
   - Set `World.signs_dirty = True` whenever signs change.
   - Persist in `to_dict`/`from_dict`, defaulting to `{}`.
3. **Event** `"sign"`, importance 2, text `{name} put up a sign: {symbol}`, data
   `{"sign": id, "symbol": symbol}`.
4. **Prompt.**
   - `verb_guide` has a `mark` line.
   - `scene` lists signs within `SIGHT` tiles on one line:
     `- Signs: "clay" 3 tiles E at (41,20) by Pip; "danger" …` (at most 5, nearest first).
5. **Transport.** `views.snapshot` includes `"signs": list(world.signs.values())`. `Runtime.frame` includes
   `"signs"` (the full list) only when `signs_dirty`, then clears the flag; otherwise it's `None`.
6. `normalize_verb`: aliases `sign`, `signpost` and `label` map to `mark`.

The web sprite for signs comes in T18.

## Done when
`python scripts/plan.py verify T07` passes.
