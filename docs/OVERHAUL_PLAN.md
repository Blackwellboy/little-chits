# LITTLE CHITS — Overhaul Plan (v2 "Hearth")

Date: 2026-09-24

This is the plan for the v2 overhaul. The earlier work is still in its branches
(`feat/phase-o-functional-civilization-artifact-ecology`,
`feat/observer-v5-max-visual`, the planning and history branches) and nothing
in it has been deleted. v2 is a clean rebuild that keeps the ideas that worked
and drops the parts that got in the way.

## 1. What I found

The vision is still right: tiny embodied AI creatures that start as
near-identical generalists, learn, build, cooperate, and leave an environment
that remembers them. It runs as a twin-world experiment (A = direct culture,
B = stigmergy only), and the world is watchable and worth following.

These are the reasons the previous build stalled:

| Symptom | Root cause |
|---|---|
| Chits only build farms and shelters, and never use storage, workshops or projects | Nothing in the world *rewards* anything else. There were no tools that change outcomes, no seasons that make stored food matter, and no crafting chain. The model chose the only things that visibly paid off. |
| The model makes shallow choices | The prompt was a JSON dump of bureaucratic fields (`action_feasibility`, `capability_retrieval.overhead_us`, `goal_intent.op`, receipts) instead of a description of a *world*. Small models drown in it. |
| Chits stand around thinking | Cognition was synchronous with plan completion, one decision covered very little work, and queues were measured instead of avoided. |
| LIVE / RECONNECTING flicker | Several sockets were in use and status flipped on every transient close. There was no heartbeat and no grace period. |
| The UI felt dated and over-engineered | Debug bars overlapped the world, the terrain was a flat green field, resource dots dominated the map, and there were many modes (Live/History/Replay/Home/More/View). |
| Progress stalled in process | About 270 commits of gates, seals, pre-registrations and audits, and the last assay made 5–7 decisions in total. The substrate never became *fun enough to have results*. |

## 2. What we keep, and what we drop

Keep these principles, because they were right:
- **Cognition proposes, the simulator decides.** The LLM never mutates state directly.
- **No assigned professions.** Roles are inferred from behaviour.
- **Local observation only.**
- **The environment is memory.** Structures, tablets, roads and ruins outlive their makers.
- **Twin worlds A/B**, differing only in the recorded capability flags.
- **Grounded chronicle.** Every sentence in the story comes from a real event.
- **Headless.** The world runs without the browser.

Drop these: Postgres/Alembic (replaced by SQLite), the treatment/receipt/ledger
bureaucracy, the 60+ cognition modules, phase-gated rule versions, and the
Day-N button walls.

## 3. The new world

### Terrain
A 128×128 tile world built from seeded noise. It has deep and shallow water,
sand beaches, grassland, meadows (fiber, berry bushes), forest, hills, rocky
mountains with copper-ore veins, and clay banks along rivers.

### Time
One tick is one in-game minute, and a day is 240 ticks. Seasons last 3 days
each (spring, summer, autumn, winter).

- **Winter** stops berry regrowth and crop growth, and nights get cold. That
  makes **storage, huts, campfires and farms matter**, so the world itself
  motivates the things the old world never used.

### Needs
- Hunger, energy, warmth, and social (World A).
- Health falls when any need is critical.
- Chits age. Two well-fed chits with high affinity and a home can have a child.

### Materials and discovery
This is the heart of "learn and grow".

- There are about 40 items. Each one has **visible properties**, for example:
  - stone is hard and heavy
  - fiber is flexible and good for binding
  - clay is moldable and hardens in heat
- Recipes are world *laws*, not a menu. Chits start knowing almost nothing.
- **EXPERIMENT** tries combining 2–3 carried items, optionally at a station
  (fire, workshop, kiln, furnace):
  - A lawful combination creates the item. The chit learns the recipe and a
    DISCOVERY event is emitted ("first in the world" if it is).
  - A failed combination becomes a memory ("stone + berries does nothing").
- An LLM can *reason* from the properties ("a sharp stone bound to a stick
  should cut wood"), which is where model quality visibly matters.
- **Tools change physics**, which gives a real reason to invent:
  - an axe doubles wood yield
  - a pick is required for ore and doubles stone yield
  - a spear allows fishing
  - a basket gives +8 carry capacity
  - copper tools are better still

### The tech ladder
Nothing here is an unlock bar. The ladder is only reachable through
discovery: stone tools → fire and cooking → farming → pottery and bricks
(kiln) → charcoal → copper smelting (furnace) → copper tools → brick
architecture → writing (tablets) → library → monuments.

### Structures
A chit can imagine a design only if its own knowledge supports it. For
example, it has to know "brick" before it can conceive a furnace. Knowledge
spreads socially, so architecture spreads too. The designs are:

- campfire (warmth, light, cooking station)
- hut and brick house (shelter, sleep, birth)
- stockpile (shared storage)
- farm (seeds → grain)
- workshop (station)
- kiln and furnace (stations)
- well
- road (fast travel)
- library (holds tablets, and reading teaches)
- monument (culture and mood)

### Cooperation
Building creates a **construction site** entity with material needs and work
remaining. *Any* chit can deliver materials or work, so a project is a site
plus the people who touched it. Chits can see sites, and their prompt says
"Mo's kiln needs 3 more clay".

### Culture channels

| | World A (direct culture) | World B (stigmergy) |
|---|---|---|
| **say** (speech bubbles; others remember what was said) | yes | no |
| **teach** (transfer a recipe or design to an adjacent chit) | yes | no |
| **write tablet** (leaves a readable artifact) | yes | no |
| **give** | yes | yes |
| **inspect** (reverse-engineer an item or structure) | yes | yes |
| **watching someone craft nearby** | yes | yes |
| **reading tablets in a library** | yes | yes (reading an artifact counts as stigmergy) |

### Learning
Chits learn in four ways:
1. **Knowledge.** Recipes and designs, each with provenance: discovered,
   taught, read, observed, or inspected.
2. **Episodic memory.** Importance-scored and capped. Retrieval by recency,
   importance and relevance.
3. **Lessons.** A daily *reflection* turns memories into up to 5 beliefs that
   steer future plans. These come from the LLM, or are rule-derived for
   instinct.
4. **Skills.** Practice raises gathering, crafting and building efficiency,
   which is where specialisation emerges.

### Relationships
Affinity grows when chits work on the same site, trade, talk, or teach. The
observer infers roles from behaviour.

## 4. Brains: drop in any model

- Anything that speaks the **OpenAI-compatible** API works: llama.cpp
  `llama-server`, vLLM, Ollama, LM Studio, SGLang, TabbyAPI, OpenRouter, or
  OpenAI.
- `brains.json` and the in-app **Brains panel** let you add an endpoint,
  auto-list its `/v1/models`, test it, and assign it per world. That makes a
  model A/B comparison trivial.
- Presets are included for the 3090 (`:18080`), the 5090 (`:18090`),
  llama.cpp (`:8080`), Ollama (`:11434`) and LM Studio (`:1234`).
- **Robust output handling:**
  - strips `<think>…</think>` and code fences
  - extracts balanced JSON and repairs trailing commas and quotes
  - aliases common verb misspellings
  - sends `response_format` when the endpoint supports it, and auto-disables
    it when it doesn't
  - sends Qwen `enable_thinking:false` when that is configured
- **Never blocks the world.**
  - An async worker pool runs with a per-brain concurrency limit.
  - Plans run up to 6 steps, so one decision covers several minutes of work.
  - The next plan is prefetched before the current one finishes.
  - Survival reflexes (starving, freezing) interrupt a plan.
  - If a model is down or slow, **instinct** takes over and is clearly
    labelled.
- The prompt is natural language and reads like a game scene: who you are,
  your needs, what you see, what you know, your memories and lessons, and
  what's happening nearby. It ends with a short verb list.
- Per-brain stats are recorded and shown live: latency, tokens/s, parse
  success, and fallbacks.

## 5. Observer

- **The world fills the screen.** Controls float on top and there are no
  debug bars.
- **The renderer is PixiJS v8 with procedurally generated pixel art.** Nothing
  is downloaded, and all assets are drawn at boot.
  - **Terrain:**
    - the terrain is baked in chunks with noise-shaded tiles and soft biome transitions
    - shorelines have foam
    - water sparkles
    - snow covers the ground in winter
  - **Chits** are round creatures with individual colours, blinking eyes and
    bobbing walk cycles. They show:
    - the tool in hand and a bundle when carrying
    - a truthful 💭 while their model is thinking
    - speech bubbles and emotes (✨ discovery, ♥ bond, zzz)
  - **Structures:**
    - animated campfire flames with smoke
    - smoking kilns and glowing furnaces
    - crop growth stages
    - scaffolding and progress bars on construction sites
  - **Lighting and weather:**
    - a day/night cycle with a dark overlay and additive light from fires and windows
    - rain, snow and falling leaves
    - particle bursts on discoveries, and dust when working
- **Minimal chrome:**
  - world switcher (A, B, or split)
  - clock and season pill
  - speed control
  - brain status pill
- **Inspector drawer:**
  - portrait, needs and traits
  - the current thought, goal and plan with step progress
  - inventory, knowledge (with how it was learned), lessons and memories
  - relationships, and which brain it uses
  - a Follow button
- **Chronicle tab:** grounded highlights. Clicking one flies the camera there.
- **Knowledge tab:** each discovery with its first discoverer, and how many
  know it in A vs B. This is the experiment, made visible.
- **Stats tab:** A vs B sparklines.
- **Transport:**
  - a single WebSocket, with a snapshot on connect and deltas at about 8 Hz
  - heartbeat and exponential-backoff reconnect
  - the status only changes after a 3 s grace period, which ends the flicker
- **Ambient audio:** none in v2. It is left for later.

## 6. Persistence and ops

- The data directory holds one SQLite database containing world snapshots
  (gzip JSON) and the chronicle and event log.
- The world snapshots every in-game day and on shutdown, and resumes on
  restart.
- `make dev` runs both server and web, and `make run` serves the built web
  from FastAPI on a single port.
- Configuration is read from environment variables and `brains.json`.

## 7. Execution order

1. The sim kernel: terrain, items and recipes, structures, agents and needs,
   actions and executor, knowledge, memory, social, reproduction, chronicle.
2. Instinct brain, so the world is alive with no model at all.
3. The LLM brain: prompt, parser, async client, scheduler, registry, reflection.
4. Server: REST and WS, persistence, runner.
5. Web: renderer, UI, brains panel.
6. Tests:
   - unit tests for the laws
   - A/B channel gating
   - parser fuzzing against messy model output
   - a fake OpenAI server end-to-end
   - a long headless instinct run that must show progression (discoveries,
     structures, births)
   - Playwright screenshots
