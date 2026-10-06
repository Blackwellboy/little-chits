# JevK5 9B vs Gemma 4 12B, one island, one culture

Protocol `6fc60a4faaa15742` · code `d3882f3` · 6 seeds × 2 arms · 25 days · island 128 · 12 founders · experiment contract
Runs finished: 12 of 12.
Arms are **unblinded** (seal checked).

## Final values

| metric | A (gemma) | B (jevk5) |
|---|---|---|
| discoveries | 21.50 [19.17, 23.83] · med 20.50 | 16.67 [12.67, 20.50] · med 16.50 |
| era | 4.50 [3.83, 5.00] · med 5.00 | 4.50 [4.17, 4.83] · med 4.50 |
| population | 25.33 [22.33, 29.67] · med 24.00 | 20.50 [19.17, 22.00] · med 20.00 |
| starved | 0.00 [0.00, 0.00] · med 0.00 | 0.00 [0.00, 0.00] · med 0.00 |
| model_step_share | 0.58 [0.56, 0.60] · med 0.58 | 0.70 [0.67, 0.73] · med 0.69 |
| requests_per_chit_day | 3.45 [3.23, 3.68] · med 3.44 | 10.52 [10.06, 10.98] · med 10.57 |

Mean [95% bootstrap interval] · median, over seeds.

## B (jevk5) vs A (gemma)

| metric | mean diff per seed [95% CI] | seeds higher / lower / tied | Cliff's delta | Mann-Whitney p |
|---|---|---|---|---|
| discoveries | -4.83 [-9.17, 0.00] | 2 / 4 / 0 | -0.56 | 0.11 |
| era | 0.00 [-0.67, 0.67] | 2 / 2 / 2 | -0.08 | 0.78 |
| population | -4.83 [-7.83, -2.33] | 0 / 6 / 0 | -0.75 | 0.03 |
| starved | 0.00 [0.00, 0.00] | 0 / 0 / 6 | 0.00 | 1.00 |
| model_step_share | 0.12 [0.09, 0.15] | 6 / 0 / 0 | 1.00 | 0.00 |
| requests_per_chit_day | 7.07 [6.69, 7.50] | 6 / 0 / 0 | 1.00 | 0.00 |

Differences are paired by seed (both arms had the same island). p-values are not corrected for the number of metrics: read them as a guide, not a verdict.

## Thinking opportunities

Per chit-day (one chit alive for one day). Reported, not equalised: a model whose plans run out sooner asks more often. Waiting is the share of a model-minded chit's time spent waiting for its answer (near 0 in lockstep, where the world waits instead); seconds waited is that lockstep wait in wall time, a cost of the card and the model, not a world fact; model steps are the finished steps that came from the model's plans (the rest are reflexes).

| | A (gemma) | B (jevk5) |
|---|---|---|
| requests per chit-day | 3.45 | 10.52 |
| waiting share | 0.00 | 0.00 |
| seconds waited per chit-day | 18.99 | 22.05 |
| model share of steps | 0.58 | 0.70 |

Means over seeds.

## Time to event

| event | A (gemma) | B (jevk5) |
|---|---|---|
| 20 discoveries | 4/6 · median day 9.00 | 2/6 · median day - |
| first copper in store | 0/6 · median day - | 0/6 · median day - |

Median day by Kaplan-Meier: a run that never got there counts as "not by the last day"; '-' means fewer than half got there.
