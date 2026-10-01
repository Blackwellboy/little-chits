# T34 · Rivals mode: "Age of Chitpires"

**Why:** two civilisations that know about each other make the biggest story of all. They explore by boat and
find the other island. Then they trade, steal, raid and make peace. Model vs model stops being two separate
fish tanks and becomes a real contest. Every choice about war or peace comes from the chits' minds; the
rules are just the physics of boats, theft and fighting from T27 and T30.

This is a **play** mode, not a clean experiment. The islands affect each other on purpose.

## Build
1. **Mode `rivals`.**
   - Add it to `runtime.MODES`: two worlds, both `direct`, with contact always on (T30).
   - ⟲ New game shows it as **⚔🏝 Rivals (Age of Chitpires)**: "The islands can find each other by boat.
     Trade, raid, or make peace."
2. **Relations.** `World.relations: Dict[str, dict]` maps another world id to `{"hostility": float,
   "trades": int, "raids": int, "gifts": int, "met": bool, "state": "unknown"|"peace"|"tension"|"war"}`.
   Persist it.
   - `met` becomes true when the first chit from that world arrives (T30 `arrive`), or one of ours arrives
     there. Emit `"contact"`, importance 5: `{world} has met the people of {other}!`.
   - Hostility rises by 10 per theft and 15 per fight involving a chit from the other world, including fights
     and thefts *by* our chits there, as the other side sees them. It falls by 5 per trade and 8 per gift
     across worlds. It decays by 1 per day toward 0, and is clamped to 0..100.
   - The state follows hostility, with hysteresis:
     - war when ≥ 60 (back down below 40)
     - tension when ≥ 25 (back down below 15)
     - otherwise peace (after `met`)
   - `record_incident` also marks both worlds as `met`, because an incident means they have met.
   - Each change of state emits `"war"`/`"peace"`/`"tension"`, importance 5 for war and peace, 3 for
     tension. Update both worlds' relations symmetrically via `Runtime.record_incident(world_a, world_b,
     kind)`.
3. **Raids by sea.**
   - A chit that sails (T30) may carry `"intent": "raid"|"trade"|"explore"|"settle"` on the `sail` step
     (default `explore`). Keep it as `a.voyage_intent`, shown to the other world's chits in their scene:
     `- A stranger from World A is here (they came to {intent}).`
   - A stranger can sail home with the verb `sail` `{"home": true}` if it has built or found a boat on the far
     shore. Arriving home with stolen goods emits `"raid"`, importance 4.
4. **Scene and reflection.**
   - `scene()` adds `- The people of {other}: {state}` once they have met.
   - Reflection may add an ambition like "make peace with World B"; this is ordinary T06.
5. **Scoreboard.** `/api/rivals` returns both worlds' relations and a side-by-side count table: population,
   discoveries, structures, trades, raids and gifts. Show it in a Stats panel section and as a card (reuse
   T14's style).
6. **Moments (T11):** `contact` 97, `war` 96, `peace` 95, `raid` 85.

## Done when
`python scripts/plan.py verify T34` passes.
