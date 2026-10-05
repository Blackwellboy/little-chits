# World rules

A world's **rules** say what kinds of civilisation are possible in it. Two examples are whether religion can emerge, and (later) whether chits can invent, or islands can meet. They are one record, `WorldRules` in `server/chits/sim/rules.py`, with these properties:

- **Chosen once.** They are set when a world is made: New Game (`POST /api/reset` with `"rules": {...}`), a Lab protocol (`"rules": {...}`), or the harness (`--rules '{...}'`). They never change while the world runs. The record is a frozen dataclass, and there is no API that edits it mid-game. If a foundational rule may change later, the change must fork the timeline (a new epoch) and record it.
- **Saved and shown.**
  - Every saved world carries the record (`"rules"`). Save points, save files, rewinds and forks bring it back as it was.
  - It appears in `GET /api/rules`, in each world's metadata (`world_meta`) and in the run manifest.
  - A save file whose worlds have different rules is refused as "not one game".
- **Versioned.**
  - `RULES_VERSION` (now 2) is saved inside the record.
  - A record from a newer build is refused, never reinterpreted, and so is an unknown rule name or a value that isn't `true` or `false`.
  - A record from an older version comes forward with each missing rule at its default.
- **Legacy by default.** Each rule's default is how worlds behaved before the rule existed.
  - A world saved before rules has no record. It loads as the legacy set (`WorldRules.from_dict(None)`) and plays exactly as it did.
  - The snapshot schema is unchanged (2): the frozen contract `plan/acceptance/test_f3_identity.py` pins it, so the rules record carries its own version instead.
- **Shared by twins.** Both worlds of a game get the same rules. World A and World B still differ only in `CULTURE_FLAGS` (AGENTS.md).

## The rules

| Rule | Default | Label | Off means |
|---|---|---|---|
| `religion` | on | Religion & belief can emerge | No faith can be founded, joined, inherited, preached, prayed to or read from a tablet. Shrines can't be imagined, taught or built, and prompts say nothing of belief. |
| `invention` | on | Chits can invent new things | No named inventions. `invent` is refused ("nobody in this world invents new things (they can still experiment)") and never offered or described. Experimenting stays: it is how the world's own recipes are discovered. |
| `library_hints` | on | Libraries may hint at undiscovered technology | Studying still trains scholars, but no insight builds up and the scholars never get an idea of a recipe nobody knows. |
| `lore_rescue` | on | Protect endangered knowledge | The last old keeper of a recipe gets no reminder in its prompt and no instinct plan to teach it or write it down. Knowledge can die out, and that is still recorded. A printing press the chits built still prints: it is their own technology, not a rescue. |
| `storyteller` | on | The storyteller may stir things up | No play-mode storyteller events: hard winters, droughts, sickness, fires, a wolf pack, a meteorite, a stranger, a bumper harvest. Experiments never have them anyway. |
| `wanderers` | on | Wanderers may join a village | No newcomers wander into a shrinking village. Experiments never have them anyway. |

**Version history.**
- Version 1 had `religion` only.
- Version 2 added the other five rules.

A version-1 record comes forward with the new rules at their defaults, which is what such a world always had.

**Considered and not made rules (yet).**
- **Technological ages** drive village projects and much of the game. They can't be switched off cleanly.
- **Elections and government:** a chief names the village's projects. Without one, projects need another way to be chosen first.
- **Combat and theft:** wolves are nature, and watchtowers and lamps exist for them. A rule here needs to separate chit-against-chit conflict from the wild first (issue #11).
- **Contact between islands** is already a match setting (the game mode and the "Allow contact" choice), and it is recorded in the run manifest.
- **Markets:** the market is a building whose only effect is on trade. It belongs with trade, if trade ever becomes a rule.

**Presets** (New Game; `GET /api/rules` lists them):

| Preset | Rules | Model-led | For |
|---|---|---|---|
| Standard | all on | no | Little Chits as intended |
| Model-led | all on | yes | the model supplies the intelligence; the chit keeps its body (docs/MODEL_LED.md) |
| Research Clean | religion, library hints, lore rescue, storyteller and wanderers **off**; invention on | yes | fewer hidden mechanics. Closer to a clean test, but play is not a controlled experiment, so use the Lab |
| Sandbox | all on | no | fun rather than claims |

Research Clean keeps invention, because inventing is the chits' own act. It removes the shared mechanics that blur a causal claim: a belief system that isn't research-ready, hints from outside the chits, rescue nudges, and outside events. The storyteller and wanderers already never run in experiments.

The running game shows its rules, read-only, in the 📜 **Rules** panel.

### Religion off: every path, and where it is closed

`tests/test_world_rules.py` tests each path in a pair. With religion on, the effect happens, which shows the test reaches the path. With religion off, it doesn't. Every gate was mutation-checked: removing any one fails a test.

| Path | Gate |
|---|---|
| Founding a faith (reflection, the holy book, a near-copy that joins) | `World.found_belief` returns nothing |
| Joining: conversion by prayer, preaching, reading a tablet, birth (a child of two co-believers), reflection | `World.convert` refuses |
| `pray` and `preach` | refused at dispatch (`actions.run`) with the exact reason: "there is no religion in this world, so nobody can pray" |
| Writing a belief down (scripture tablets) | `_do_write` sees no belief |
| A reflection naming a conviction | it is dropped from the parsed record, and nothing is founded |
| The holy book (god mode) | only a strange old book: no mood and no faith |
| Co-believers warming to each other; a believer's mood by its own shrine | `World._belief_tick` has no followers |
| The shrine design, by any route (insight, teaching, reading, study) | `World.learned` refuses `design:shrine`. A shrine can't be built by a chit that can't know it |
| A Lab treatment that teaches the shrine | the protocol is refused (`SpecError`), not half-applied |
| Prompts: the `pray`/`preach` verbs, "write ... belief", the reflection's invitation to a faith | left out |

Checked and found not to need a gate:
- There is no belief-linked work speed.
- There is no religious village project. Instinct never plans `pray` or `preach`, and its only religious plan, a shrine, needs a belief.
- The golden idol (god mode) lifts mood nearby but is not coded as religion, so it stays.

**This rule does not make the belief system research-ready.** Switching religion on gives today's T21 belief system, which `docs/RESEARCH_READINESS.md` (gates C and D) does not count as a worldview engine fit for causal claims. Religion off is a clean control: no belief exists.

## Using rules

- **New Game.**
  - Send `"rules": {"religion": false}` with `POST /api/reset`. Leave the field out to keep the current game's rules.
  - `GET /api/rules` lists every rule (label, default, what off means), the current rules, and each world's rules.
- **Lab.** A protocol takes `"rules": {...}`, which applies to every arm.
  - It enters the protocol fingerprint only when set, so older protocols keep theirs.
  - The manifest records the full rule set as `world_rules`.
- **Harness.**
  - Run one world: `tools/harness/run.py SEED --rules '{"religion": false}'`.
  - A/B a rule on one tree: `tools/harness/ab.py TREE TREE --new-rules '{"religion": false}'`.

## Adding a rule

1. Add it to `RULES` (default, label, what off means) and to `WorldRules`. The default must keep today's behaviour. Bump `RULES_VERSION`.
2. Gate every path it covers, and write a paired on/off test for each path. Mutation-check the gates.
3. Check what depends on the system. A rule that would leave recipes, buildings or actions with no purpose needs those handled, or it isn't a clean rule.
4. Document it here.
