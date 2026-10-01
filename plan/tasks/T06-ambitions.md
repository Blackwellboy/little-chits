# T06 · Ambitions: each model-driven chit chooses a life goal

**Why:** free-thinking growth means chits pursue things *they* chose. "Mo has decided to build the island's
first monument" is a storyline people follow day after day.

## Build
1. `Agent.ambition: str = ""` and `Agent.ambition_since: int = -1`. They must survive `to_dict`/`from_dict`,
   and old snapshots without these fields must still load.
2. `server/chits/brain/parse.py`:
   `parse_reflection(text) -> {"lessons": list[str], "ambition": str}`.
   - Lessons follow the same rules as `parse_lessons`, which you should keep, implemented via
     `parse_reflection`.
   - `ambition` is the `ambition`/`goal`/`dream` string. Strip it and cap it at 120 characters. It is `""`
     if missing or shorter than 6 characters.
3. `server/chits/brain/mind.py`: `apply_reflection(world, agent, text) -> dict`.
   - This is a plain function holding the logic `_reflect` has today. `_reflect` calls it.
   - It adds new lessons, keeping at most 6.
   - If the ambition is non-empty and differs from the current one (case-insensitive): set
     `agent.ambition`, set `ambition_since = world.tick`, and emit event kind `"ambition"`, importance 3,
     text `{name} set their heart on: "{ambition}"`, with `data={"ambition": ...}`.
   - Returns the parsed dict.
4. `prompt.reflection_messages`:
   - Ask for `{"lessons":[...],"ambition":"..."}`.
   - Tell the chit its current ambition, if it has one, and that it may keep it or choose a new one.
     The ambition should be something ambitious but possible in this world.
5. `prompt.scene` and the compact scene (if T02 is done): when the chit has an ambition, add the line
   `YOUR AMBITION: <text>` directly after the YOU line.
6. `views.agent_detail`: add `ambition`. `web/src/ui/Inspector.tsx` shows it as a highlighted line under the
   personality ("🌟 <ambition>").
7. Update `tests/fake_llm.py` so reflection replies also include an `"ambition"`
   (e.g. `"Build a warm home for everyone before winter"`).

## Done when
`python scripts/plan.py verify T06` passes.
