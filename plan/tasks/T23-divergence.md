# T23 · Divergence report: how differently did the two worlds think?

**Why:** the question people care about is not "which world has more stuff" but **"did they become different
civilisations?"** This task turns the twin worlds into a single, honest comparison: what only one world
figured out, who got there first, what each called things, what each invented and believed. It comes with a
divergence score and ready-to-post text.

## Build
1. **`server/chits/story/divergence.py`.**
   - `compare(wa: World, wb: World) -> dict` returns:
     ```
     {"day": max day of the two,
      "worlds": {id: {"id","name","label","culture","day","population","generations","era",
                      "discoveries": len(base keys in first), "inventions": [names], "beliefs": [names],
                      "local_names": {key: local name}}},   # T05 culture_names
      "shared": [keys],                 # base keys in both worlds' `first`, sorted by the earlier first tick
      "only": {wa.id: [keys], wb.id: [keys]},   # sorted by tick
      "race": [{"key", "name", wa.id: day|None, wb.id: day|None, "winner": id|None}],  # shared keys
      "wins": {wa.id: n, wb.id: n},
      "scores": {"knowledge": J, "order": K, "culture": C},
      "divergence": int 0..100,
      "headline": str}
     ```
   - **Base keys** are the keys in `world.first` that start with `recipe:` or `design:` and are not `inv_`
     inventions. Inventions and beliefs are counted separately.
   - The scores:
     - `J` (knowledge): `1 - |A∩B| / |A∪B|` over base keys, or 0 if the union is empty.
     - `K` (order): the normalised Kendall tau distance of the shared keys' first ticks. It is the fraction
       of shared pairs ordered differently in the two worlds. It is 0 with fewer than 2 shared keys.
     - `C` (culture): `min(1, (inventions_A + inventions_B + beliefs_A + beliefs_B) / 10)`.
   - `divergence = round(100 * (0.5*J + 0.3*K + 0.2*C))`.
   - A race day is `first_tick // 240 + 1`. `winner` is the world with the smaller first tick. It is None on a
     tie.
   - Display names use the world's local name when it has one (T05), else `item_name` / `DESIGNS[k].name`.
   - `headline` examples:
     - `Same island, two minds: 59% divergent by day 12`
     - `Same island, two minds: identical so far (day 3)` when divergence is 0
2. **`to_markdown(cmp) -> str`** is a post-ready report. It has:
   - a `# ` title line with the headline
   - a numbers table: population, generations, era, discoveries, inventions and beliefs, one column per
     world
   - a `## Only in <world name>` section for each world, listing the names (local names in quotes)
   - a `## The race` list: `stone axe — World A day 2 · World B day 5 (A first)`
   - a `## Inventions` section and a `## Beliefs` section, listed per world
   - a final line: `Divergence: {n}/100 (knowledge {J:.2f} · order {K:.2f} · culture {C:.2f})`
3. **`to_tweet(cmp) -> str`**: at most 280 characters. It holds the headline, then one line per world with a
   standout item: its most recent unique discovery, invention or belief, in that order of preference. It
   ends with the divergence.
4. **API.**
   - `GET /api/compare` returns `{"compare": ..., "markdown": ..., "tweet": ...}` for the first two worlds.
     It returns 400 with a single world.
   - CLI `python -m chits.tools.compare [--url http://127.0.0.1:8000] [--tweet]` fetches the endpoint and
     prints the markdown (or the tweet).
   - Makefile target `compare`.
5. **Web.** The Knowledge tab gets a **⚖ Compare** button. It opens a small panel with the headline, the
   divergence score, the two "only in" lists, and **Copy markdown** / **Copy tweet** buttons.
6. **Experiment runner (T15).** If `summary.md` is produced, append the comparison markdown to it.

## Done when
`python scripts/plan.py verify T23` passes.
