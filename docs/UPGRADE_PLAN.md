# Little Chits — upgrade plan (2026-09-28)

## Where it honestly stands

The simulation is now stable (population holds, deaths are old age, no loops), and progression works on paper:
World B reached the **Copper Age**; headless runs reach iron and copper tools by day ~35. But as a thing to *watch*
it is thin:

- **Buildings don't do anything.** A workshop, kiln or furnace is only a "station" an experiment can happen at.
  Nothing is produced there, nobody works there, and nothing on the map changes when one is built. So the map
  is farms, huts, campfires and a few libraries.
- **Progress is mostly luck.** A new thing appears when a chit happens to put the right items together.
  There is no research, no goal the village works towards, and no reason to build the next thing.
- **Items rarely matter after they're made.** Tools give a speed bonus you can't see; glass, copper and wool have
  one or two uses deep in the recipe list; inventions give small invisible effects.
- **The models don't show initiative.** The 5090's model spends its turns on chores (0.8% of steps were
  experiments); the 3090's model experiments more but drives only ~12-17% of World B, so World B is mostly the
  built-in instinct brain.

## Ten upgrades (ideas borrowed from games that do this well)

1. **Production buildings (Factorio, RimWorld "bills", Banished).** Every building *does* something daily when a
   chit works it: the kiln fires stored clay into pots and bricks, the furnace smelts ore + charcoal into
   copper, the workshop makes tools and paper, a mill turns grain into flour, a granary stops food spoiling. Inputs
   come from the stockpile, outputs go back, and you see smoke, sparks and full shelves.
2. **Village projects (Civilization, Settlers).** The chief (or the village) picks one goal at a time from what
   is buildable next ("a furnace", "the first copper"). It shows on screen with a progress bar, and chits who
   help get renown. It gives progression a direction instead of luck.
3. **Research at libraries (Civ tech, RimWorld research bench).** A scholar who studies at a library with
   tablets earns insight. When it fills, the village learns a *hint* for the next recipe ("something that burns
   very hot, with ore, at a furnace"). Knowledge becomes an investment, not a lottery.
4. **More buildings, and upgrades (Minecraft, Valheim, Anno tiers).**
   - A **bridge** (crosses rivers; the far-resource problem goes away).
   - A **well**, **granary**, **mill**, **smithy** and **dock or fishing hut**.
   - **Walls and a watchtower** (for wolves).
   - **Market stalls**, a **school** (children learn faster), a **bell tower** (copper: the village gathers).
   - Home tiers: hut → brick house → **stone hall**, with glass windows and a lantern.
5. **Every item has a verb (RimWorld, Stardew).**
   - Food spoils unless kept in pots or a granary.
   - A plough (iron) doubles farm yield; a cart (wheels) carries 16.
   - A cloak keeps warm; a lantern lights the night around its holder, visibly on the map.
   - Glass makes windows; paper makes books.
   - A test fails if anything is made that nothing uses (the item pipeline exists; this extends it to
     buildings and effects).
6. **Wants, renown and imitation (The Sims, RimWorld).** Chits want things (a brick house, a copper axe, to be the
   first to make something). Fulfilling a want lifts mood and renown. Famous chits are imitated, so a culture
   forms around what the famous do: some villages become builders, others traders or scholars.
7. **Visible eras (Age of Empires age-up).** Each new era changes the village's look: roads, lamp light at
   night, smoke from kilns, a statue for each era's first discoverer, and a fanfare banner. Progress you can see
   at a glance, which also makes for good clips.
8. **Outposts (Settlers, Anno).** A village can found a camp next to a far resource (a sand or ore camp)
   with a stockpile and a path home. Chits live there in shifts and haul back. This fixes "sand is 32 tiles away"
   properly and makes the map fill out.
9. **A storyteller (RimWorld's Cassandra, Frostpunk).** A pacing director throws challenges matched to the era:
   a hard winter, a drought, wolves, a meteorite, a fire, a sickness. Each has a tech answer (granary, walls,
   medicine), which drives invention and gives every week a story arc worth filming.
10. **Invention 2.0 (Little Alchemy + Scribblenauts, within physics).** Models invent from *material + shape +
    mechanism*. The world maps the result onto real hooks: heat, speed, yield, warmth, light, carrying, storage,
    defence, mood, knowledge. An invention can be a building too (bellows add furnace heat, a waterwheel runs the
    mill). Inventions are taught and inherited like recipes, and appear on the map and in the Knowledge tab.

## JEV on both cards: the "cascade mind"

JEV's idea (from the JEV Fleet Lab and SemIf research): *score a choice instead of generating text*, with a
confidence gate that escalates hard cases.

- **Every decision starts as a choice.** Instinct drafts up to 6 plans. Option **"my own idea"** is always on the
  list. The model answers with one letter, scored by logprobs.
  - Measured on the 3090: 6 s instead of 25 s, half the prompt.
- **Cascade.** If the model picks "my own idea", or its confidence is below ~0.5, the same chit gets a *full*
  generation turn (it writes its own plan, speech and inventions). Creative moments stay, and routine moments
  get fast. This is the JEV Confidence-Gated Policy Cascade.
- **Both cards.**
  - The 5090 runs the cascade with a generous escalation rate: most chits fully model-driven, plenty of free text.
  - The 3090 runs it with a tighter one, so its world stops being mostly instinct.
- **Cheap scoring elsewhere.** Elections, trades (accept or refuse), which belief to join, and which lesson to
  keep can all be one-token choices.
- **Visible in the game: the "Mind" panel.** Click a chit to see what it considered: each option with a
  probability bar, what it chose, and whether it escalated to its own idea. The JEV-style decision becomes part of
  the show, and clips of a chit weighing "harvest 12% / experiment at the furnace 82%" are great on X.

## Does stop/start keep all this?

Yes:
- Code changes are committed on `claude/dazzling-dijkstra-5nv6xh`, and the game runs from that checkout.
- Brain settings (prompt style, parallel requests) live in `server/data/brains.json`.
- The 5090 vLLM settings are in `~/logs/start-mirai-s-5090.sh`, and the 3090 llama-server flags are in
  `~/start-gpus.sh`.
- The desktop shortcut runs those.
- Anything new gets the same treatment, and I check it by doing a real stop/start.

## The X post

A story in numbered clips, cut from the auto-recorder's daily clips and weekly reels plus stills from them:

- **What it is:** two identical islands, one model each, nothing scripted.
- **Why:** to see whether a model can grow a civilisation from nothing.
- **How it works:** instinct keeps chits alive, the model decides, the world judges by physics.
- **The story:** day 1 campfire, first farm, the first chief, a law, the "copper" moment, glass, funny lines.
- **The upgrade:** the cascade mind (JEV), shown in the Mind panel.
- **The ask:** follow along.

Each clip is numbered in the order it appears (`xpost/01_…mp4`, `02_…`) with its caption, next to the thread text.
