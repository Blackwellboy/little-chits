# Told stone tools vs untold

Protocol `2d291a7c835ba2be` · code `3e7cc5b+dirty` · 12 seeds × 2 arms · 30 days · island 128 · 18 founders · experiment contract
Runs finished: 24 of 24.
Arms are **unblinded** (seal checked).

## Final values

| metric | A (told) | B (untold) |
|---|---|---|
| discoveries | 42.25 [39.33, 44.83] · med 43.00 | 42.25 [37.67, 46.67] · med 42.50 |
| population | 58.75 [57.75, 59.67] · med 60.00 | 56.17 [52.67, 59.00] · med 59.50 |
| era | 6.58 [6.08, 7.00] · med 7.00 | 6.67 [6.17, 7.08] · med 7.00 |
| food | 604 [468, 764] · med 564 | 605 [520, 696] · med 577 |
| homes | 17.50 [15.58, 19.17] · med 18.00 | 17.08 [15.83, 18.17] · med 18.00 |
| useful | 9.00 [7.17, 10.75] · med 10.00 | 8.08 [6.33, 9.75] · med 8.00 |
| villages | 1.67 [1.25, 2.08] · med 1.50 | 1.83 [1.33, 2.50] · med 1.50 |
| births | 40.75 [39.75, 41.67] · med 42.00 | 38.50 [35.08, 41.17] · med 41.50 |
| copper | 3.25 [0.42, 6.67] · med 0.50 | 6.67 [0.42, 13.83] · med 0.00 |

Mean [95% bootstrap interval] · median, over seeds.

## B (untold) vs A (told)

| metric | mean diff per seed [95% CI] | seeds higher / lower / tied | Cliff's delta | Mann-Whitney p |
|---|---|---|---|---|
| discoveries | 0.00 [-4.33, 5.42] | 4 / 8 / 0 | -0.03 | 0.91 |
| population | -2.58 [-5.83, -0.25] | 1 / 5 / 6 | -0.22 | 0.33 |
| era | 0.08 [-0.42, 0.58] | 3 / 3 / 6 | 0.06 | 0.76 |
| food | 0.25 [-131, 115] | 5 / 7 / 0 | 0.07 | 0.77 |
| homes | -0.42 [-2.42, 1.75] | 4 / 6 / 2 | -0.12 | 0.62 |
| useful | -0.92 [-2.58, 0.67] | 5 / 7 / 0 | -0.13 | 0.58 |
| villages | 0.17 [-0.42, 0.83] | 4 / 4 / 4 | 0.06 | 0.80 |
| births | -2.25 [-5.42, 0.00] | 1 / 5 / 6 | -0.15 | 0.50 |
| copper | 3.42 [-2.50, 10.75] | 3 / 4 / 5 | 0.00 | 1.00 |

Differences are paired by seed (both arms had the same island). p-values are not corrected for the number of metrics: read them as a guide, not a verdict.

## Time to event

| event | A (told) | B (untold) |
|---|---|---|
| 20 discoveries | 12/12 · median day 3.00 | 12/12 · median day 5.00 |
| first copper in store | 8/12 · median day 17.00 | 9/12 · median day 16.00 |

Median day by Kaplan-Meier: a run that never got there counts as "not by the last day"; '-' means fewer than half got there.

## Reading it

The told arm's founders (half of them, by the seed) start out knowing how to make sharp stones, stone axes and stone
picks. They reach 20 discoveries sooner (median day 3 against 5), but by day 30 the two arms are level on
discoveries, era, food, homes and villages. The told arm ends with a few more chits (about 2.6 per seed, and the
interval stays just above zero), but that is one of nine metrics with uncorrected p-values, so it is a lead to test
again, not a finding. In short: telling the founders a practice gives the village a head start that the untold
village makes up within a month. (The pack is synthetic: this shows the lab's treatment arm working, not anything
about real cultures.)
