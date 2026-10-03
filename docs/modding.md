# Content packs

A content pack is one JSON file. It adds items and recipes to a game. The chits are not told about them: they
find the new recipes by experiment, the same way they find the base ones.

A pack is data only. Nothing in it is run. A theme changes names and art; a pack changes what can be made.

## Try the example

[`docs/packs/honey.json`](packs/honey.json) adds bees: a woven hive, honeycomb, honey and mead.

Check it:

```bash
cd server && python -m chits.sim.packs ../docs/packs/honey.json
```

Play with it, either way:

- **In the game:** ⟲ New game → **📦 Content pack** → choose the file → Start.
- **From the command line**, for a fresh install: `CHITS_PACK=$PWD/docs/packs/honey.json make play`
  (use a full path: the server runs from `server/`).

`CHITS_PACK` is only read when the data folder has never held a game. After that the game remembers its own
pack. A new game keeps the pack until you press **No pack**.

## The file

```json
{
  "schema": 1,
  "id": "honey",
  "name": "Honey",
  "version": "1.0",
  "description": "Bees.",
  "author": "you",
  "items": [
    { "key": "skep", "name": "skep", "props": ["woven", "hollow", "shelters bees"], "icon": "🛖" },
    { "key": "honeycomb", "name": "honeycomb", "props": ["edible", "waxy", "sweet"], "food": 15 }
  ],
  "recipes": [
    { "makes": "skep", "inputs": { "fiber": 3, "cord": 1 }, "work": 8 },
    { "makes": "honeycomb", "inputs": { "skep": 1, "berries": 2 }, "qty": 2 }
  ]
}
```

Top level:

| Field | Needed | What it is |
|---|---|---|
| `schema` | yes | `1` |
| `id` | yes | 2-32 of `a-z 0-9 _ -`, starting with a letter |
| `name` | yes | up to 60 characters |
| `version` | no | text, like `"1.0"` |
| `description`, `author` | no | up to 400 and 60 characters |
| `items` | yes | 1 to 32 items |
| `recipes` | yes | 1 to 32 recipes |

An item:

| Field | Needed | What it is |
|---|---|---|
| `key` | yes | 2-32 of `a-z 0-9 _`, starting with a letter. Not a key the game already uses. |
| `name` | yes | lower-case letters, digits, spaces, `'` and `-`. Not a name the game already understands. |
| `props` | yes | 1 to 6 properties, written like the name. Chits see these and reason from them. |
| `food` | no | hunger restored when eaten, 0 to 100 |
| `tool`, `tool_power` | no | `axe`, `pick`, `spear` or `light`, and a power up to 4 (an iron tool) |
| `carry_bonus` | no | extra things it lets a chit carry, 0 to 16 |
| `weight` | no | 1 to 4 |
| `icon` | no | one emoji |

A recipe:

| Field | Needed | What it is |
|---|---|---|
| `makes` | yes | the key of one of the pack's own items |
| `inputs` | yes | item key → amount. Up to 4 kinds and 5 things in total. Base items or the pack's. |
| `station` | no | `fire`, `workshop`, `kiln`, `furnace`, `forge`, `factory`, `mill` or `loom`. Left out: made by hand. |
| `qty` | no | how many it makes, 1 to 4 |
| `work` | no | how long it takes, 1 to 30 |

Unknown fields are refused. The file can be at most 64 KiB.

## The rules

A pack is held to the rules of the base game (`tests/test_item_uses.py`):

- **Every item has a use.** It is food, a tool, a container, something warm to wear (`wearable` and `warm`),
  or an input of another recipe.
- **Every item can be made.** Each item has exactly one recipe, and the chain starts from things the base game
  has. Two items that are only made from each other are refused.
- **Every input and station exists.**
- **No clash.** A recipe can't take the same things at the same place as a base recipe or another pack recipe.
  (A recipe with no station works anywhere, so it clashes with the same inputs at any station.)
- **No renaming.** A pack adds. It can't replace a base item, give a base item a second recipe, or use a name
  the game already understands (`rope` already means cord).

The server says why a pack is refused, for example
`content pack refused: item wax has no use: make it food, a tool, ...`.

## What the game does with a pack

- Each world gets its own copy, in its own catalogue, beside its inventions. The shared tables are not
  changed, so a game without the pack can't see any of it.
- Every world of a game gets the same pack. Twin worlds still differ only in what they are meant to differ in.
- The pack is saved with each world. Its id and sha256 are in the run manifest
  (`data/runs/<run>/manifest.json`), in `/api/health`, and in a replay bundle.
- Making a world with a pack draws no random numbers. The island and the starting chits are the same with or
  without it. After that the two games go their own ways, because different things can be made.
- **Without a pack nothing changes.** The simulation and the saves are what they were before packs existed.
- **Experiment runs refuse packs.** An experiment must differ from the base game only in its intended flags,
  and a pack is not part of any sealed protocol yet. Start the experiment with **No pack**. The Experiment Lab
  (`python -m chits.lab`) and `make experiment` never load one.

## What a pack can't do yet

- **No building designs.** This first version adds items and recipes only. Designs are looked up in one
  shared table in many places (ideas, sites, upgrades, the planners, the observer's art), and doing that per
  world correctly is a larger change.
- **Nothing new to gather.** Every pack item is made from something. The map has no new resources.
- **Instinct uses packs less than models do.** A chit on instinct can stumble on a pack recipe by blind
  experiment, makes it again when asked to, and eats pack food it carries. But the village planners (projects,
  research, the chief) only know the base ladder, and a hungry chit does not fetch pack food from the stores.
- **God mode** drops base items only.
- The observer draws a pack item with its emoji, not pixel art.

## For the careful

A pack file is untrusted input. It is parsed as strict JSON (no NaN, no Infinity), limited in size, and every
field is checked for type and range. Names and properties are limited to plain lower-case words because the
models read them. The New game dialog sends the file's contents, never a path. `CHITS_PACK` is a path chosen by
whoever starts the server, and only that file is read.
