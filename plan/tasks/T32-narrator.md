# T32 · The narrator: one storyteller for every world

**Why:** in T12, each world's own model tells its own day. That's charming, but in model vs model it means the
better *writer* seems to have the better *world*. A separate narrator model gives both worlds the same voice,
so the story compares like with like. A weekly saga gives you a ready-made long post.

## Build
1. **Config.** `Mind.narrator: str = ""` holds a brain id, or `""` for none. It is persisted in `brains.json`
   as `"narrator"` and returned by `Mind.status()` as `"narrator"`.
   - `POST /api/narrator {"brain": "<id>|"}` sets it: 404 for an unknown id, `""` clears it.
2. **Who narrates.** `Runtime.narrator_brain(world) -> Optional[LLMBrain]` returns the narrator brain if one
   is set and healthy. Otherwise it returns the world's own brain if that's a model (T12's behaviour), or
   None. T12's scheduling uses it.
3. **Weekly saga.** Every 7 in-game days, `Runtime.write_saga(world, week) -> Path` gathers that week's daily
   facts (T12 `daily_facts` for each day) and the top 10 moments (T11). It writes the template version at
   once and returns its path. When a narrator brain is available, it also schedules the narration in the
   background and rewrites the file when that finishes, as T12 does. The narration:
   - asks the narrator for 2–4 short paragraphs, validated by T12's `validate_narration` (only real names;
     numbers must appear in the facts)
   - falls back to a template made from the top moments when there's no narrator or validation fails
   - writes `stories/<world>/week-<nn>.md`, starting with `# {world name} — Week {n}`
   - `GET /api/worlds/{wid}/sagas/{n}` returns `{"markdown"}` (404 when missing), and
     `GET /api/worlds/{wid}/sagas` lists them
4. **Web.**
   - The Brains panel gets a **✒ Narrator** select.
   - The Chronicle's "By day" view shows the told text with a small `✒ told by {label}` line.
   - A "Weeks" toggle shows the sagas.

## Done when
`python scripts/plan.py verify T32` passes.
