# T02 · Compact prompt style for small or short-context models

**Why:** a 7–9B GGUF or a model served with a 4k–8k context does better with a shorter prompt. Each brain
should be able to pick one.

## Build
1. `BrainConfig` (in `server/chits/brain/llm.py`): add `prompt_style: str = "full"`. Allowed values are
   `"full"` and `"compact"`.
2. `server/chits/brain/prompt.py`: change the signature to `messages(world, a, style: str = "full")`.
   - `"full"` keeps today's output **byte for byte**.
   - `"compact"` returns the same two messages (system + user) and the same JSON reply contract
     (`{"thought","goal","plan":[...]}`), but:
     - The system prompt is ≤ 1400 characters. List the verbs on exactly one line of the form `Verbs: gather, eat, sleep, …` (comma-separated verb names), not the long guide.
       Drop every verb the world forbids (in stigmergy: no `say`, `teach` or `write`).
     - The scene is ≤ 1800 characters. Include:
       - the time line
       - the needs line
       - the carrying line
       - known recipes and designs
       - the 4 most relevant memories
       - resources in sight
       - up to 4 chits and up to 5 structures
       - the last result
     - The combined length is at least 35% shorter than `"full"` for the same chit.
     - Both styles contain the chit's name and the word `plan`.
3. `Mind._ask` passes `brain.cfg.prompt_style` to `P.messages`.
4. Brains panel (`web/src/ui/BrainsModal.tsx`): add a "Prompt" select (Full / Compact) that saves `prompt_style`.
   Also add `prompt_style` to the `BrainBody` model in `server/chits/app.py`.

## Done when
`python scripts/plan.py verify T02` passes, including the web build.
