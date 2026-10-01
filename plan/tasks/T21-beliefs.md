# T21 · Beliefs, shrines and scripture

**Why:** people don't only invent tools. They invent *meaning*. A model-driven chit that has watched fires die
in a storm might come to believe "the fire remembers those who feed it". Whether that spreads by preaching
(World A), by silent shrines (World B), or not at all, and whether a world ends up with a scripture, is a
completely different story in each world and for each model. Nothing is scripted: the belief text is the
model's own.

**Honesty rule:** beliefs have **no magic**. Their only effects are social and physical: mood near shrines,
affinity between co-believers, and what gets built and written. The chronicle reports them as what chits
*believe*, never as fact.

## Build
1. **Agent.** `Agent.belief: str = ""` holds a belief id, or `""` for none. Persist it; old snapshots load
   with `""`.
2. **World.**
   - `World.beliefs: Dict[str, dict]`, keyed by `_new_id("belief")`. Each value is
     `{"id","name","tenet","founder","founder_name","tick","followers": [agent ids]}`.
     Persist it, defaulting to `{}`.
   - `World.found_belief(a, name, tenet) -> Optional[str]`:
     - Returns None, doing nothing, if `a.belief` is already set, the tenet is shorter than 8 characters, or
       a belief with the same name (case-insensitive) exists in this world.
     - Otherwise creates the belief, sets `a.belief`, emits `"belief"` (importance 5) with text
       `{a.name} founded {name}: "{tenet}"` and data `{"belief": id, "name", "tenet"}`, calls
       `check_insights(a)`, and returns the id.
     - Name: `sanitize_name`-style cleaning, but up to 40 characters. Tenet: stripped and capped at 160.
   - `World.convert(a, belief_id, how) -> bool`:
     - Only works if `a.belief == ""`. Adds `a` to the followers and sets `a.belief`.
     - Emits `"convert"`, importance 3, text `{a.name} came to believe in {name} ({how})`.
     - `how` is one of `preached`, `prayed`, `read`, `raised` (children, see below).
   - When a chit dies, remove it from its belief's followers.
   - **Children** of two parents who share a belief are born with it (`convert(child, id, "raised")`).
3. **Where beliefs come from: reflection only.** Extend T06's `parse_reflection` to also return
   `"belief": {"name": str, "tenet": str} | None`.
   - It accepts `{"belief": {"name":..,"tenet":..}}`, `{"belief": "<tenet string>"}`, or `faith`/`creed`
     keys.
   - For a plain string, the name is `""`.
   - `apply_reflection` calls `world.found_belief(agent, name or f"The Way of {agent.name}", tenet)` when
     the agent has no belief and the reflection holds one.
   - `reflection_messages` tells the chit that it *may* add
     `"belief": {"name": "...", "tenet": "..."}` if, from its life so far, it truly holds a conviction about
     the world, what is sacred, or how to live. It must not invent one just to fill the field. If it already
     follows a belief, name it.
   - Instinct never founds beliefs, and that's the point: meaning comes from minds.
4. **Shrines** (both worlds).
   - New design `shrine`: materials `{"stone": 6, "wood": 2}`, work 25, size (1, 1), decay 0.5, blurb
     `a sacred place; chits come here to pray`.
   - A new prereq kind `("belief", "any")`, which `design_prereqs_met` treats as met when `agent.belief`
     is set.
   - `Structure.belief: str = ""` is persisted. When a shrine completes, it takes its completing builder's
     belief, and its `name` becomes `Shrine of {belief name}`.
5. **Verbs.**
   - **`pray`** (both worlds): `{"do":"pray"}` or `{"do":"pray","target":"<shrine id>"}`.
     - It walks to the given shrine, or the nearest functional one within 30 tiles, and prays for 12 ticks.
       Then it adds `+6` mood, and if the chit has no belief, `convert(a, shrine.belief, "prayed")`.
     - No shrine → failure containing `shrine`.
     - In World B this is how belief spreads, silently, through places.
   - **`preach`** (World A only; needs `flags["say"]`): `{"do":"preach"}`.
     - The chit speaks its tenet as a speech bubble (`a.speak`).
     - Every awake chit within 6 tiles without a belief converts with probability
       `clamp(0.25 + affinity_toward_preacher / 200, 0.05, 0.9)`, using `world.rng`.
     - Fails with a message containing `believe` if the chit has no belief, and with a message containing
       `talk` in a world without speech.
   - **Scripture** (World A only; needs `flags["write"]`):
     - `{"do":"write","what":"belief"}` (also `"scripture"`, `"teachings"`, or the belief's name) inscribes a
       tablet with knowledge `belief:<id>` and text `"{name}: {tenet}"`, using the usual tablet and library
       rules.
     - When a belief reaches 3 tablets, emit `"scripture"` once, importance 5:
       `The {name} now has a scripture — 3 tablets of teachings`.
     - **Reading** a `belief:` tablet converts a chit with no belief (`how="read"`) instead of calling
       `learned`.
6. **Everyday effects** (every 10 ticks):
   - Two followers of the same belief within 3 tiles gain `+0.5` affinity toward each other.
   - A follower within 8 tiles of a functional shrine of its own belief gains `+0.3` mood.
7. **Prompt.**
   - `scene()` shows `YOUR BELIEF: {name} — "{tenet}"` after the YOU/ambition lines.
   - The nearby-structures listing names shrines.
   - `verb_guide` gains lines for `pray` (both worlds) and `preach` (only when `flags["say"]`).
   - The `write` line mentions `belief`.
8. **Views and web.**
   - `views.snapshot` includes `"beliefs"`, and `agent_detail` includes `belief`: `{id, name, tenet}` or None.
   - The Inspector shows `🕯 {name}`.
   - The Knowledge tab gets a **Beliefs** section per world: name, tenet, founder, followers, and whether it
     has a scripture.
9. **Moments (T11):** `belief` scores 90, `scripture` 88.

**Honesty (added after review):** belief *content* comes from models; the mechanics that spread it are ours.
The chronicle says what chits believe, never that it is true.

## Done when
`python scripts/plan.py verify T21` passes. 🖐 Then read the beliefs a real model founds over a few days.
