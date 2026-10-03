# Norse theme (Fjordfolk)

`CHITS_THEME=norse` turns it on (case and surrounding spaces don't matter; any other value, or none, is the default
theme). It changes how the game is presented, never what happens in it.

## What changes

- **Chit names.** New chits get a Norse-inspired given name, usually with a place byname: "Astrid of the Fjord",
  "Bjorn of the Pine", "Sigrun". The names are ASCII spellings inspired by Scandinavian history, not period-accurate
  reconstructions, and the bynames are places, not traits.
- **World names.** New worlds are **Fjordhaven** (A) and **Pineholm** (B). Their ids stay `A` and `B`, and their
  culture labels ("Direct culture", "Stigmergy only") are unchanged.
- **The observer.** The server reports the theme (`"theme"` in `/api/health`, in the WebSocket hello and in replay
  bundles). With `norse`, the observer uses the Nordic palette, wool-clad villagers, spruce, pine and birch, timber
  halls under turf roofs, the Fjordmark and the Fjordfolk title. Every sprite keeps its default size, so footprints,
  depth and labels are unchanged. `?theme=norse` or `?theme=default` in the URL overrides the server's choice.

## What doesn't change

Everything the simulation decides. Entity ids, items, rules, saves and every random stream are the same with the
theme on or off. `tests/test_norse_theme.py` runs a seed for two in-game days on instinct, plus births across ten
generations and a death, with the theme off and on. It checks that the two worlds are identical, apart from the
names chits are shown by.

Saved names are never rewritten. A world saved without the theme keeps its syllable names (and "World A") when the
theme is turned on, and the other way round. Start a new game to see the Norse names.

## How the names keep the random numbers the same

Chit names come from a syllable generator (`make_name` in `server/chits/sim/agent.py`). When a candidate is already
taken, the generator draws again, so a collision costs extra random numbers. A themed name that drew its own random
numbers, or that checked collisions against Norse names, would change every later draw.

So the theme doesn't make its own names. The syllable generator still runs and checks collisions against the
*syllable* names of those already taken. Its result is then shown through a fixed, one-to-one table
(`server/chits/theme.py`):

| Syllable name | How many | Norse name |
|---|---|---|
| short, e.g. `Pilo` | 1,940 | a given name with a byname (100 × 20 = 2,000 names) |
| longer, once the short ones run out, e.g. `Pimolo` | 8,000 | a compound given name with a byname (`Thorgeir of the Heath`) |
| numbered, after that, e.g. `Pilo7` | unbounded | its base's Norse name and a Roman numeral (`Astrid of the Fjord VII`) |

The table is ordered by SHA-256, never Python's per-process string hash, so it is the same on every machine and
every run. A Norse name reads back to the syllable name it stands for. Any other name, such as an old save's
syllable name or a typed-in one, stands for itself.

**Compatibility:** don't reorder or edit `GIVEN`, `BYNAMES`, `PREFIXES` or `SUFFIXES` in `server/chits/theme.py`,
or the syllable lists in `agent.py`. Saved Norse names are read back through them; changing them would need a
migration.

## Where it lives

- `server/chits/theme.py`: the active theme, world names and the name table.
- `web/src/theme.ts`: the one place the observer picks a theme. Renderers and panels ask it for palette, painters,
  chit art and branding.
- `web/src/render/norse.ts`: the Nordic art.
- `web/src/styles.css`: the Norse colours, scoped under `[data-theme="norse"]`.
- Tests: `tests/test_norse_theme.py`, `tests/web/theme.test.ts`.

Norse theme contributed by @poptartsmmmgood117-bit.
