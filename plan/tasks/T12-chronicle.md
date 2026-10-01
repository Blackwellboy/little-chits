# T12 · Daily chronicle files, with an evidence-checked historian

**Why:** every in-game day becomes a readable markdown page: the raw material for X threads, and a history you can
scroll back through. The model may narrate it vividly, but a validator throws out invented facts.

## Build
Create `server/chits/story/chronicle.py`:

```python
def daily_facts(world: dict, day: int, events: list[dict], stats: dict | None, names: dict[str, str]) -> dict
def render_markdown(facts: dict) -> str
def validate_narration(text: str, facts: dict, known_names: set[str]) -> list[str]
async def narrate(brain, facts: dict, known_names: set[str]) -> str | None
def write_day(data_dir: Path, facts: dict, narration: str | None = None) -> Path
```

- **`world`** is `views.world_meta(w)` plus an optional `"brain"` label.
- **`daily_facts`** takes the events whose `tick // 240 + 1 == day`, and returns:
  - `world`: id
  - `world_name`, `brain` (or `""`), `day`
  - `counts`: kind → n
  - `stats`
  - `agents`: sorted unique names of every actor in the day's events, via `names`
  - `events`: `[{"seq", "text"}]` for importance ≥ 2, at most 40, in seq order
  - `moments`: up to 6 `dataclasses.asdict(Moment)` from `story.moments.find_moments` for that day's events
- **`render_markdown`**:
  - starts with `# {world_name} — Day {day}`
  - then a one-line summary built from counts, e.g. `3 discoveries · 2 buildings finished · 1 birth`
  - then `## Highlights`: one bullet per moment (else per event), each ending with its citation(s) like `(#123)`
  - then `## Numbers`: population, discoveries, structures from stats
- **`validate_narration`** returns a list of problems (empty = valid):
  1. It must cite at least one `(#seq)`, and every cited seq must be in `facts["events"]` or a moment's `seqs`.
  2. Every word in `known_names` (the world's chit names, alive or dead) that appears in the text must be in
     `facts["agents"]`.
  3. Every integer in the text, except inside `(#…)` citations, must appear somewhere in the facts
     (`day`, counts values, stats values, or inside an event text).
- **`narrate`**:
  - Ask the brain, as a *historian*, for 100–200 words: vivid but strictly factual, citing `(#seq)`.
  - Validate the reply. If it fails, retry once and include the problems in the retry.
  - Return the text, or None. Never raise.
- **`write_day`** writes `data_dir/stories/{world}/day-{day:03d}.md`: the markdown, plus
  `\n## The day, told\n\n{narration}\n` if a narration was given. Return the path.
- **`Runtime.write_chronicle(world, day) -> Path`**:
  - builds facts from the store's events for that day
  - writes the markdown immediately
  - if the world's brain is a model, schedules `narrate` in the background and rewrites the file when it
    returns
  - is called automatically at `tick % 240 == 10` for the previous day
- **`GET /api/worlds/{wid}/stories/{day}`** returns `{"markdown": ...}`, or 404.

**Truth layer (added after review):** checking names and numbers isn't enough. "Mara courageously rallied the
village and saved everyone" passes those checks when the events only say "Mara delivered wood".
- `daily_facts` event entries also carry `"kind"`: `{"seq", "kind", "text"}`.
- `validate_narration` also flags these word families unless a supporting fact exists:
  - **causation:** because, so that, which led, caused, saved, thanks to → always flagged (the facts record
    what happened, not why)
  - **emotion and motivation:** courageous(ly), brave, frightened, afraid, angry, loved, desperate,
    determined → needs a `speech` event in the facts from a chit named in the same sentence
  - **leadership:** led, rallied, chief, leader, commanded → needs an `election`, `elder` or `law` event in
    the facts (T26)
  - **superlatives:** first, best, greatest, only → "first" needs a `first`/`discovery` fact; the others are
    always flagged
- Problems are listed as `unsupported <family>: "<word>"`. See `plan/acceptance/test_t12b_truth.py`.

## Done when
`python scripts/plan.py verify T12` passes.
