# The model-testing programme

Little Chits as a small-model civilisation benchmark: which local minds build what, and at what thinking cost. Nothing here is a finding yet. This is the plan the findings will come from.

## Rules of evidence

- **Only the Lab decides.** That means a pre-registered protocol with the same world rules and culture, matched seeds, lockstep, request seeds and matched sampling. Results are blinded until the report is frozen, then unblinded. Every call goes on a BrainTape, invalid runs are kept and retried only for a cause outside the experiment, and the seed count is justified by the measured variance.
- **What doesn't decide:**
  - Bench agreement does not predict game results (docs/research/lab-model-vs-model.md).
  - Play-mode games are observations.
  - A single seed is an anecdote.
  - Model-only runs are a diagnostic, never a screening arm.
- **Random scheme 3.** Seeded absolute outcomes from before it are not compared with results under it.
- **Every model gets two report cards.** Neither is collapsed into one score:
  - **Civilisation quality:** discoveries, era, population, preventable deaths and starvation, food, infrastructure (homes, useful buildings), invention success, knowledge lost and recovered, failed steps, loops.
  - **Thinking cost:** requests per chit-day (for each level of a two-level mind), tokens per discovery, seconds per chit-day, VRAM, wall time.
- **Who drove the world** (docs/PROVENANCE.md) is reported beside both:
  - strategic decisions by the model, and the share it wrote itself
  - reflex, routine and instinct step shares

## The funnel

Candidates and their facts are in docs/research/model-landscape-2026-10.md.

1. **Stage A, cheap screening:** decision-bench and prompt checks.
   - valid replies, impossible actions, schema compliance, latency, tokens
   - for letter models: calibration of the letter readout, and whether urgent needs are recognised
   - Reject the plainly unusable.
2. **Stage B, the model in the loop:** `tools/harness/run.py --mind URL` on representative seeds, in the model's normal mode and model-led.
   - starvation, stuck loops, invented or missing items, malformed actions, who drove the world
   - Per-model sampling isn't in the harness yet (issue #141). A model whose card needs other sampling goes straight to stage C, with `"sampling": "native"`.
3. **Stage C, the Lab:** as above.

## Studies, in order

Each comes after the one before, on the RTX 5090. Later rounds are designed after the earlier results, not fixed now.

| # | Study | Protocol | Question |
|---|---|---|---|
| 1 | JevK5 9B vs Gemma 4 12B (full prompt) | `docs/protocols/jevk5-vs-gemma.json` | **Done (2026-10-06), partial report card (its code predates it): [results](jevk5-vs-gemma-2026-10.md).** Gemma 4 12B: larger villages on all 6 seeds (25.3 vs 20.5, paired p 0.031); discoveries lean its way (21.5 vs 16.7, p 0.16). JevK5 was run as a JSON planner, not in its letter interface: studies 2-3 test that. |
| 2 | Choice repair off vs on (JevK5 cascade) | `docs/protocols/choice-repair-jevk5.json` | Does telling a choosing model why it failed help, or just change the failures? Decides `CHOICE_REPAIR`. |
| 3 | Two-level mind | `docs/protocols/two-level-jev-gemma.json` | Planner only vs Jev + Gemma vs cascades vs menu-only. |
| 4 | JevK5 9B vs Qwen3.5-9B, its own base | to write after 1-3 | Does the fine-tune help? Same prompt architecture (cascade, JevK5's letter interface), same quantization (Q8_0), same sampling: only the fine-tune differs. Whatever wins studies 1-3 is a separate benchmark arm, not this comparison |
| 5 | Winner vs Qwen3.5-4B, Granite 4.2 8B | after stage A/B | the efficiency end |
| 6 | Best general planner vs the best two-level mind | after 3-5 | architecture against size |
| 7 | Best efficiency model vs best absolute model (Gemma 4 26B-A4B, Qwen3.6-35B-A3B, Qwen3.8-27B) | after stage A/B | what the 5090's biggest models buy, and at what cost |

**Seeds.** Six seeds is a start, not a power analysis. After study 1, the per-seed spread of each primary outcome sets the seed count of the next protocol. The aim is a difference that matters, reached with a stated probability.

**Recorded from now on** (#150):
- **Preventable deaths.** A starvation with food in a store on the chit's own land within 30 tiles, judged at the moment of death (`lab/autopsy.py`). Runs from before this, such as the JevK5-vs-Gemma study, report it as not measured, never as 0.
- **Native sampling.** A protocol may declare `"sampling": "native"`, so that each model runs at its card's own temperature and sampler settings. Everything else must still match.

## What every report says

Effect sizes with confidence intervals, per-seed results, thinking opportunities, the model's step share, failures, waiting cost, and limitations, including any shared-world mechanics left on (docs/WORLD_RULES.md). From now on, a protocol can switch those off (`"rules": {...}`). Nothing is oversold from a few seeds.
