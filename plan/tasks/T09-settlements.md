# T09 · Settlements: villages emerge and get names

**Why:** "The village of Mossbrook, founded on day 6 by Pip and Mo, now has 14 chits". Settlements are
*inferred* from what the chits built, never assigned.

## Build
New module `server/chits/sim/settlements.py`:

```python
@dataclass
class Settlement:
    id: str               # the numerically smallest structure id in the cluster, e.g. 's3' < 's12' (stable over time)
    name: str
    x: float; y: float    # centroid of the cluster's structure centers
    structures: list[str] # structure ids, sorted by their number
    homes: int
    residents: list[str]  # ids of living agents whose home is in the cluster, sorted
    founded: int          # tick the settlement was first detected

def detect(world) -> list[Settlement]
def village_name(seed: int, sid: str) -> str
```
- **Clustering** uses complete, non-ruined structures. Two structures are linked if their footprints are within
  8 tiles (`Structure.dist` on a center tile is fine). Clusters are the connected components.
- A cluster is a settlement when it has **≥3 structures including ≥2 homes** (hut/brick_house).
- `village_name` is deterministic from `(seed, sid)`: two parts from fixed word lists, e.g.
  `Moss`+`brook`, `Stone`+`hollow`, `Ember`+`ford`.
- `World.settlements: Dict[str, dict]` keeps each settlement's `name` and `founded` once it has been seen, so
  the name stays stable. Persist it, defaulting to `{}`.
- `World.update_settlements() -> list[Settlement]`, called every 60 ticks from `step`:
  - For each settlement detected for the first time, emit `"settlement"`, importance 4:
    `The village of {name} was founded by {up to 3 resident names}` (use builder names if there are no
    residents yet), with `data={"settlement": id, "name": name}`.
  - When a settlement's residents first reach 10 and 20, emit `"village_growth"`, importance 3.
- **API:** `GET /api/worlds/{wid}/settlements` returns a list of dicts (the dataclass fields plus
  `population` = len(residents)).
- **Prompt:** when a chit's home is in a settlement, the YOU line says `… at (x,y) in the village of {name}`.
- **Stats:** `World.stats()` gains `"settlements": <count>`.

## Done when
`python scripts/plan.py verify T09` passes.
