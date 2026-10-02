# Upgrade plan status, 2026-09-29

An evidence check of [docs/UPGRADE_PLAN.md](UPGRADE_PLAN.md) (written 2026-09-28) against the code and tests on
the v2 branch `claude/dazzling-dijkstra-5nv6xh`. The frozen 41-task plan in `plan/` is complete and is not part of
this list. Every row was checked in the source, not taken from commit titles.

- **DONE**: in the branch, with tests.
- **PARTIAL**: some of it is in the branch, or all of it exists only on an unmerged local branch.
- **NOT_STARTED**: no code for it anywhere.
- **SUPERSEDED**: replaced by a different approach.

"Base" means the branch head before this session's work (`0bc9571`). "This session" names the commits that
landed on top of it. The rows were updated after a second pass the same day, which merged the village projects and
buildings branches, and again after a third pass that built ten further ideas on top (both are described near the
end).

## The ten upgrades

| # | Upgrade | Status | Evidence |
|---|---|---|---|
| 1 | Production buildings (bills, shifts, goods back to stores) | **DONE** (this session) | Base had none: a kiln, furnace or workshop was only a place to experiment (`sim/actions.py` had no `work` verb). Merged in c15b5ad from the local-only branch `claude/production-buildings` (03f1eb3, 437e902, 893a361, dd8f522), plus a visible layer (0f1cc2f): the `work` verb and `plan_bill`/`era_path` in `sim/actions.py`, instinct shifts in `brain/instinct.py`, `worked_until`/`produced` on structures, smoke and sparks while a shift runs (`web/src/render/WorldView.ts`, `WORK_FX`), and the Inspector's "At work" row and "Made here" card. Tests: `tests/test_production.py` (18). 12-seed, 30-day instinct A/B: 0 → 388 goods made per village; discoveries, era and population held (22.4 → 22.3, 5.4 → 5.5, 58.7 → 59.2). A mill and granary (the plan's other two examples) are not stations here; they are in the buildings branch (row 4). |
| 2 | Village projects | **DONE** (second pass) | Merged in 145c5e3 from the local-only branch `claude/village-projects` (c23b05c + f04db7a): `sim/projects.py`, `brain/civic.py`, and a project bar with the road to the next age in the Progress panel. Reviewed and fixed in cb1b1dd and e28bee8: the world's own pick is "chosen by need", never presented as a chief's call; only chits that knew of a project are thanked for it; where chits can't talk, a project is known only by sight of its site. Tests: `tests/test_village_projects.py` (22). |
| 3 | Research at libraries | **DONE** (second pass) | `sim/research.py` (145c5e3): a `study` verb at a library with tablets earns insight, and enough of it gives a hint worded by properties. Where chits can't talk, only those who studied know the hints. By design a hint is drawn from the recipe table: it says what an undiscovered thing's inputs are like, never which things. A find after a hint is still recorded as "discovered", with no hint lineage. |
| 4 | More buildings and upgrades | **PARTIAL** (most of it, second pass) | Merged in d0ae424 from `claude/buildings` (af05722): `sim/buildings.py`, `brain/builder.py` and the sprites in `web/src/render/buildings.ts`. New: longhouse and two-storey homes (a crowded home is rebuilt bigger in place), bridge, well, granary, mill, smithy, watchtower, school and bell tower. `market` and `monument` already existed. Not built: dock or fishing hut, walls, stone hall. Tests: `tests/test_buildings.py` (26). |
| 5 | Every item has a verb | **PARTIAL** | Done: the item-pipeline invariant (`tests/test_item_uses.py`: every item has a use, a way to get it, and existing inputs and stations; 68962bc), and uses stated in the prompt (56df494). A cart carries 16, cloaks halve the cold, and a lantern counts as warmth. Second pass: stored food spoils unless a granary is near or clay pots hold it, flour and loaves come from the mill, and the smithy doubles metal-tool speed. Done later: an iron plough doubles the base farm yield while carried (PR #32). Lantern light was already present in the live renderer (`a.tool === "lantern"` adds a moving light around its holder). Still not done: paper books and extending the pipeline test to buildings and effects. |
| 6 | Wants, renown and imitation | **DONE** (second pass) | `sim/wants.py` (145c5e3). Each adult has a want, which comes true only by what really happens. Renown comes from discoveries, projects, teaching and wishes, and chits near the most renowned lean towards what it is doing. Where chits can't talk, a chit wants only what it has seen (cb1b1dd). Shown in the Inspector (💭 wants, ⭐ renown). |
| 7 | Visible eras | **DONE** (third pass) | Before: an age-up and news banner (ac10a4a, `web/src/ui/Overlays.tsx`), kiln, furnace and brick-house smoke and night light, roads, and the second pass's longhouses, two-storey and brick houses. 2f11032 adds lamps along the roads at night from the copper age, brighter and whiter with each age (`web/src/render/eras.ts`), and a statue by the biggest village for each age's first maker (`views.eras`, `/api/worlds/{wid}/eras`). Huts already standing are not re-skinned by era. Tests: `tests/web/eras.test.ts` (4) and `test_the_eras_endpoint_names_each_ages_first_maker`. |
| 8 | Outposts | **DONE** (third pass) | c1fb1a4 adds an `outpost` design: a camp store and tent, costing wood 8, stone 4 and cord 2. Store, take and haul treat it as a store. A chit sleeps at a camp when home is more than 30 tiles away. A failed gather names the spot the chit remembers and suggests a camp. Instinct founds a camp only where a chit remembers the resource at least 30 tiles from home (`brain/outposts.py`), so on instinct camps stay rare: 0.1 to 0.25 per village by day 30, and about 1 per village by day 60 in the no-speech runs. Instinct otherwise stays local by design, because sending it far cost discoveries and chits. Models get the verb and the hint. Tests: `tests/test_outposts.py` (4). |
| 9 | A storyteller | **DONE** | a6294a6: `sim/storyteller.py` covers hard winter, wolf pack, drought, sickness, fire, meteorite, traveller and bumper harvest. It is play-only and follows one schedule for both worlds (`tests/test_storyteller.py`). d6b8145 makes both worlds apply a challenge with the same random stream and stops the traveller handing out recipes (`tests/test_audit_fairness.py`). Since the second pass, several challenges have a building to answer them: a watchtower for wolves, a granary for drought stores, warm homes for a hard winter. |
| 10 | Invention 2.0 | **PARTIAL** | Done: 3eff5be adds the defence, farming, healing and speed purposes with real hooks, and makes material quality scale tool power (`sim/invent.py`, `tests/test_invent2.py`). Not done: composition from material, shape and mechanism (purposes are still keyword buckets, and the module docstring says so), and inventions that are buildings (bellows, waterwheel). |

## The JEV "cascade mind" section

| Item | Status | Evidence |
|---|---|---|
| Every decision starts as a choice (options, letter, logprobs) | **DONE** | a8ba9fc `prompt_style: choose`; `Mind._ask_choice`/`_choose`; `test_choose_mode_adopts_the_plan_the_model_picked` |
| Cascade: own idea or low confidence gets a full turn | **DONE** | a5294f8; `escalate_below`; `test_cascade_keeps_confident_choices_to_one_token`, `test_cascade_escalates_its_own_idea_to_a_written_plan` |
| Both cards, different escalation rates | **DONE** | fffec4b per-brain `escalate_share` budget, `test_cascade_keeps_to_its_escalation_budget`. The per-card values live in `server/data/brains.json` (machine-local, not in git). |
| Honest records of each cascade decision | **DONE** (this session) | df894c8: an unreadable reply is a parse failure, not a silent "A"; both requests and the escalation grant or denial are recorded (`test_invalid_choice_is_not_a_successful_option_a`, `test_cascade_records_both_requests_and_correct_full_prompt`). |
| Cheap scoring elsewhere (elections, trades, beliefs, lessons) | **PARTIAL** (third pass) | 23baab2: a model chief chooses the village's next project from the world's candidates with one token (logprobs), recorded as a `chief-project` decision. The world checks the answer. When no answer comes, need decides and the project says why (11c0b02). **2026-10-03:** elections and trades too (`sim/ballots.py`, decision styles `vote` and `trade-offer`). Each model-minded voter backs one front-runner, and each model-minded partner accepts or refuses an offer. Without an answer, the simulator decides. Beliefs and lessons are still decided in the simulator. |
| The Mind panel ("What it weighed") | **DONE** | a5294f8, `web/src/ui/Inspector.tsx` shows `last_choice` options with probabilities, the choice and whether it escalated |

## Other sections

| Item | Status | Evidence |
|---|---|---|
| Stop/start keeps it all | **DONE** | Code and data are in the branch; brain settings are in `server/data/brains.json`; model flags are in `~/start-gpus.sh` and `~/logs/start-mirai-s-5090.sh` (outside the repo). A real stop/start was checked on 2026-09-28. |
| The X post | **PARTIAL** | The tooling is done: recorder day clips, week reels and live close-ups of big moments (1b8a45d, e09a03b, aa86cf1; `tests/test_recorder.py`). The third pass adds a director's cut (860dcf2): a week's best moments, numbered in story order with captions, joined into one video (`POST /api/recordings/{run}/cut/{week}`, a button per week in Recordings). Nothing has been posted; posting is the owner's call. |

## Also carried in this session: the recovered Codex audit

A Codex session ran out of credits with an integrity audit that existed only as uncommitted changes. It was
preserved (local branch `wip/codex-audit-fixes-2026-09-29` = 59abd05, also pushed; a binary patch sits outside the
repo), reviewed, and carried in two commits:

- d6b8145 makes the twin worlds fair (storyteller, traveller, culture-true inheritance and failure sharing).
- df894c8 covers atomic checkpoints and schema 3 timelines, per-step action outcomes with provenance, stricter
  experiment parsing, the supply ledger and choice records.

On review I dropped one change that would have undone the copper-age "heat hunch", and added a week's retention
for action outcomes. 7c8a910 is a follow-up: the audit rightly stopped option-drafting from making a chit
homeless, which also removed the only way a grown chit left a crowded family home. Now it moves into the house it
builds when that house is finished.

12-seed, 30-day instinct A/B against the base (T10 setup):

- discoveries 22.9 → 22.4
- era 5.6 → 5.4
- population 58.8 → 58.7
- starvations 0.3 → 0.0
- homes 22.8 → 16.4

Fewer homes is the removed side effect: chits no longer turn homeless at random and build extra huts.

1a7fef1 is a second follow-up. The audit starts a new timeline when a play world resumes after a crash. The
chronicle, story, log and history views then read only the new timeline, and would have been empty before the
restart: a dry run on a copy of the live save found 0 of 30,421 events. Now a timeline also reads its ancestors
up to each fork, and a loaded world's events are stored once instead of being copied into the new timeline.

## Second pass (same day): village projects and buildings

Both local-only branches were merged, reviewed and fixed:

- **Village projects** (145c5e3). Culture gating (cb1b1dd), then review fixes (e28bee8). An independent review
  found:
  - the world's pick was announced as a chief's call;
  - thanks and memories went to chits that never knew of the project;
  - recipe inputs appeared in model menus with no channel;
  - a find plan named the hidden item;
  - station shifts didn't count towards "make" projects.

  Each fix has a test that fails without it.
- **Buildings** (d0ae424). Integration fixes are in the merge commit:
  - the road to the next era took the smithy's bricks for a missing workshop;
  - "mill" meant the factory;
  - the smithy didn't speed station shifts;
  - drafting a bridge option wrote to the chit;
  - a two-storey family "wanted a brick house".

Instinct-only A/B of the combined branch against the pre-merge head `2ff1cd6` (T10 setup):

| run | discoveries | era | population | starvations | projects done | useful buildings |
|---|---|---|---|---|---|---|
| direct, 12 seeds x 30 days | 22.3 → 37.6 | 5.5 → 6.4 | 59.2 → 55.0 | 0.2 → 0.0 | 9.7 | 6.9 |
| direct, 8 seeds x 60 days | 27.4 → 44.2 | 6.1 → 6.9 | 59.0 → 59.1 | 0.4 → 0.1 | 12.1 | 11.1 |
| no speech, 6 seeds x 30 days | 25.5 → 36.0 | 5.7 → 6.0 | 55.3 → 53.7 | 0 → 0 | 5.0 | 6.8 |

- **Population** grows more slowly early on: crowded homes have fewer children, and five of seven huts become
  longhouses. It reaches the cap by day 60.
- **Station output** falls by about a quarter (388 → 271 goods at 30 days), because chits are busier with the
  village's projects.

## Third pass (same day): ten ideas

Ten ideas were built on `53e4b11` in a scratch worktree. Each fix has a test that fails when the fix is switched off
(every one was checked that way). Afterwards they were independently reviewed for culture leaks and the experiment
contract. The review found no blockers, 3 should-fix issues and 6 nits, all fixed in 11c0b02.

| # | Idea | Commits | What it does | Tests |
|---|---|---|---|---|
| 1 | Outposts | c1fb1a4 | See row 8. | `test_outposts.py` (4) |
| 2 | Knowledge that outlives its keepers | e189ea7 | `sim/lore.py`. An old chit that is the last keeper of a skill passes it on the way its culture allows: it teaches the youngest where chits teach, writes a tablet where they write, and otherwise makes the thing where others can watch. A lost skill is told as "forgotten". The Progress panel lists the knowledge at risk. | `test_lore.py` (3) |
| 3 | A model chief chooses the project | 23baab2, 11c0b02 | See "Cheap scoring elsewhere" above. Only where chits talk and the chief thinks with a model. | `test_chief.py` (4) |
| 4 | Food security | 0554424, 11c0b02 | `sim/food.py` counts the days of food in the stockpiles a chit can see (never an outpost's store). Below 3 days the project waits and chits fill the stores. Models see the same line in their scene, and the Progress panel shows the village's days. | `test_food.py` (5) |
| 5 | Director's cut | 860dcf2, 11c0b02 | See "The X post" above. | `test_director_cut.py` (2) |
| 6 | Model scorecard | 30fe7df, 11c0b02 | `diag.scorecard`, `/api/scorecard` and a table in Stats compare the worlds side by side: era, discoveries, discoveries per 100 adopted decisions (a running count since the game started), model share, step success, escalations, latency and projects done. | `test_scorecard.py` (1) |
| 7 | Visible eras | 2f11032, 11c0b02 | See row 7. | `eras.test.ts` (4) |
| 8 | Lighter saves | 6f8d88f, 11c0b02 | A dead chit keeps 12 memories, 5 bonds and 5 lessons (with their sources), plus what it knew and its stats. Checkpoints use gzip level 1. On a copy of the live save, a checkpoint went from 10.8 to 6.8 MB and from 244 to 127 ms. | `test_saves.py` (2) |
| 9 | Family and knowledge trees | ec43836, 11c0b02 | `views.family` and `views.spread`, with `/api/worlds/{wid}/family/{aid}` and `/spread/{knowledge}`. The Inspector shows a family card; clicking a knowledge name opens how the village came to know it. | `test_family.py` (4) |
| 10 | Trade between the islands | e8f9177, 11c0b02 | Contact games only. A village with 20 or more of one good in store and a boat sends one trader at a time with 8. Abroad, `{"do":"trade","at":"stores"}` swaps the load for goods of no greater worth (at most 12), preferring things the trader has never had. It is a silent trade, so it works in any culture, and it eases hostility. The trader sails home in its boat, back to its old home under its old id, and the village keeps the boat. A village with a surplus and no boat builds one. | `test_trade_voyage.py` (4) |

The review found and fixed these:

- **Food gauge:** an outpost's store read as "the stores", so a camp worker saw 0 days with 200 bread at home.
- **Chief fallback:** when the chief's model never answered, need picked the project with no trace.
- **Scorecard:** it divided by a 5000-record window, so the ratio climbed as a game went on.
- **Smaller fixes:**
  - the trade wait wasn't saved;
  - ids coming home from the sea were stripped of every "-x";
  - a visitor's teacher was looked up among local ids;
  - dead chits' lesson sources cited trimmed memories;
  - a remade cut left old clips behind;
  - statues were tinted by position.

Instinct-only A/B against `53e4b11` (T10 setup: 128 map, 18 chits; no model, no contact):

| run | discoveries | era | population | starvations | stored food | useful buildings |
|---|---|---|---|---|---|---|
| direct, 12 seeds x 30 days | 37.6 → 37.9 | 6.42 → 6.42 | 55.0 → 56.8 | 0 → 0 | 458 → 554 | 6.9 → 8.1 |
| direct, 8 seeds x 60 days (before the review fixes) | 44.2 → 47.5 | 6.9 → 6.9 | 59.1 → 60.0 | 0.1 → 0.1 | 462 → 512 | 11.1 → 12.6 |
| no speech, 12 seeds x 30 days | 34.0 → 33.6 | 5.83 → 5.58 | 51.6 → 52.3 | 0 → 0 | 570 → 665 | 7.4 → 7.9 |
| no speech, 8 seeds x 60 days | 39.1 → 39.8 | 6.4 → 6.4 | 59.8 → 59.8 | 0 → 0 | 552 → 639 | 11.1 → 13.8 |

- **Food first has a cost in the silent world.** At day 30, 4 of 12 seeds are one age behind and 1 is one ahead.
  With food first switched off, the branch matches the base (34.4 discoveries, era 5.83). Before the review fixes,
  when the gauge also counted outpost stores, the cost was larger: era 6.0 → 5.2 on 6 seeds. By day 60 the gap
  is gone (8 seeds: era 6.4 → 6.4, discoveries 39.1 → 39.8), so the threshold stays at 3 days.
- **Some ideas don't show up in these runs.** Nothing was forgotten in any of them, trade needs contact, and camps
  were rare before day 60. Two 30-day rivals smoke runs (instinct, contact on) made 3 trade round trips between them, and the
  islands ended at peace.
- **The live save loads.** A copy (day 908, about 1,700 dead) loads with the new code in 4.7 s and steps a day on
  instinct.

## Fourth pass (same day): ten more ideas

The live worlds pointed at each of them. Both worlds had sat in the Iron Age for 600+ days with a forge nobody could
afford ("no copper ore anywhere nearby" 5,600 times), 60 chits in one village on a mostly empty island, chits covered
by instinct 27-58% of the time while their models were busy, and about 1,000 dead each.

| # | Idea | Commits | What it does | Tests |
|---|---|---|---|---|
| 1 | Stop the waiting | fba1d2a | A model whose replies take 12+ ticks is asked two steps before a plan runs out. The diagnostics say plainly that "waiting" is instinct keeping a chit busy. | `test_focus.py` |
| 2 | Break the Iron Age ceiling | ceeb6ae, d386a1d | It was an ore ceiling. A mine dug by rock or hills has a seam that fills with 4 ore a day (16 at most), and gathering ore uses it once the deposits near home are gone (with a pick). | `test_mine.py` (5) |
| 3 | Daughter villages | 4e00f08, a70a545, d386a1d | A village of 40 in a world that can talk sends 6 young adults to found a new village 35-70 tiles out. They light its fire and build their homes there, and it gets its own name. The world still holds 60 (the models' load is the same). | `test_pioneers.py` (9) |
| 4 | Prospectors | ece5a57 | `prospect` walks 40 tiles out, looks about 12 wide and comes home. Where chits talk, it tells the village where the ore is (a heard place counts); where they can't, only the prospector knows. Instinct sends one at a time, only when something needed is gone from around home. | `test_prospect.py` (3) |
| 5 | Spend the model where it matters | fba1d2a, d386a1d | A brain's "focus" (on by default, a checkbox in Brains): a plan that is only eating, sleeping or hauling is left to instinct, and the model's share is counted over the rest. Never in an experiment. | `test_focus.py` (5) |
| 6 | Great works | ddb9552 | A great library (study goes twice as far), a lighthouse (voyages take half the time; its lamp lights the coast) and an aqueduct (fields grow 30% faster and through a drought), each needing a big village. All can be a village project, and their sites show the building rising. | `test_great_works.py` (5) |
| 7 | Trade fairs | a288dee | In a versus game, 3 days every 30 when boats can cross, so island trade happens live. Boats at sea still land after it ends, and villages build their boat just before. | `test_fairs.py` (4) |
| 8 | Hall of ancestors | d327a64 | A biography for every chit that mattered, from its own record (firsts, inventions, elections, laws, teaching, children, its last reflection). People panel, "hall". | `test_hall.py` (3) |
| 9 | The story so far | c36a9c1, d386a1d | A recap for someone who has just arrived: the ages, the dead, what was forgotten (World A: iron), who is remembered, the laws, the storms and wolves, the rival island, who leads now. A count or a quote on every line. "📜 So far" in the Chronicle panel and on the welcome screen. | `test_recap.py` (4) |
| 10 | What-if forks | c3b0599, d386a1d | A copy of a world as it is now, stepping alongside it on instinct (or unable to talk), compared as the two drift apart. Play games only; at most 2; in memory. Stats, "What if...". | `test_forks.py` (4) |

An independent review found two blockers, both fixed in d386a1d with tests:

- **Pioneers almost never founded their village.** A hut by a chit with a home was refused, and "build a fire near
  the site" fed the fire beside the chit.
- **The site reached a silent world's pioneers without any speech.** Pioneers now need a world that can talk.

It also found two should-fix issues (the Focus checkbox did nothing, and the what-if's ✕ bypassed the access token)
and eight nits; all are fixed. The first A/B caught two more defects before that:

- births stopped in a full village, which cost 19 chits by day 30;
- a crash when a site candidate lay 8 tiles from the edge of the map.

Instinct-only A/B against `811498d` (the head before this pass; T10 setup: 128 map, 18 chits; no model, no contact):

| run | discoveries | era | population | starvations | stored copper | useful buildings |
|---|---|---|---|---|---|---|
| direct, 12 seeds x 30 days | 37.9 → 39.0 | 6.4 → 6.2 | 56.8 → 56.4 | not counted | 0.5 → 0.8 | 8.1 → 8.2 |
| no speech, 12 seeds x 30 days | 33.6 → 34.2 | 5.6 → 5.4 | 52.3 → 51.7 | not counted | 2.3 → 4.2 | 7.9 → 7.8 |
| direct, 8 seeds x 60 days | 46.2 → 55.8 | 6.9 → 7.0 | 59.9 → 58.5 | not counted | 0.4 → 6.5 | 13.9 → 13.6 |
| no speech, 8 seeds x 60 days | 39.8 → 43.8 | 6.4 → 6.5 | 59.8 → 59.6 | not counted | 0.8 → 9.5 | 13.8 → 13.5 |

By day 60 the mines have put copper in the stores (0.4 → 6.5 with speech, 0.8 → 9.5 without) and discoveries are
up (46.2 → 55.8 with speech, 39.8 → 43.8 without). At 30 days the pass costs a little: the era is 0.2 lower on
average with and without speech, and the population 0.4-0.6 lower. Goods made in workshops fell at 60 days (888 → 781
with speech, 1,329 → 1,007 without), a cost to watch: time went to digging, prospecting, pioneering and great works
instead, though this A/B doesn't show which. Starvations are not counted: the sweep reads them from the world's event
log, which keeps only the last 4,000 events and a 60-day run outgrows it.

## Fifth pass (2026-09-30): spreading out

An audit of the live worlds at day 1,361 found both living in one village on a few percent of the 512 island. Its
findings and the fixes, all on `feat/expansion`:

| Finding (live worlds, day 1,361) | Fix | Tests |
|---|---|---|
| The world held 60 chits; at the cap every child was born in the big village; all 6 daughter villages died with their founders | 90 chits on islands of 256+ (small islands keep 60, as the plan's invariants hold them); smallest villages have their children first; a village of 50 has none while another has room; pioneers are under 30 and leave as couples first | `test_expansion.py` |
| World B's model-minded pioneers founded 1 village in 14 tries | a pioneer's duty comes before its model's plans (not in experiments) | same |
| All 780 ore deposits lie on rock; World A had none it could reach within 120 tiles | a mine tunnels one rock tile a day towards ore within 3 tiles (40 per mine); tunnels are walkable, drawn as roads, saved | same |
| Sand near home ran out ("no sand anywhere nearby" was World A's commonest failure) | a mill grinds up to 4 stone a day into sand while the stockpiles around it hold under 8; a fed, rested chit fetches a scarce material from where it remembers it (up to 80 tiles, a few at a time) | same |
| 54 "I need a pick" failures a week | instinct gets or makes a pick first; a model's plan that digs ore gets the pick steps first; a chit that can't get one plans as before | same |
| Nobody picked anything up in a week: god-mode gifts and meteorites lay untouched; one pile held 570 charcoal and 19 copper | a curious chit picks up and studies a strange object; loose goods are carried into a store with room and used by the supply planner; full stockpiles: build another (at most 5) or rebuild the fullest as a **warehouse** (4x the room, keeps its goods) | same |

Every mechanism has a test that fails when it is switched off (mutation-checked).

Instinct-only A/B against `main` (`38cbee2`), before the warehouse:

| run | discoveries | era | population | stored copper | stored iron | useful buildings | food stored | villages | tunnels | loose goods | starvations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 12 seeds x 30 days, 128 map | 39.0 → 39.7 | 6.2 → 6.4 | 56.4 → 56.8 | 0.8 → 4.8 | 0.2 → 0.8 | 8.2 → 8.0 | 594 → 545 | 1.6 → 1.9 | 0 → 6.8 | 890 → 882 | 0 → 0.2 |
| 8 seeds x 60 days, 128 map | 55.8 → 55.5 | 7.0 → 7.2 | 58.5 → 57.9 | 6.5 → 8.9 | 0.8 → 2.9 | 13.6 → 14.6 | 497 → 517 | 2.9 → 3.0 | 0 → 24.9 | 1,060 → 922 | 0 → 0.4 |
| 8 seeds x 60 days, 256 map | 51.9 → 54.2 | 7.0 → 7.1 | 59.6 → 67.6 | 8.8 → 9.4 | 1.6 → 1.0 | 17.5 → 16.6 | 488 → 594 | 3.1 → 3.5 | 0 → 23.9 | 1,159 → 1,354 | 0 → 0.4 |

Starvations are counted from the last 4,000 events only. A new cost to watch: about 0.4 per world by day 60 (none
before). The research layer that comes next is planned in `docs/RESEARCH_PLAN_2026-09-30.md`.

## What this means for the next slice

In order of value:

1. Watch the models play it. The chief's choice, focus, the mines, the prospector's verb, fairs and trade have only
   run with instinct and fake models.
2. Is there a Machine Age now? Mines put copper in the stores; the next question is whether a forge, steel, gears
   and a steam engine follow in a long run.
3. The rest of row 4 (dock, walls) and row 5 (plough, books, visible lantern light).
4. One-token scoring for elections and trades, and Invention 2.0 composition (row 10).
