# T30 · Contact: boats between the islands

**Why:** two separate islands make a clean experiment. Letting them *meet* makes history. With contact on, a
chit that builds a boat can sail to the other island and arrive as a stranger. It carries its own knowledge,
its own memories and, in model-vs-model games, **its own model's mind**. What happens when a World A pioneer
washes up among World B's people?

Contact is an **option** (off by default), so a pure model-vs-model comparison stays pure.

## Build
1. **The option.**
   - `Runtime.contact: bool`, stored in store meta `contact` and set by `CHITS_CONTACT=1` or by the reset body
     `"contact": true`.
   - It only applies in two-world modes. ⟲ New game shows the checkbox **⛵ Allow contact between the islands**
     for versus and culture modes.
2. **Boat.**
   - Design `boat`: materials `{"wood": 10, "cord": 4}`, work 40, prereqs `("recipe","cord")` and
     `("recipe","stone_axe")`, size 1×1, blurb `a boat to cross the sea`.
   - `find_site("boat", …)` only returns passable land tiles next (4-neighbour) to water.
3. **Verb `sail`**: `{"do":"sail"}`, with aliases `voyage`, `row` and `set_sail`.
   - It needs a functional boat within 20 tiles; walk to it.
   - With contact off, fail with a message containing `sea` ("Beyond the horizon there is only more sea").
   - With contact on:
     - Remove the boat.
     - `world.depart(a)` removes the chit from its world and puts `{"agent": a.to_dict(), "from": world.id,
       "arrive_tick": world.tick + 120}` into `world.outbox`. Don't count it as a death.
     - Emit `"voyage"`, importance 5: `{name} sailed away over the sea`.
4. **Arrival.**
   - `Runtime.step_worlds(n=1)` steps every world once per call with `mind.hook`, then moves due outbox
     entries into the other world via `world.arrive(agent_dict, from_world_id)`. The runtime loop uses
     `step_worlds` too.
   - `arrive`:
     - places the chit on a random passable coast tile (next to water), keeping its id (suffixed `-x` if
       taken), name, knowledge with provenance, memories, lessons, skills and **brain id**
     - sets `a.origin = from_world_id` (a new persisted field, default `""`) and `a.home = None`
     - clears its plan
     - emits `"arrival"`, importance 5: `A stranger named {name} arrived by boat from {from world name}!`
     - adds a memory `I crossed the sea and reached a new land` (importance 5)
   - If its brain id doesn't exist in the mind, it falls back to the destination world's brain.
5. **Everyone notices.**
   - `scene()` lists `- A stranger is among you: {name}, from across the sea.` for nearby chits whose
     `origin` isn't this world.
   - Views include `origin`, and the Inspector shows `⛵ from World A`.
   - T23's divergence report counts knowledge that arrived by boat (provenance of an arrived chit) as
     `contact`.
6. **Moments (T11):** `voyage` 90, `arrival` 96.

**Integrity (added after review):**
- Contact is forbidden in `experiment` runs (F1), and enabling it records `contact: true` plus the first
  contact tick in the run manifest.
- If an immigrant's brain id doesn't exist in the mind: **play** falls back to the destination world's brain,
  but **experiment** marks it `brain_unavailable` (it waits like any strict chit) and never switches policy.
- Carried inventions (T20) travel with the chit: the destination world adds the foreign item and recipe to its
  catalogue under the original key, and the chit keeps knowing it.

## Done when
`python scripts/plan.py verify T30` passes.
