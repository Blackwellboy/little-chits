# Research layer plan (2026-09-30)

Source: a review of Microsoft TinyTroupe, Turing Experiments and AnthropomorphicIntelligence (PersonaArena,
LearnArena, MotiveBench, SocialCC, Proact-VL, PCC, HumanLLM) against Little Chits after PR #6. Its conclusion, which
this plan keeps: **don't copy their world architecture; mine them for the research layer around the simulation.**

The review's claims about those repositories were not re-checked here; the numbers below match its list so none is
dropped. Two corrections to it: "Mirai" is not a separate model (World A's `qwen3.8-s` is Mirai's compressed
Qwen3.8-27B-S), and no GLM model is in the current fleet. They are placeholders for "model A / model B".

## Guardrails that apply to everything below

- The simulator stays authoritative. Judges, normalizers, propositions and fingerprints are **read-only analysis**:
  nothing they produce feeds back into a chit or the world.
- Experiment mode (the strict contract) keeps its promise: the model decides; only frozen, deterministic
  syntax/schema repair. No semantic critic, no instinct stand-in, no cached replies unless the run is declared a
  deterministic replay (and the manifest says so).
- Raw emergent text (beliefs, laws, ambitions, invention names) is never overwritten; any clustering is a separate
  layer that points back to it.
- No modern-human personas. Temperaments only, and only as initial conditions or real inheritance.
- Every experiment is pre-registered: manifest (models, seeds, days, treatment, interventions, metrics, code commit)
  written before the first tick.
- Real-model runs on the cards need the owner's go-ahead (the 5090 is often in use).

## The 38 ideas, where each lands

| # | Idea | In Little Chits | Phase | Status |
|---|---|---|---|---|
| 1 | Experiment Lab | `chits/lab/`: YAML manifest → runs every seed × model × treatment, persists per-run manifests, resumes interrupted batches, collects results, builds a comparison pack | 1 | planned |
| 1a | Statistics | means + medians, bootstrap CIs, effect sizes, per-seed paired differences, Mann-Whitney where suitable, time-to-event (first copper, first settlement, extinction), distribution plots | 1 | planned |
| 2 | Blind model labels | analysis sees "Model A/B" until the report is frozen; the model→world-slot mapping is randomised per seed and stored sealed in the manifest | 1 | planned |
| 3 | Chit Validation Chamber | 12 deterministic micro-worlds on the real simulator (full inventory, cold night, missing prerequisite, broken construction, told recipe, observed technique, stranger arrives, scarce food, failed invention, conflicting goals, trade offer, repeated failed action) → a capability profile per model | 2 | planned |
| 4 | No semantic action correction in experiments | play mode may use an optional critic; experiment mode only frozen syntax repair; an observer-side quality score (coherence, consistency, repetition, grounding, social fit) never reaches the chit | 1 (guardrail), 5 (score) | planned |
| 5 | Behavioural health metrics | automatic diagnostics: `REPEATED_FAILURE_WITHOUT_ADAPTATION`, `OBJECTIVE_CHURN`, `UNGROUNDED_PLAN_REFERENCE`, plus plan coherence, knowledge grounding, social coherence | 2 | started: repeated failure (item 41) |
| 6 | Episodic + semantic memory hierarchy | recent episodic → episode summaries → semantic facts → procedural knowledge, each compressed item carrying source memory ids | 3 | planned |
| 7 | Consolidation, not trimming | ageing memories grouped into named episodes ("The First Winter") with sources kept in history; feeds the Hall of Ancestors | 3 | planned |
| 8 | PCC-style context compression | later research lane: a local chit-memory compressor ("500 days in a few thousand effective tokens"), only after 6-7 | 7 | later |
| 9 | Population / genome factory | stratified temperament genomes (curiosity, sociability, risk, patience, novelty, persistence, cooperativeness, exploration) so twin worlds start with identical distributions; a profiler proves it | 4 | planned |
| 10 | Heritable fragments | temperament and cultural fragments only as initial experimental conditions or through real inheritance, never injected mid-run | 4 | planned |
| 11 | Results extractor / reducer | one analysis layer: world archive → fact reducers → run dataset (tidy per-day table) → cross-run dataset → report | 1 | planned |
| 12 | Normaliser for emergent text | offline clustering of beliefs, ambitions, laws, inventions into themes for cross-run analysis; raw text stays authoritative | 5 | planned |
| 13 | Propositions / monitors | deterministic facts first (`knowledge_was_actually_delivered`, `project_has_multiple_verified_contributors`, `invention_was_used_successfully`, ...); a judge only for the genuinely interpretive ones | 5 | **started:** `lab/propositions.py` emits evidence-backed delivered/proven knowledge, multi-contributor projects and physically existing inventions; it explicitly refuses the unsupported successful-use claim until effect-use provenance exists |
| 14 | Intervention DSL | pre-registered, timestamped interventions (`at_day`, `when: population_gte`), identical across treatment worlds, stored in the manifest; separate from god mode and the storyteller | 4 | planned |
| 15 | Civilization Experiments | commons dilemma, barter/ultimatum, scarcity, information diffusion, rumour accuracy, collective action, leadership choice, explore/exploit, reciprocity, tool adoption, newcomers, innovation diffusion | 4 | planned |
| 16 | Distortions and fingerprints | per-model behavioural fingerprint across many seeds (exploration, cooperation, risk, sharing, conflict, innovation reuse, goal persistence) instead of "best model" | 4 | planned |
| 17 | Alien Physics mode | renamed materials, permuted properties, changed recipes and some changed causal rules, so pretrained human technology can't be recalled | 4 | planned |
| 18 | Learning Arena | instructor (taught) vs concept (tablet) vs experience (own trial), then the same later challenge: success rate, attempts to success, transfer to an altered task, retention after N days | 2 | planned |
| 19 | Learning curves | `attempt_number → success / efficiency / errors` for repeated tasks, not just endpoints | 2 | planned |
| 20 | Relevance-based retrieval | retrieve the most relevant past experiences for the situation, log `memory id + relevance`, then check (with F7 citations) whether the model used them | 3 | planned |
| 21 | Motivation diagnostics | classify expressed objectives afterwards (survival, curiosity, affiliation, status, family, community project, ambition, exploration, fear) and compare models; never scripted | 5 | planned |
| 22 | Independent judge layer | 2-3 judges score trajectories (grounding, objective coherence, adaptability, social coherence, learning, novelty, physical reasoning); disagreement recorded | 5 | planned |
| 23 | Multi-judge debate | judge A + judge B + skeptic on one evidence bundle → evidence, counterargument, confidence; qualitative only | 5 | planned |
| 24 | Endogenous cultural adaptation | a stranger from village B enters village A's evolved culture (belief, ownership norm, greeting, trade norm, law, taboo): notices, infers, adapts, violates, learns after correction? | 4 | planned |
| 25 | Knows vs acts | separate `KNOWS_NORM` from `ACTED_IN_ACCORDANCE_WITH_NORM` (e.g. knows the winter-sharing law, still hoards when hungry) | 4 | planned |
| 26 | Proactive narrator metrics | director/narrator scored on moment precision, moment recall, latency, silence discipline, redundancy, grounded-claim rate | 5 | planned |
| 27 | Vision-grounded chits | optional mode: a rendered crop of the surroundings instead of the text scene; same model, text vs vision | 6 | later |
| 28 | Civilization profile page | initial traits, skills, jobs, beliefs, ages, families, objectives, knowledge ownership, renown, settlements, and how twin worlds diverge | 4 | planned |
| 29 | Compute efficiency | per civilization: tokens/day, tokens per strategic decision, tokens per discovery, GPU-seconds, wall time, requests, repair rate, successful actions per 1k tokens | 1 | planned |
| 30 | Controlled fork experiments | formalise what-if forks: run to day N, freeze, fork into treatment arms (speech on/off, drought/none) from the identical history | 4 | planned |
| 31 | LLM-call caching | development and tests only; off in experiments unless declared a deterministic replay, and recorded | 1 | planned |
| 32 | Scenario generator | a model drafts physically valid validation scenarios; mechanically validated, then frozen as a suite | 2 | planned |
| 33 | Trajectory dataset | export observation → objective → decision → outcomes → later effects for every meaningful model decision | 6 | planned |
| 34 | ChitBrain | future: a specialist model fine-tuned on quality-controlled trajectories, benchmarked against its base with held-out physics and tasks (guard against self-training collapse) | 7 | later |
| 35 | Separate dimensions | never one civilization score: innovator, social learner, survivor, planner, speed, coherence kept apart | 5 | planned |
| 36 | Empirical validation where it fits | compare diffusion curves, sharing, reciprocity, risk, collective action with known qualitative patterns, only to find distortions | 5 | planned |
| 37 | Human-baseline micro experiments | some Validation Chamber scenarios playable by a person in the browser; humans vs models on the same embodied problem | 6 | later |
| 38 | Multidimensional leaderboard | local-model table by survival, adaptation, innovation, learning, social, grounding, speed | 5 | planned |

## What stays as it is (the review agrees these are already ahead)

Authoritative physical simulation; embodied needs, resources and tools; persistent multi-generation world; emergent
construction and settlements; material prerequisites; local knowledge diffusion; verified knowledge lineage; play vs
experiment separation; per-decision provenance; timeline/epoch identity; bounded real-time observer transport;
historical replay; the evidence-grounded Chronicle; the world-first viewer; interventions that physically affect the
world; civilization progression.

## Phases

1. **Measurement core** (1, 1a, 2, 4 guardrail, 11, 29, 31): the Experiment Lab. After this, every other feature is
   measurable. Instinct-only batches need no GPU; model batches need the owner's go-ahead.
2. **Capability suites** (3, 5, 18, 19, 32): Validation Chamber, behavioural health, Learning Arena with curves.
3. **Memory** (6, 7, 20): hierarchy, consolidation, relevance retrieval with citations.
4. **Science designs** (9, 10, 14, 15, 16, 17, 24, 25, 28, 30): interventions, controlled forks, Chit Experiments,
   fingerprints, Alien Physics, cultural adaptation, genome factory, profile page.
5. **Interpretation** (4 score, 12, 13, 21, 22, 23, 26, 35, 36, 38): read-only judges and normalisers, narrator
   metrics, multidimensional leaderboard.
6. **Data and new modes** (27, 33, 37): trajectory export, vision-grounded chits, human baselines.
7. **Later research** (8, 34): memory compression, ChitBrain.

The review's headline benchmark, the **Alien Civilization Learning Benchmark**, is phases 1 + 2 + 4 together:
Alien Physics (17) × Learning Arena (18, 19) × Experiment Lab (1, 2) over 20-50 seeds, tracking whether knowledge is
acquired → retained → referenced → executed → physically succeeds → transfers → spreads.

---

# Addendum: Worldview Genesis and the research platform (second review, same day)

A second, earlier review (prompted by a commenter's "starting religions over centuries" idea) adds a generic
**Worldview Genesis** laboratory and a sharper research roadmap (R0-R16). Everything in it is listed here; items that
repeat the first list point to their number above.

## New items (39 onward)

| # | Idea | In Little Chits | Phase |
|---|---|---|---|
| 39 | BrainTape | record request hash, exact observation, model identity, sampling, response, parsed plan; replay a run with the same brain output to tell physics/code changes from model randomness (development/replay only in experiments, see 31) | R2 |
| 40 | Bounded action repair | a model's impossible action → the simulator's exact reason → one bounded repair turn by the same model → both attempts recorded (pre-registered for experiments, never a semantic critic, see 4) | R2 |
| 41 | Loop detector | formal repeated-plan detector: in play it can trigger a rethink; in experiments it records, and only a pre-registered repair acts (see 5) | R2 |
| 42 | InvariantMonitor | hard gates (abort) and soft diagnostics: no experiment fallback, no cross-world leakage, no negative inventory, no treatment touching physics, no unsupported "learned" claim, no narrator feedback, conversion only after exposure, no inherited beliefs, no duplicate physical effect (see 13) | R3 |
| 43 | Fair cognition scheduler | strategic calls round-robin across worlds/treatments; equal strategic-opportunity budgets; per-request seeds where the backend allows; records opportunities, requests, plans, tokens, latency, retries | R1 |
| 44 | Simultaneous cognition rounds | in experiments, resolve model calls in rounds so a faster-returning call gains no simulation-order advantage | R1 |
| 45 | GPU energy | optional joules per sim-day from NVIDIA telemetry, beside tokens and latency (see 29) | R1 |
| 46 | TreatmentPack | generic schema (id, version, sources with citation/edition/licence, claims with source ids and category, practices, founder distribution, scope note, reviewer notes) + a linter + coverage/token report; a treatment only changes what founders know | R1 |
| 47 | N-way blinded, balanced assignment | treatments A-K randomised to world slots per seed, balanced over seed blocks so every treatment occupies every slot (see 2) | R1 |
| 48 | Matched exogenous schedule | the same drought/disease/contact at the same time in every treatment world (see 14) | R1 |
| 49 | CLI | `chits experiment run protocol.yaml`, `resume RUN_ID`, `analyze RUN_ID`, `aggregate family/` (see 1) | R1 |
| 50 | Strict worldview contract | beliefs give no mood/affinity/shrine bonus; prayer, preaching and reading don't auto-convert; children don't inherit beliefs; no automatic last-keeper rescue; library research can't read the hidden recipe table (`closed_knowledge`); scripted T26 elections off when institutions should emerge. All kept in play | R8 |
| 51 | Belief model | `BeliefClaim` (text, source claims, origin, created by/when, exposure source, status heard/considered/affirmed/questioned/rejected), `BeliefExposure`, `BeliefDecision`, `Affiliation`, `ConversionEvent`, `RejectionEvent`; the simulator never adjudicates metaphysics; narration says "they believe X" | R8 |
| 52 | Text and teaching lineage | texts with content hash + parent hash; quote/copy (high fidelity) vs retell/reinterpret (derived claim); doctrinal drift measured, never a scripted mutation rate | R8 |
| 53 | Groups from agent actions | `found_group`, `join_group`, `leave_group`, `write_charter`, `teach_claim`, `reinterpret_claim`, `challenge_claim`; denominations and syncretic traditions only when agents found them; lineage tracked | R8 |
| 54 | Tradition states | active / dormant (texts survive) / lost / revived, for traditions and for knowledge | R8 |
| 55 | Institution 2.0 | agent-created Group, Charter, Office, Membership, Proposal, Norm/Law, Decision rule; institutions described only by their adopted rules (never "democracy" from a schedule); current T26 stays in play | R7 |
| 56 | Religion as ordinary physical/social action | pray, gather, ritual, preach, teach, write, read, copy, build shrine/temple, debate: meeting places, text storage, labour, co-location, and no hidden bonus unless that is itself a treatment | R8 |
| 57 | Founder bottleneck | 2 keepers with the full teachings + N ordinary founders with the basics, identical in every treatment world; a saturated variant as a separate treatment | R8 |
| 58 | Pretraining contamination modes | `named` / `blinded_content` / `synthetic`; controls: neutral, name-only, content-only, name+content, synthetic; state plainly that model priors can't be erased | R16 |
| 59 | Technology-prior defence | a model's hypothesis ("heat red rock with charcoal") stays a hypothesis until the simulator produces the result; track attempts to invoke unacquired concepts (see 17) | R6 |
| 60 | WorldGraph | generalise World A/B to N full worlds with explicit sea routes; an 11-node ring with identical terrain/resources/coast/route degree; natural contact vs fixed contact year; every cross-world transfer (trade, migration, intermarriage, teaching, texts, inventions, conversion, conflict, treaty) an explicit recorded event | R9 |
| 61 | Deep-time scaling | strategic cognition only for goals, invention, institutions, worldview, migration, projects, preservation, diplomacy, trade, conflict, novel evidence; an identical deterministic routine body for the rest (the simulation body, not a fallback); cascade/one-token choices; generational archive, cold snapshots, dead-agent compaction; a 2,000-year mock run with bounded memory | R11 |
| 62 | Memory pyramid (full) | tier 0 raw → 1 important episodes → 2 cited life chapters → 3 semantic/procedural → 4 beliefs and worldview claims → 5 lineage (parents, teachers, institutions, texts); retrieval by relevance + recency + importance + current objective (see 6, 7, 20) | R5 |
| 63 | ChitLab additions | motivation scenarios where nobody commands the obvious (winter in 20 days, an elder's unique knowledge, a lost child, a ruin, falling food, a neighbour's resource); wisdom-of-crowds estimates; five-generation transmission chains; SocialCC-style fictional cultures (see 15, 18, 21, 24) | R6 |
| 64 | Two read-only commentary channels | Storyteller and Analyst, both evidence-grounded and one-way (see 26) | R14 |
| 65 | Civilization Atlas | 11-world view: territories, population, age, self-declared worldview, contact/migration/trade routes; belief tree, scripture tree, knowledge-flow graph, institution timeline, generation slider, "what remains of the founders?" (see 28) | R13 |
| 66 | Invention 3.0 | compositional physics: material properties (hardness, toughness, elasticity, density, heat resistance, conductivity, flammability, water resistance) × shapes (edge, point, vessel, wheel, beam, sheet, rope, tube) × mechanisms (lever, axle, gear, pulley, spring, flow, combustion, heat exchange) → measured affordances, instead of named purpose buckets | R12 |
| 67 | Dataset QC pipeline | raw → episode slicing → contamination filtering → quality control → SFT-ready records; a trained ChitBrain never used when benchmarking general models (see 33, 34) | R15 |
| 68 | Owner request: building upgrades and warehouses | stockpile → warehouse (bigger, rebuilt in place keeping its goods) like hut → two-storey house; instinct upgrades the fullest store instead of dropping loads | now |
| 69 | Owner request: model-proposed building improvements | a chit proposes an improvement to a building type from its own knowledge; the world judges it by materials into measured effects (capacity, spoilage, work speed, warmth); the first step towards 66 for buildings | R12 |

## Acceptance gates before calling anything research-ready

A treatment isolation (physics never reads `worldview_id`) · B no magic religion effect (same BrainTape, different
pack → identical physics) · C a newborn has no worldview without exposure · D exposure ≠ conversion · E the last
keeper can die and knowledge really disappears · F every copied/reinterpreted text traces to its parent · G no
cross-world state moves without a recorded transfer · H analysis runs on treatments A-K blind · I equal strategic
opportunity budgets · J a 2,000-year mock run stays bounded · K BrainTape replay reconstructs a bounded run ·
L narrator output can't reach memory, beliefs, prompts, rewards or physics · plus checkpoints preserve all lineages
and RNG state.

## Explicitly not doing

No return to the old v1/R1-R11 architecture; no edits to the frozen `plan/`; no religions hard-coded into
`sim/world.py`; no hidden bonuses; no conversion from proximity; no inherited religion; no scheduled election called
emergent democracy; no library oracle in closed-knowledge runs; no automatic rescue of dying knowledge in strict
history runs; no claim that model priors are erased; no "which religion won"; no judge or narrator influence; no real
worldview packs written from model memory (sourced, licensed, reviewed packs only, after synthetic packs pass); no
real GPU experiments without the owner's go-ahead; no major research work merged to main before owner review.

## Build order (both reviews combined)

- **R0** baseline docs (this file), CURRENT/HANDOFF refresh.
- **R1** experiment kernel: ExperimentSpec, TreatmentPack + linter, manifests, blinded N-way balanced assignment,
  matched intervention schedule, fair scheduler, resumable batch runner + CLI, per-run result dirs, compute accounting
  (1, 1a, 2, 11, 14, 29, 31, 43-49).
- **R2** BrainTape + replay, bounded action repair, loop detection (39-41, 4, 5).
- **R3** InvariantMonitor / propositions (42, 13).
- **R4** results framework: extractor → reducer → aggregator → reporter, JSONL/CSV/Markdown (11, 1a).
- **R5** memory pyramid with source ids (6, 7, 20, 62).
- **R6** ChitLab: validation chamber, learning arena, motivation, transmission, bargaining, cultural adaptation,
  novel-material discovery (3, 18, 19, 21, 24, 25, 32, 59, 63).
- **R7** institution substrate (55). **R8** worldview engine (50-54, 56, 57). **R9** WorldGraph (60).
- **R10** Worldview Genesis prototype with synthetic packs, 11 mirrored worlds, 3-5 seeds.
- **R11** deep-time scaling (61). **R12** Invention 3.0 incl. building improvements (66, 69).
- **R13** Civilization Atlas (65, 28). **R14** proactive narrator + analyst (26, 64).
- **R15** real worldview content pipeline (sourced packs), dataset QC (33, 67). **R16** controls + pre-registered
  multi-seed run (58, 16, 38).
- Later research lanes: 8, 27, 34, 37.

## Progress

- **R1, first slice (branch `feat/lab`):** `server/chits/lab/`: protocols (JSON, or YAML with PyYAML), validation,
  pre-registration (manifest with fingerprint and code commit), blind labels with a sealed assignment and a rotating
  run order (every arm takes every slot), resumable runs (atomic results; a changed protocol can't resume a
  directory), parallel workers, matched interventions (drought, storm, snow, rain, hard winter, ore shortage) on the
  same day in every arm, a tidy per-day table, and a blind-by-default report (bootstrap intervals, per-seed paired
  differences, Cliff's delta, Mann-Whitney, Kaplan-Meier time-to-event) with CSV exports. Items 1, 1a, 2, 11 (first
  reducer), 14/48 (first interventions), 47, 49. Example: `docs/protocols/speech-vs-silence.json` and its report,
  `docs/research/lab-example-speech-vs-silence.md`.
- **R1, compute accounting (item 29):** every `make experiment` summary has a `compute` block per world and the
  report a "What the thinking cost" table: tokens (the server's own counts, every call), tokens per day, per adopted
  plan and per discovery, requests, failed requests and retries, request seconds, the repair rate, and the model's
  steps done (and their success rate) per 1k tokens. The report also stopped calling a versus run "World B can only
  watch".
- **R1, fair cognition (item 43):** lockstep (above) already makes a faster card's answers land on the same tick as
  a slower one's, so request order and speed don't change the world. Added: every experiment request carries a
  sampling seed made from the run's seed and the exact prompt (`request_seeds` in the manifest; `--no-request-seeds`
  to turn it off; a brain's own fixed seed wins), so the same question samples the same way on llama.cpp and vLLM.
  Not done: capping each world's strategic calls to an equal budget. That would change behaviour and needs a
  pre-registered design.
- **R1, TreatmentPack (item 46):** `server/chits/lab/treatment.py`. A pack holds sources (citation, edition,
  licence), claims (text, category, cited sources), practices (recipes and designs the simulator already has), the
  share of founders told, a scope note and reviewer notes. `python -m chits.lab lint PACK` reports every problem and
  what the pack covers (claims by category, sources cited, estimated tokens per founder). The linter refuses any field
  that isn't knowledge (inventories, flags, physics), practices the simulator doesn't have, uncited or unlicensed
  claims, and over-long claims. A protocol names packs in `treatments` (inline or by path, read in so the
  fingerprint covers their content), and an arm carries one with `treatment`. The seeded share of founders learn
  the practices (as told, with the pack as source) and remember the claims before the first tick. The manifest
  holds each pack's coverage. Who was told goes to `runs/*/treatment.json`, apart from what the blind report reads.
  Example: `docs/protocols/told-stone-tools.json` with `treatments/stone-tools.json` (synthetic), 12 seeds × 30
  days, report in `docs/research/lab-example-told-stone-tools.md`: the told village reaches 20 discoveries sooner
  (median day 3 against 5), and the untold one catches up within the month.
- **Fix (BrainTape, found by CI):** a lockstep experiment now answers the last tick's model calls before it closes.
  Cancelled half-way, a recording lost the calls still on the wire, while a replay answered them from the tape at
  once and missed. Whether any call landed on the last tick depended on the fake model's call count, so it failed
  only in some test orders; it is reproduced and pinned in the test.
- **R1, model arms:** `chits.lab` protocols can seal exact brain configs in `protocol.brains`; model arms require both
  `allow_models: true` and `CHITS_LAB_ALLOW_MODELS=1`, then run strict + lockstep with seeded requests and the same
  per-tick invariant gate. Literal API keys are refused; use `env:NAME`. The sealed config changes the protocol
  fingerprint, so a changed model/config cannot resume an old run.
- **R1, identical settings (item 71):** model arms are rejected unless every behavior-affecting BrainConfig field
  matches (concurrency, timeout, temperature, token budget, JSON/thinking mode, sampling/extra body, prompt style,
  cascade thresholds/share and focus). Model identity/routing may differ. The manifest also pins prompt version.
  Still to do in R1: paired card swaps (72), GPU energy (45), and a pre-registered equal strategic-call budget.
- **R3, InvariantMonitor (item 42, first slice):** `server/chits/invariants.py`. Hard: negative stock in hands or
  stores; knowledge marked proven with no tick it was proven on; knowledge that came by no known way; in the
  experiment contract, a chit thinking with a brain its world wasn't given, and a model's chit acting on an instinct
  plan. Soft: loops (item 41). `make experiment` checks every world each day and stops on a hard break (its report
  opens with "Stopped ... Nothing below is a result"); the lab stops the batch (exit 3, no result written); the live
  diagnostics only report them (`invariants` per world). Its first run on a copy of the live save found 216 chits
  whose starting knowledge (hut, campfire) was marked proven with no tick: new chits got no status at birth, and a
  reload filled in "worked" without one. Fixed at birth and on load (only where the way it was learned proves it).
  Still to come with the worldview engine (R8): conversion only after exposure, no inherited beliefs, no narrator
  feedback.
- **Live fix (found by the loop detector on its first day live):** World B's instinct planned "craft charcoal" for
  its copper with no kiln in reach, 590 failures in 8 minutes. Instinct now treats an input made at a station out
  of reach as one it can't make, on every path that plans crafts (the reach is the action's own, 45 tiles). A 12-seed
  × 30-day A/B against `main` (instinct only): neutral (discoveries 42.2 → 42.4, population 56.2 → 56.6, homes 17.1
  → 17.7; seed 4 worse, seeds 7, 42 and 99 better).
- **R2, BrainTape (item 39, with 31 and 44):** `server/chits/brain/tape.py`. `make experiment ARGS="--tape FILE"` records
  every model call (a hash of the brain, the exact messages and the sampling; the reply; a failed call's error), and
  `--replay FILE` answers the same calls from the tape, so a rerun tells a code or physics change from model
  randomness. A replay that asks something the tape never saw stops with `TapeMiss` (the run has diverged); a call
  that failed when recorded fails the same way. Experiments now run **lockstep** by default: the world waits for
  every outstanding model call before the next tick, so how fast a card answers can't change what the world looks
  like when the next chit asks (item 44 for `make experiment`; `--no-lockstep` keeps the old wall-clock pacing).
  Without lockstep a replay diverged after a few hundred calls; with it, a recorded day replays exactly.
- **R2, loop detector (item 41, the first of item 5's metrics):** the same step (verb and object) failing for the
  same reason 4 times in a row is a loop, counted by who planned it (a model's plans, instinct, a reflex) in
  `/api/diagnostics` (`loops`, `loop_examples`), with a warning when a model's plans loop 5 times. In play the chit's next
  prompt says so and asks for something different; in an experiment the loop is only recorded. (Diagnostics no
  longer carry over to a new world that reuses a freed world's memory address.)
- **R2, bounded action repair (item 40):** when a step from a model's plan fails, that chit's next request to the
  same model adds the simulator's exact reason and the rest of the plan that was dropped, and asks for a plan that
  can work from here. Once per failure: a repaired plan (`model_repaired` in the step log) that fails gets no second
  repair, and a note older than a plan's staleness limit is dropped. Both attempts are on record: the repair's
  decision has `style: "repair"`, `repair_of` (the failed plan's decision), `repair_step` and `repair_reason`.
  Nothing judges the plan. On in play; an experiment has it only when declared (`--repair`, recorded in the
  manifest). With the fake model server, a 1-day run made 5 repairs in 56 decisions with it on, 0 with it off.
- **R1, model arms ready for a first study (items 29, 39, 43, 72):** `make lab` runs the Lab from the repository
  root. Model arms send the same explicit sampling as `make experiment` (a brain's own `extra_body` wins), record a
  BrainTape per run (`runs/*/tape.jsonl`), and report thinking opportunities per chit-day (`requests_per_chit_day`,
  `waiting_share`, `wait_seconds_per_chit_day`, `model_step_share`; a "Thinking opportunities" table in the report), reported and never
  equalised. `starved` joins every run's row. `card_swap` (paired card swaps, item 72) runs each model on its other
  card on every other seed. `--url BRAIN=URL` sets a server at run time, sealed in the manifest. Every server is
  checked before a run, and must answer and list the brain's `model`. Which server answered goes to
  `runs/*/server.json`, apart from the blind result. First study: `docs/protocols/jevk5-vs-gemma.json`; how to run
  it, and how to serve two models on one card: `docs/research/lab-model-vs-model.md`. Not done: replaying a Lab run
  from its tape, and an equal-budget cap.

## From an outside code review (2026-09-30)

A collaborator's model agent read the code. Every claim was checked; the bugs are fixed on `fix/review-notes`.

Fixed:
- `make experiment` compared two cultures as well as two models: the command line now defaults to `--mode versus`
  (both worlds can talk); `--mode culture` keeps the old design. (`run_experiment()` itself keeps the old default,
  which the frozen T15 acceptance test relies on.)
- Both models in `make experiment` get the same explicit sampling (`top_p`, `top_k`, `min_p`), since vLLM and
  llama.cpp default differently; the run's manifest records the mode and the sampling.
- `extra_body` was merged shallowly, so a user's `chat_template_kwargs` silently dropped `enable_thinking: false`;
  dicts now merge.
- An empty `content` with reasoning cut off at the length limit was parsed as the plan; it is now counted
  (`cut_off`) and not used. (A finished reasoning answer is still used, and one-token choices, which always stop at the
  limit, are unaffected.)
- Which code ran which days: every start on a different commit records the commit and each world's day
  (`code_stretches` in `/api/run`); the manifest also shows each brain's focus and extra sampling.

New items:

| # | Idea | In Little Chits | Phase |
|---|---|---|---|
| 70 | Speed must not leak into model comparisons | the live game runs with pacing off and a brain's focus on, so instinct covers a slow model's chits (the 5090's model thinks longer, so World A likely got more instinct plans). Report model share per world with every comparison; compare with pacing on and focus off (the lab's model arms and `make experiment` run strict, where instinct never stands in) | R1 |
| 71 | Identical settings across arms | same `escalate_below`/`escalate_share`, same explicit sampling, same prompt version, per-stretch commit log; the live islands had per-card cascade settings and mid-run upgrades | R1 |
| 72 | Paired seeds with card swaps | the 20-run design: pair seeds, and on half of them swap which card runs which model; report the per-seed differences and their spread, not just the mean (lab model arms, after R2) | R1/R2 |
| 73 | Bench v2 | at least 3 repeats with the spread; score by playing each plan forward N ticks and checking that needs and steps improved, not by valid JSON (45%) and the use of "experiment"/"social" verbs; 12 scenes is too few (one scene = 3.75 points); send scenes so server-side queueing isn't counted as latency (client queue time is already separate). Folds into the Validation Chamber (3) | R6 |


### R3 proposition monitor — first slice (2026-10-01)

`server/chits/lab/propositions.py` is a read-only reducer included in every Lab run summary. It emits only facts the
simulator can point back to: delivered knowledge with channel/tick/source, knowledge proven by physical success,
completed projects with at least two recorded contributors, and inventions with physical manufacture/holding evidence.
It deliberately lists `invention_was_used_successfully` as unsupported: v2 does not yet record a generic effect-use
event for every invention, so the research layer must not infer that claim. Tests prove the reducer does not mutate
the world. This starts item 13; interpretive judges and effect-use provenance remain open.


### R4 persistent results reducer — first complete dataset slice (2026-10-01)

F6's saved `World.tallies` are now exposed by `lab.extract.lifetime()` and exported by every comparison pack as
`lifetime-{blind|unblinded}.csv`: one row per run, every event counter the simulator persisted, plus `since_tick`,
`through_tick` and `complete_from_start`. Fresh Lab worlds therefore have honest whole-run totals from tick 0;
a migrated legacy world can never be mistaken for complete history. This fills the persistent reducer/cross-run
dataset gap in item 11/R4; the existing `runs-*.csv` remains endpoint state and `daily-*.csv` remains the tidy
time series.
