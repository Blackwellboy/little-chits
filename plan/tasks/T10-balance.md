# T10 · Balance: a thriving no-model baseline, without building spam

**Why:** instinct is the baseline every model is compared against, and it also covers for slow models. Today
it survives, but it spams buildings (up to 19 stockpiles, 11 kilns and 36 brick houses by day 30 on some seeds),
which looks bad on camera and makes the comparison meaningless.

Measured before this task (30 days, 18 chits):

| seed | pop | discoveries | stockpiles | kilns | campfires | brick houses | workshop/furnace |
|---|---|---|---|---|---|---|---|
| 42 | 26 | 12 | 9 | 2 | 4 | 11 | no |
| 7 | 28 | 18 | 19 | 11 | 14 | 10 | yes |
| 99 | 40 | 17 | 14 | 4 | 10 | 36 | no |

## Build
Tune `server/chits/brain/instinct.py` (and world rules only where truly needed) so that, for seeds 42, 7 and
99, after 30 days with 18 chits:
- population ≥ 12, and it never hits 0
- discoveries ≥ 14
- stockpiles ≤ 6, kilns ≤ 4, campfires ≤ 10, farms ≤ population/2 + 2
- brick houses + huts ≤ population/2 + 4 (homes hold 2–4 chits)
- a workshop or furnace exists in at least 2 of the 3 seeds

Suggested levers:
- **Count what already exists across the whole settlement**, not just within a small radius.
- **Prefer upgrading and repairing over new builds.**
- **Use the stockpile before gathering.**
- **Weight workshop/furnace goals higher once their prerequisites are known.**
- **Share food:** a generous chit with >4 food gives to a hungry neighbour.

Don't make instinct smarter than a model could be. It still must not know recipes it hasn't learned.

## Done when
`python scripts/plan.py verify T10` passes. The test takes about 1–3 minutes.
