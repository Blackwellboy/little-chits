# T13 · X thread generator: the day's story, ready to post

**Why:** at the end of a session you want a thread you can copy-paste straight to X, built only from what
really happened, with both models named.

## Build
Create `server/chits/story/xpost.py`:

```python
def make_thread(worlds: list[dict], moments: dict[str, list], max_posts: int = 6) -> list[str]
def pick_clip(moments: dict[str, list]) -> dict | None
```
- **`worlds`**: `[{"id", "name", "brain", "culture", "day", "stats"}]`, with `stats` as from `World.stats()`.
- **`moments`**: world id → a list of `Moment` or dicts with the same fields (accept both).

**`make_thread`** is deterministic, and every post is ≤ 280 characters (cut long texts with `…`):
1. **Hook** (post 1). With two worlds:
   `Day {day} on a tiny island. Two AI civilisations, same start. 🧠 {A.brain} runs World A (they can talk) vs 🧠 {B.brain} runs World B (they can't). 🧵`
   With one world, adapt the wording. If a moment exists, add a line with the best moment's text.
2. **Moments** (posts 2 … max_posts−1): take the best moments across worlds, alternating worlds when scores
   tie, skipping the one used in the hook. Format: `{emoji} World {id} · {brain}: {text}`.
   Emojis by kind: first ✨, teaching_chain 📚, legacy 📜, built_together 🏗️, lost_pioneer 🕯️, birth 🍼,
   storm ⛈️, settlement 🏘️, ambition 🌟, anything else •.
3. **Scoreboard** (last post):
   `Scoreboard, day {day}: World A — {population} chits, {discoveries} discoveries, {structures} buildings · World B — … #LittleChits #AI`

   The post count is ≤ max_posts, and at least 2 when any world exists.

**`pick_clip`** returns the best-scoring moment as `{"world", "x", "y", "tick", "kind", "text"}`, or None.

**API** `GET /api/story/x?since_day=1&max_posts=6`:
- builds each world's dict (the brain label comes from the runtime's brain summary) and each world's moments
  from its stored events with `tick >= (since_day-1)*240`
- returns `{"posts": [...], "clip": {...} | null}`

**CLI** `python -m chits.story.xpost [--url http://127.0.0.1:8000] [--since-day N]` prints the thread from a
running server, with `---` between posts.

**UI:** add a "𝕏 Thread" button to the Chronicle panel header. It opens a small modal showing the posts, each
with a copy button.

## Done when
`python scripts/plan.py verify T13` passes.
