# Research readiness (audit, 2026-10-05)

An audit of the acceptance gates in `docs/RESEARCH_PLAN_2026-09-30.md` against `main` at `142d58f`. Mostly reading
and testing; the only code added is `tests/test_research_gates.py`. Paths are under `server/chits/` unless they start
with `tests/` or `docs/`.

**Short answer:** the Lab is a working, deterministic, blind, pre-registered harness for instinct-only studies, and
can run model arms with sealed configs. It is not research-ready for worldview studies: the belief system that exists
today (T21) breaks gates C and D and has hidden effects, and the worldview engine the gates assume (R8) isn't built.
A first model-vs-model study on one island and culture is a few small steps away (end of this file).

Statuses: **PASS** (implemented and tested) · **PARTIAL** · **NOT IMPLEMENTED** · **NOT APPLICABLE YET**.
"New test" means one added by this audit. Each was checked by breaking the code it guards and watching it fail.
"xfail" means a strict expected failure: it documents a gap, fails today for the stated reason, and fails the suite
once the gap is fixed, so that the marker has to be removed.

## The gates

| Gate | Status | Evidence | Missing |
|---|---|---|---|
| **A** treatment isolation: physics never reads `worldview_id` | **PARTIAL** (no `worldview_id` exists yet) | TreatmentPacks only teach practices and add memories (`lab/treatment.py:141-155`). The linter refuses any non-knowledge field (`lab/treatment.py:45-47`). Who was told goes to `runs/*/treatment.json`, outside the world and the blind result (`lab/run.py:92-95`). Tests: `tests/test_treatment.py:86, 139`. **New test:** `tests/test_research_gates.py:67`, no module in `sim/` or `brain/` imports `chits.lab`. | The T21 belief id (`Agent.belief`) **is** read by physics: co-believers gain affinity and a shrine of your own faith lifts mood (`sim/world.py:809-821`), prayer gives +6 mood (`sim/actions.py:1820`), and mood above 70 means 1.1x work speed (`sim/actions.py:689, 1269, 2560`). A worldview id must not get the same treatment. |
| **B** no magic effect: the same BrainTape with a different pack gives identical physics | **PARTIAL** | **New test** `tests/test_research_gates.py:85`: brain output held fixed (no plans), a claims-only pack changes memories and nothing else over a day. | There's no worldview pack yet. The BrainTape can't hold the brain fixed across packs, because a pack changes the prompt, so a replay misses (`brain/tape.py`, `TapeMiss`). The gate needs a "replay by decision index" mode, or a fixed-brain harness like the new test. The T21 bonuses above would fail this gate for beliefs. |
| **C** a newborn has no worldview without exposure | **NOT IMPLEMENTED** (violated) | `World._make_child` converts a child whose parents share a faith, as "raised" (`sim/world.py:1987-1988`), in every contract. **New test (xfail):** `tests/test_research_gates.py:111`. | Plan item 50: under the strict contract, children inherit no beliefs. The World doesn't know its contract today, so it needs a flag. |
| **D** exposure is not conversion | **NOT IMPLEMENTED** (violated) | Preaching converts a listener by chance (`sim/actions.py:1846`). Praying at a shrine converts (`sim/actions.py:1822`). Reading a belief tablet converts (`sim/actions.py:2961`, `sim/artifacts.py:109`). Exposure is recorded (`met_beliefs`, `sim/actions.py:1843`). Only `mind.py:120` (a reflection that names a faith) is the chit's own choice. **New test (xfail):** `tests/test_research_gates.py:121`. | R8: BeliefExposure / BeliefDecision. In strict mode, only a mind's decision converts. |
| **E** the last keeper can die and knowledge really disappears | **PARTIAL** | `sim/lore.py:60-67` emits `forgotten`. Nothing re-grants knowledge without a recorded way (`invariants.py` `unknown_provenance`). Tests: `tests/test_lore.py:29, 44`. **New test:** `tests/test_research_gates.py:135`, nobody alive knows it afterwards and a day of play hands it back to nobody. | The world rescues knowledge in every contract. An old last keeper gets a prompt line telling it to teach before it dies (`sim/lore.py:70-82`, used at `brain/prompt.py:287-290, 374, 574`), and instinct ranks passing it on first (`brain/civic.py` `LORE_W`). Library research reads the hidden recipe table for hints (`sim/research.py:75-113`). Plan item 50 says strict history runs get neither. Only recipes are tracked, not designs. |
| **F** every copied or reinterpreted text traces to its parent | **NOT IMPLEMENTED** | A `Tablet` has an author and tick but no content hash or parent (`sim/world.py:189-198`). There is no copy or retell verb. Reading records no source (`World.learned(a, k, "read", None)`, `sim/actions.py:2969`). **New test (xfail):** `tests/test_research_gates.py:158`. | R8 item 52: content hash and parent hash, with copy and reinterpret as separate verbs. |
| **G** no cross-world state moves without a recorded transfer | **PARTIAL** | Lab runs are one world per process, so nothing can cross. The experiment contract refuses contact (`runtime.py:332`). In play, a voyage is recorded both ways (`sim/world.py:431-433` `voyage`; `sim/world.py:456-490` `arrival`, with `origin`, and carried inventions via `adopt_foreign`). Tests: `tests/test_trade_voyage.py`, `tests/test_forks.py:77` (nobody sails out of a fork). | `Runtime.mend_foreign` (`runtime.py:220-232`) copies invention definitions between worlds on load with only a log line (it is a legacy-save repair). There is no WorldGraph (R9) and no transfer ledger as data. |
| **H** analysis runs on treatments A-K blind | **PASS** (Lab) | Labels are sealed with a hash in the manifest, and run order rotates so every arm takes every slot (`lab/assign.py`). The report is blind unless `--unblind` and the seal checks (`lab/report.py`). Up to 26 arms (`lab/spec.py:14, 108`). Tests: `tests/test_lab.py:99, 136`, `tests/test_treatment.py:139`, `tests/test_propositions.py:45`. | `make experiment` (`tools/experiment.py`) is not blind: it names Worlds A/B and their URLs. Use the Lab for studies. |
| **I** equal strategic opportunity budgets | **NOT IMPLEMENTED** | Opportunities are measured, not equalised: compute accounting per world (requests, tokens, plans; `lab/run.py:172-177`, `tools/experiment.py`), lockstep, and per-request seeds. The plan's Progress section says the budget cap is not done. | A pre-registered equal strategic-call budget (R1). Until then, report requests per chit-day with every comparison. |
| **J** a 2,000-year mock run stays bounded | **NOT IMPLEMENTED** | Nothing exists for deep time (R11). There are bounds in places: memory cap (`sim/agent.py:267`), the dead trimmed (`sim/agent.py:315`), the event window, and recorder retention (`tests/test_recorder_retention.py`). | The R11 mock run and its memory and disk bound test. |
| **K** BrainTape replay reconstructs a bounded run | **PARTIAL** | `brain/tape.py`, wired into `make experiment` (`tools/experiment.py:189-190, 308-321`). Test: `tests/test_braintape.py:49` (1 day: identical stats and every event, with zero misses), plus miss and failed-call tests. | Lab model arms have no `--tape` (`lab/run.py:130-179`). The replay test compares stats and events, not the full world state. |
| **L** narrator output can't reach memory, beliefs, prompts, rewards or physics | **PASS** (structural) | The narrator (`story/`: chronicle, sagas, recap, moments) only writes files (`runtime.py:750-800`). The storyteller *game director* (`sim/storyteller.py`) does act on the world, but play only (`runtime.py:990`). Tests: `tests/test_recap.py:68`, `tests/test_storyteller.py:57`. **New test:** `tests/test_research_gates.py:67`, `sim/` and `brain/` never import `chits.story`, `chits.tools` or `chits.recorder`. | `Runtime.narrator_brain` can borrow the world's own model in play (`runtime.py:742-749`). That is load on the measured server, not state. A narrator run during an experiment would count against the world's request stats. |
| **+** checkpoints preserve all lineages and RNG state | **PARTIAL** | Named RNG streams are saved and restored (`sim/world.py:2029, 2136-2149`). **New test:** `tests/test_research_gates.py:198`: a JSON checkpoint carries on identically for 3 days (parents, the dead, tablets, beliefs, knowledge sources, RNG), apart from traffic. | `World.to_dict` rounds `traffic` to 1 decimal (`sim/world.py:2030`), so a restored world's road-forming traffic drifts (by 0.5 within 3 days in the test). **New test (xfail):** `tests/test_research_gates.py:206`. The Lab never checkpoints mid-run; resume reruns whole runs. |

Also added: `tests/test_research_gates.py:213` checks that the same Lab run twice gives byte-identical results and
daily rows. I also confirmed this by hand for a 2-seed, 2-arm batch, with `--jobs 2` against `--jobs 1`.

## The Lab today

- **Two runners.** `make experiment` is `chits.tools.experiment`: two worlds, model A against model B, one seed, not
  blind, with a tape option. The Lab is `python -m chits.lab run|resume|analyze|lint`, and there is **no Makefile
  target for it**. Only the Lab has protocols, seeds × arms, sealing and statistics.
- **End to end, instinct only, no GPU: works.** I ran `docs/protocols/speech-vs-silence.json` cut to 2 seeds × 5 days,
  with the drought moved to day 3. With `--jobs 2`, 4 runs took 8 s. `analyze` wrote `report-blind.md` with final
  values and bootstrap CIs, per-seed paired differences, Cliff's delta, Mann-Whitney and Kaplan-Meier time to event.
  It also wrote `runs-blind.csv`, `daily-blind.csv` and `lifetime-blind.csv`, alongside `manifest.json` (protocol,
  fingerprint, commit, prompt version, assignment hash) and `sealed/assignment.json`. `resume` on the finished
  directory ran 0 runs. A rerun into a new directory gave identical results. `make experiment ARGS="--days 2 --chits 8"`
  (instinct against instinct) also ran. Both worlds came out identical, as they should.
- **Model arms.** These exist and are tested against a fake server (`tests/test_lab.py:66, 181`). Each world runs
  strict and lockstep with per-request seeds and the per-tick invariant gate, and stops after 12 failed calls in a row.
  The Lab refuses mismatched comparison settings, and literal API keys.

### What a model-vs-model run through the Lab needs (not run)

```json
{
  "name": "Model A vs model B, one culture",
  "arms": [{"name": "m1", "culture": "direct", "brain": "m1"},
           {"name": "m2", "culture": "direct", "brain": "m2"}],
  "allow_models": true,
  "brains": {
    "m1": {"id": "m1", "label": "m1", "base_url": "http://127.0.0.1:<port-a>/v1", "model": "<served name>", <SHARED>},
    "m2": {"id": "m2", "label": "m2", "base_url": "http://127.0.0.1:<port-b>/v1", "model": "<served name>", <SHARED>}
  },
  "seeds": [1, 2, 3, 4, 5, 6, 7, 8], "days": 10, "size": 128, "population": 18
}
```

`<SHARED>` stands for the same values in both brains: `max_concurrency`, `timeout`, `temperature`, `max_tokens`,
`json_mode`, `disable_thinking`, `prompt_style`, `escalate_*`, `focus` and `extra_body`. Put the sampling in
`extra_body` (for example `{"top_p": 0.95, "top_k": 40, "min_p": 0.05}`), because the Lab doesn't add it the way
`make experiment` does. Run it with `CHITS_LAB_ALLOW_MODELS=1 python -m chits.lab run p.json --out DIR --jobs 1`,
from `server/`, with the owner's go-ahead for the cards. Both arms on one seed get the same island. Keep `--jobs` low,
because parallel runs share a server and timeouts end runs at 12 failures in a row. Use `"api_key": "env:NAME"` if a
key is needed.

## Experiment mode (the strict contract) against play

**Experiment mode guarantees today:**
- A model's chit never acts on an instinct plan. It waits instead, both when a reply is late and when the queue is
  full (`brain/mind.py:229-262, 316-335`). The invariant gate enforces this as `stand_in` and stops on a break.
- A chit never thinks with a brain its world wasn't given (`foreign_mind`, `invariants.py:52-57`).
- There is no focus routing and no duty override, and action repair happens only when declared (`brain/mind.py:262,
  371, 382`).
- The world is left alone: no storyteller challenges, wanderers or rescue of a dying world (`runtime.py:990`). There
  are no pop caps, skip-ahead, forks, save restores, god mode or content packs (`runtime.py:194, 284, 402, 416, 636,
  1008, 1252, 1293`), and no contact between islands (`runtime.py:332`).
- An unrestorable or out-of-step run is refused or marked invalid, never patched (`runtime.py:246, 254, 593`).
- With `make experiment` and the Lab: lockstep, so card speed can't change the world; per-request seeds; and explicit
  sampling (`make experiment` adds it, while the Lab arms must carry it in `extra_body`). Hard invariants are checked
  every tick or day and the run stops on a break.

**Play mode does not guarantee:** that a model drove its chits. Instinct fills in for a slow, queued or unavailable
model, focus hands routine plans to instinct, and pacing is off by default, so speed leaks into results (plan item 70).
Play also runs the storyteller, wanderers, boats, forks, pop caps and god-mode edits, and only reports invariants.

**Neither mode turns off** the T21 belief mechanics (inheritance, conversion by preaching, prayer or reading, mood and
affinity bonuses), the last-keeper rescue nudge, library hints drawn from the hidden recipe table, or scheduled T26
elections. Plan item 50 assigns all of these to the strict contract, and none of it is built.

## What can honestly be claimed today

- Instinct-only comparisons through the Lab are reproducible, pre-registered, blind until unsealed, matched on
  island and interventions, and reported with paired effect sizes and intervals. Examples: speech against silence,
  and told against untold stone tools.
- A TreatmentPack changes only what founders know. A claims-only pack changes no physics when the decisions are held
  fixed.
- Model-vs-model runs in the Lab are strict (the model decides every plan), lockstep, seeded and fairness-checked on
  settings. No real-model Lab run has been made.
- Not yet claimable: anything about worldviews, religion, conversion or cultural transmission of beliefs (C, D and F
  fail, and A and B fail for T21 beliefs). Also not claimable: "knowledge loss" as a natural process in strict runs
  (E has rescue nudges), deep-time results (J), or equal-opportunity model comparisons (I).

## Smallest steps to a first study: model against model, same island and culture

1. Add `make lab ARGS=...`, a Makefile target for `python -m chits.lab`, so the documented entry point exists.
2. Have the Lab arms add the same explicit sampling as `make experiment` (`SAMPLING`) when `extra_body` has none, and
   record it in the manifest.
3. Wire `BrainTape` into Lab model arms (a tape per run under `runs/<seed>_<label>/`) so every real run can be
   replayed (gate K for the Lab).
4. Report opportunity use per arm in the blind report: requests, adopted plans and waiting ticks per chit-day. This
   is the measured half of gate I. An equal-budget cap is a separate, pre-registered design.
5. Pair seeds with card swaps (plan item 72): on half the seeds, swap which server and card hosts which model, and
   record it in the manifest.
6. Before the GPUs are used, make a dry run of the exact protocol against `make fake-model` on two ports. This checks
   the config, the seals and the report.
7. Pre-register: write the protocol (8 or more seeds, both arms on `direct`, a fixed number of days, the metrics, and
   the events to time) and get the owner's go-ahead for the cards. Then run it with `CHITS_LAB_ALLOW_MODELS=1`.

The study doesn't use beliefs as a treatment, so C, D and F don't block it. Its write-up must say that T21 beliefs and
the knowledge-rescue nudges are active in both arms, as part of the shared world.
