# JevK5 9B vs Gemma 4 12B: results (2026-10-06)

The first pre-registered model-vs-model study. Protocol: [`docs/protocols/jevk5-vs-gemma.json`](../protocols/jevk5-vs-gemma.json) (fingerprint `6fc60a4faaa15742`), run with the code at `d3882f3`. Method and apparatus: [lab-model-vs-model.md](lab-model-vs-model.md).

## Design

- **Runs:** 6 seeds × 2 arms, 25 days each, all 12 finished and none invalid.
- **World:** one island per seed, shared by both arms; 128 tiles; the direct culture; 12 founders.
- **Contract:** the experiment contract (the model decides every plan, with no instinct stand-ins), in lockstep.
- **Requests:** seeded, with identical explicit sampling (temperature 0.7, top-p 0.95, top-k 40, min-p 0.05).
- **Pre-registered metrics:** discoveries, era, population, starved, model step share, and requests per chit-day.
- **Blinding:** arms were labelled A/B. The blind report was written and frozen before the seal was opened.

| file | sha256 (frozen 2026-10-06T03:36:34Z, before unblinding) |
|---|---|
| `report-blind.md` | `38ae93c66e4c9ab8e5374dab6f952e54e82048399044a82e4ad16cf4323d27f4` |
| `runs-blind.csv` | `d35c953b2c29ec4af773fc0d05d1f565e69b190332781f9bbef25a049b187033` |

Both reports are in [`jevk5-vs-gemma/`](jevk5-vs-gemma/). After unblinding, **A = Gemma 4 12B** and **B = JevK5 9B**.

## Result

| metric | Gemma 4 12B | JevK5 9B | JevK5 − Gemma per seed [95% CI] | seeds JevK5 higher / lower / tied | p (Mann-Whitney) |
|---|---|---|---|---|---|
| discoveries | 21.50 | 16.67 | −4.83 [−9.17, 0.00] | 2 / 4 / 0 | 0.11 |
| era | 4.50 | 4.50 | 0.00 [−0.67, 0.67] | 2 / 2 / 2 | 0.78 |
| population | 25.33 | 20.50 | −4.83 [−7.83, −2.33] | 0 / 6 / 0 | 0.03 |
| starved | 0 | 0 | 0 | 0 / 0 / 6 | 1.00 |
| model step share | 0.58 | 0.70 | +0.12 [0.09, 0.15] | 6 / 0 / 0 | <0.01 |
| requests per chit-day | 3.45 | 10.52 | +7.07 [6.69, 7.50] | 6 / 0 / 0 | <0.01 |

Here is what the study shows:
- **Population:** under these conditions Gemma 4 12B's villages grew larger than JevK5's on every seed.
- **Discoveries:** Gemma led on 4 of 6 seeds. The interval reaches 0, so this is a lean, not a finding.
- **Ages:** neither model reached a later age.
- **Request rate:** JevK5 asked about three times as often per chit-day. Its plans are shorter, so they run out sooner.

The p-values are not corrected for the six metrics. Read them as a guide.

This does not support the earlier informal 3-seed comparison, in which JevK5 led on discoveries. That comparison was not pre-registered and is superseded by this study.

## Exploratory (not pre-registered)

These columns come from the same runs. They were not named in the protocol, so they suggest where to look next and test nothing.

| at day 25, mean of 6 seeds | Gemma | JevK5 |
|---|---|---|
| farms | 4.3 | 25.7 |
| stockpiles | 6.8 | 1.3 |
| food in store | 184 | 19 |
| loose goods on the ground | 512 | 834 |
| births | 13.3 | 8.5 |
| structures | 26.5 | 37.8 |

JevK5's villages built many farms but almost no stockpiles. They kept little food in store and left more goods on the ground, and fewer chits were born. One reading is that a model fine-tuned to pick one letter from a short list repeats a building choice it rates well when it is asked for a whole JSON plan. That is a hypothesis for the cascade studies below, not a conclusion.

## Limitations

- **JevK5 was run outside its native interface.** It is a decision model, fine-tuned to pick a letter from short option lists, but here it wrote full JSON plans (`prompt_style: "full"`) like Gemma. This study measures JevK5 *as a JSON planner*, not JevK5 in the cascade it was trained for. Choice-repair and two-level studies 2 and 3 in the [programme](model-programme.md) use its native interface.
- **The quantizations differ:** JevK5 at Q8_0, Gemma at Q4_K_M. The arms differ in model, size and quantization at once.
- **Preventable deaths were not measured.** The autopsy was added after this study's code was frozen, so they are reported as not measured, not as 0. No chit starved in either arm.
- **Six seeds and 25 days.** This is short, and the effect on population is clear but the effect on discoveries is not.
- **Beliefs and library hints were active in both arms.** Religion (T21), last-keeper reminders and library hints are part of the shared world here, not a treatment.

## Reproduce

```bash
CHITS_LAB_ALLOW_MODELS=1 make lab ARGS="run docs/protocols/jevk5-vs-gemma.json --out runs/jevk5-vs-gemma --jobs 2"
make lab ARGS="analyze runs/jevk5-vs-gemma"            # blind
make lab ARGS="analyze runs/jevk5-vs-gemma --unblind"  # after freezing the blind report
```

The model servers are set up as described in [lab-model-vs-model.md](lab-model-vs-model.md).
