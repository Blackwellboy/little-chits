# T22 · Deep time: eras, the long ladder, and a rocket

**Why:** "can they eventually get to space?" Yes, lawfully and slowly. The ladder from copper to a rocket is
long, expensive and needs a big population. It also needs knowledge to survive many generations, because
chits live 45–70 days. That makes the twin-world question sharper. Does a world that can teach and write
(A) reach the stars sooner than one that can only watch and leave marks (B)? Does it get there at all?

Nothing here is a script. Every step is still discovered by experiment (or invention, T20), and every
building is still imagined from knowledge. This task only makes the world's physics deep enough.

## Build
1. **Items** (`server/chits/sim/items.py`). Add these with the props given; the props are the chits' only
   hints.

   | key | name | props | extra |
   |---|---|---|---|
   | iron | iron | metal, hard, dark, holds an edge | |
   | iron_axe | iron axe | tool, cuts wood, metal | tool axe 4.0 |
   | iron_pick | iron pick | tool, breaks rock, metal | tool pick 4.0 |
   | wheel | wheel | round, rolls, sturdy | |
   | cart | cart | container, rolls, large | carry_bonus 16, weight 3 |
   | paper | paper | thin, flat, can be inscribed, light | |
   | steel | steel | metal, very hard, springy | |
   | gear | gear | toothed, precise, metal | |
   | engine | steam engine | hot, powerful, turns wheels | weight 3 |
   | wire | copper wire | thin, metal, conducts lightning | |
   | magnet | magnet | metal, pulls iron, invisible force | |
   | dynamo | dynamo | spins, makes lightning, humming | weight 2 |
   | lightbulb | light bulb | glass, glows with lightning | tool light 2.0 |
   | fuel | rocket fuel | volatile, burns violently | |
   | alloy | alloy | light, strong, heat-proof, metal | |
   | rocket_part | rocket section | huge, shaped, heat-proof | weight 4 |

2. **Stations.** `STATIONS` gains `forge` and `factory`.
3. **Recipes.**

   | output | inputs | station | qty | work |
   |---|---|---|---|---|
   | iron | 2 ore + 2 charcoal | furnace | 1 | 12 |
   | iron_axe | iron + wood | workshop | 1 | 10 |
   | iron_pick | iron + wood + cord | workshop | 1 | 10 |
   | wheel | 2 wood + iron | workshop | 1 | 10 |
   | cart | 2 wheel + 2 wood | workshop | 1 | 12 |
   | paper | 3 fiber | workshop | 2 | 8 |
   | steel | 2 iron + charcoal | forge | 1 | 14 |
   | gear | steel | workshop | 2 | 10 |
   | engine | 2 steel + 2 gear + pot | forge | 1 | 20 |
   | wire | copper | factory | 3 | 8 |
   | magnet | iron + wire | factory | 1 | 10 |
   | dynamo | magnet + 2 wire + engine | factory | 1 | 20 |
   | lightbulb | glass + wire | factory | 1 | 8 |
   | fuel | 2 charcoal + pot | factory | 1 | 10 |
   | alloy | steel + copper | factory | 1 | 12 |
   | rocket_part | 2 alloy + engine | factory | 1 | 24 |

   Paper is an alternative writing surface: `write` accepts `paper` when there's no `clay_tablet`.
4. **Designs.** Add `min_pop: int = 0` to `Design` and to `_d(...)`. Starting a new construction site of a
   design fails, with a message containing `people`, when `len(world.agents) < min_pop`. A great work needs
   a great many hands.

   | key | name | materials | work | prereqs | size | station | min_pop | decay |
   |---|---|---|---|---|---|---|---|---|
   | forge | forge | 10 brick, 4 iron, 6 stone | 80 | recipe iron | 2×2 | forge | 0 | 1.0 |
   | factory | factory | 20 brick, 8 steel, 2 engine | 150 | recipe engine | 3×3 | factory | 20 | 1.0 |
   | launch_pad | launch pad | 40 brick, 20 steel, 6 rocket_part, 10 fuel, 2 dynamo | 400 | recipes rocket_part, fuel, dynamo | 3×3 | – | 40 | 0.3 |

   - Blurbs:
     - forge: `a blast forge hotter than any furnace, for steel and engines`
     - factory: `machines that make machines`
     - launch_pad: `a tower and a rocket: the island's reach for the sky`
   - `normalize_design`:
     - `forge` now maps to `forge`, **not** furnace. Keep `smelter` → furnace.
     - Add `rocket`, `launch pad`, `spaceport` → `launch_pad`, and `mill`, `works` → `factory`.
5. **The launch.**
   - When a `launch_pad` completes, the crew is its **top 3 builders by contribution**. Each crew member gets
     `Agent.astronaut = True`, which is persisted and defaults to False.
   - Emit `"launch"`, importance 5, text
     `{crew names} rode the first rocket into the sky — {world name}'s first astronauts!`, with data
     `{"crew": [ids]}`.
   - Astronauts keep living normally afterwards. Their memories get
     `I saw the whole island from the sky` (importance 5).
6. **Eras.**
   - `ERAS` in `server/chits/sim/world.py` is an ordered list of `(name, knowledge key)`:
     1. `("Wanderers", None)`
     2. `("Firekeepers", "design:campfire")`
     3. `("Toolmakers", "recipe:stone_axe")`
     4. `("Farmers", "design:farm")`
     5. `("Potters", "recipe:pot")`
     6. `("Scribes", "recipe:clay_tablet")`
     7. `("Copper Age", "recipe:copper")`
     8. `("Iron Age", "recipe:iron")`
     9. `("Machine Age", "recipe:engine")`
     10. `("Electric Age", "recipe:dynamo")`
     11. `("Space Age", "design:launch_pad")`
   - `World.era() -> Tuple[int, str]` is the highest index whose key is in `self.first` (index 0 always
     counts).
   - `World.update_era()`: if `era()[0]` is above the stored `self.era_index`, store it and emit `"era"`
     (importance 5): `{world name} enters the {Era}`, data `{"era": name, "index": i}`.
     - Call it from `_new_day`, from the discovery branch of `learned`, and after a first build in
       `complete_structure`.
     - Persist `era_index` (default 0).
   - `stats()` includes `"era"` (the name). `clock()` includes `"era"`.
   - `scene()` includes the line `- Your people live in the {Era}.`
   - The web top bar clock pill shows the era name. The Stats tab shows the era reached for each world.
7. **Moments (T11):** `era` scores 85 (Space Age: 99). `launch` scores 99.

**Claims (added after review):** this is an **authored** progression. If a world reaches the rocket, say "the
civilisation autonomously discovered and traversed an authored physical progression", not "they invented
rocketry". Pretrained models already know human technology, so a future *research mode* could rename
materials, randomise properties and reshuffle recipes by seed, so that prior knowledge can't shortcut
discovery.

## Done when
`python scripts/plan.py verify T22` passes.
