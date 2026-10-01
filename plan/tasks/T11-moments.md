# T11 · Moment detector: find the story beats in the event log

**Why:** thousands of events happen each day. The story engine needs a ranked list of the few that matter, and
each one must cite the real event sequence numbers it came from (no fan-fiction).

## Build
Create `server/chits/story/__init__.py` (empty) and `server/chits/story/moments.py`:

```python
@dataclass
class Moment:
    kind: str; score: int; tick: int; x: float | None; y: float | None
    actors: list[str]   # agent ids, most important first
    text: str           # one plain sentence, built only from event text and `names`
    seqs: list[int]     # the event seq numbers that prove it

def find_moments(events: list[dict], names: dict[str, str]) -> list[Moment]
def top_moments(events, names, since_tick: int = 0, limit: int = 10) -> list[Moment]
```

`events` are `Event.to_dict()` dicts: `seq, tick, kind, text, importance, actor, x, y, data`. `names` maps
agent id to name, and includes the dead.

**Rules.** Scores are ints. One moment per matching event unless the rule says otherwise.

| kind | from | score |
|---|---|---|
| `first` | events of kind `discovery` or `first` | 90, +5 if `data.local_name` |
| `teaching_chain` | ≥3 chits: `learned` events with `data.how == "taught"` for the same `data.knowledge`, where each learner (`actor`) is the next event's `data.source`, each within 480 ticks of the previous | 70 + 5·(chain length − 3), max 95. `actors` in chain order (teacher first). `seqs` = all the taught events. Text: `"{A} taught {B}, who taught {C}{…}: {knowledge name}"`. Emit only maximal chains. |
| `legacy` | kind `legacy` | 80 |
| `built_together` | kind `built` with `len(data.builders) >= 3` | 55 + 5·(n−3), max 80; +15 if `data.first` |
| `lost_pioneer` | kind `death` whose actor was the actor of any earlier `discovery` event | 85 |
| `birth` | kind `birth` | 40, or 60 if `data.generation >= 2` |
| `storm` | kind `storm` | 65 |
| `settlement` | kind `settlement` | 75 |
| `ambition` | kind `ambition` | 45 |

- The knowledge name is `data.knowledge` after `:` with `_` replaced by spaces.
- The `x`/`y`/`tick` of a moment are those of its **last** cited event.
- `find_moments` sorts by score (descending), then tick (descending).
- `top_moments` filters `tick >= since_tick` and applies `limit`.

## Done when
`python scripts/plan.py verify T11` passes.
