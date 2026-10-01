# T08 · Weather and disasters

**Why:** a storm that blows out every fire the night before winter makes a story, and makes survival depend on
foresight.

## Build
1. **State.** `World.weather: str`, one of `"clear"`, `"rain"`, `"storm"`, `"drought"`, `"snow"`.
   `World.weather_until: int` is the tick it ends. Persist both, defaulting to clear.
2. **`World.set_weather(kind: str, days: float = 1.0) -> None`.** Sets the weather and emits an event
   (effects below). Calling it with the current kind again does nothing.
3. **Daily roll.** At each day boundary (in `_new_day`), if the weather has ended, pick new weather with
   `self.rng`:
   - winter: snow 50%, storm 10%, else clear
   - autumn: storm 20%, rain 25%, else clear
   - summer: drought 15%, rain 15%, else clear
   - spring: rain 35%, else clear

   Weather lasts 1 day (storms 0.5 days).
4. **Effects.**
   - **storm**, applied once on start:
     - every lit campfire goes out (fuel = 0)
     - each complete structure has a 35% chance to lose 25 durability
     - emit `"storm"`, importance 4: `"A storm tears across the island"`
     - while storming, `temperature()` is reduced by 0.15
   - **drought**:
     - berry and fiber regrowth is ×0 (in `_regrow`), and farms don't grow
     - emit `"drought"`, importance 3
   - **rain**:
     - farm growth is ×1.5 and berry regrowth is ×1.5
     - lit campfires lose 0.05 extra fuel per tick
     - emit `"rain"`, importance 1
   - **snow**: emit `"snow"`, importance 1. No mechanical change beyond winter.
   - **clear**: when changing *to* clear, emit nothing.
5. **Clock and prompt.**
   - `clock()` includes `"weather"`.
   - `scene()`'s first line includes the weather when it isn't clear, e.g. `… It is cold. A storm is raging.`
6. **Web** (keep it minimal here; T18 does the art): `types.ts` `Clock` gets `weather: string`, and the top bar
   clock pill shows an icon (🌧 ⛈ 🔥 ❄) when it isn't clear.

7. **Common sense: get out of the weather.** Chits must know to go inside when a storm hits or snow is
   falling, whoever or whatever is driving them.
   - `World.sheltered(a) -> bool` is True if any of these hold:
     - `in_home(a)` is truthy
     - the chit stands on, or next to (Chebyshev distance ≤ 1), a cell of a functional `hut` or `brick_house`
     - the weather is not `storm` and the chit is within 2 tiles of a lit campfire
   - `World.exposure(a) -> float` is the extra warmth lost per tick to the weather:
     - `0.0` when sheltered
     - otherwise storm `0.35`, snow `0.2`, rain `0.05`, else `0.0`

     Apply it where warmth is updated each tick. While exposed to a storm, health also drops by `0.02` per
     tick.
   - **New verb `shelter`.** Add it to `VERBS`, with aliases `take_cover`, `go_inside`, `hide` and `cover`.
     - It walks to the chit's own home if that is functional. Otherwise it goes to the nearest functional
       `hut`/`brick_house` within 30 tiles. Otherwise, if the weather isn't a storm, it goes to the nearest
       lit campfire within 30 tiles.
     - With none of those, it fails with a message containing `nowhere`.
     - Once `sheltered`, set activity to `"sheltering"`. Finish when the weather is no longer `storm` or
       `snow`, or after 240 ticks.
   - **Reflex.** In `actions.reflexes`, after the hunger and energy checks and before the warmth check: insert
     `{"do":"shelter","_reflex":True}` when all of these hold:
     - the weather is `storm`, or it is `snow` and `a.warmth < 60`
     - the chit is not `sheltered`
     - the head step's verb is not `shelter`, `sleep`, `eat` or `warm_up`

     Set emote ⛈ for a storm and 🌨 for snow.
   - **Prompt.**
     - When the weather isn't clear, `scene()`'s first line also says `You are out in it.` when not sheltered,
       or `You are under cover.` when sheltered.
     - `verb_guide` gains `{"do":"shelter"}  (get indoors or by a fire in bad weather)`. If T02 is done, the
       compact `Verbs:` line lists `shelter` too.

## Done when
`python scripts/plan.py verify T08` passes.
