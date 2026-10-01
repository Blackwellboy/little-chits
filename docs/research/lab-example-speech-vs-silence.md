# Speech vs silence, with a drought

Protocol `19dfdfc4d5c5b092` · code `a9f195a+dirty` · 12 seeds × 2 arms · 30 days · island 128 · 18 founders · experiment contract
Runs finished: 24 of 24.
Arms are **unblinded** (seal checked).

Interventions, identical in every arm: day 20 drought

## Final values

| metric | A (talking) | B (silent) |
|---|---|---|
| discoveries | 43.50 [39.00, 47.75] · med 43.00 | 35.92 [32.83, 39.08] · med 35.00 |
| population | 56.00 [52.00, 58.92] · med 58.50 | 52.58 [49.75, 55.33] · med 53.50 |
| era | 6.75 [6.25, 7.17] · med 7.00 | 5.50 [5.08, 5.92] · med 5.50 |
| food | 535 [393, 655] · med 592 | 654 [576, 738] · med 646 |
| homes | 16.83 [15.25, 18.25] · med 17.00 | 13.83 [12.25, 15.42] · med 13.50 |
| useful | 8.92 [7.08, 10.58] · med 9.50 | 9.17 [7.75, 10.67] · med 9.00 |
| villages | 1.75 [1.17, 2.42] · med 1.00 | 1.42 [1.08, 1.83] · med 1.00 |
| births | 38.67 [34.83, 41.58] · med 41.00 | 34.58 [31.75, 37.33] · med 35.50 |
| forgotten | 0.00 [0.00, 0.00] · med 0.00 | 0.00 [0.00, 0.00] · med 0.00 |
| copper | 8.67 [2.67, 16.33] · med 2.50 | 2.75 [0.50, 5.75] · med 0.00 |

Mean [95% bootstrap interval] · median, over seeds.

## B (silent) vs A (talking)

| metric | mean diff per seed [95% CI] | seeds higher / lower / tied | Cliff's delta | Mann-Whitney p |
|---|---|---|---|---|
| discoveries | -7.58 [-11.33, -4.00] | 1 / 11 / 0 | -0.56 | 0.02 |
| population | -3.42 [-6.83, 0.75] | 2 / 9 / 1 | -0.46 | 0.05 |
| era | -1.25 [-1.83, -0.75] | 0 / 9 / 3 | -0.70 | 0.00 |
| food | 120 [-55.25, 326] | 7 / 5 / 0 | 0.25 | 0.30 |
| homes | -3.00 [-4.67, -0.67] | 1 / 10 / 1 | -0.56 | 0.02 |
| useful | 0.25 [-1.42, 2.00] | 5 / 5 / 2 | 0.00 | 1.00 |
| villages | -0.33 [-0.83, 0.17] | 2 / 5 / 5 | -0.14 | 0.50 |
| births | -4.08 [-7.42, -0.17] | 2 / 9 / 1 | -0.50 | 0.04 |
| forgotten | 0.00 [0.00, 0.00] | 0 / 0 / 12 | 0.00 | 1.00 |
| copper | -5.92 [-12.67, 0.67] | 1 / 9 / 2 | -0.42 | 0.07 |

Differences are paired by seed (both arms had the same island). p-values are not corrected for the number of metrics: read them as a guide, not a verdict.

## Time to event

| event | A (talking) | B (silent) |
|---|---|---|
| 20 discoveries | 12/12 · median day 5.00 | 12/12 · median day 6.00 |
| a second village | 6/12 · median day 27.00 | 6/12 · median day 21.00 |
| first copper in store | 10/12 · median day 16.00 | 5/12 · median day - |

Median day by Kaplan-Meier: a run that never got there counts as "not by the last day"; '-' means fewer than half got there.
