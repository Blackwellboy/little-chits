# T05 · Chits name their inventions

**Why:** "Pip invented the *Chopper*" is a post; "Pip discovered stone axe" isn't. Each world develops its
own vocabulary, and World A and World B will call the same thing different names.

## Build
1. **Step argument.** An `experiment` step may carry `"name": "<what the chit calls it>"`.
   - In `server/chits/brain/parse.py` `normalize_step`: for verb `experiment`, keep a `name` key as `name`.
     Today `name` is mapped to `to`; keep that mapping for every other verb.
   - Also accept `call`/`called` as synonyms for experiment steps.
2. **Sanitising** is `sanitize_name(raw) -> Optional[str]` in `server/chits/sim/actions.py`:
   - keep letters, digits, spaces, `'` and `-`
   - collapse runs of whitespace
   - strip
   - cut to 24 characters, then strip again
   - return None if the result is empty or doesn't contain a letter
3. **World.**
   - Add `World.culture_names: Dict[str, str]`, mapping a knowledge key to a local name.
   - In `_do_experiment`: when the experiment produces a recipe that is a **first for the world** and the step
     has a valid name, store `world.culture_names["recipe:<key>"] = name`. Do this *before* calling
     `world.learned`, so the discovery event includes the name.
   - Only the first discoverer names it. Later names are ignored.
4. **Events.**
   - `World.learned`: if `culture_names` has the key, the discovery text becomes
     `{name} discovered how to make {item} and named it "{local}" — a first for the world!`.
   - Put `name` in the event `data` (as `local_name`) for every discovery and learned event whose key has a
     local name.
5. **Prompt.**
   - In `scene()`, each known recipe with a local name is shown as `... -> stone axe (called "Chopper" here)`.
   - In `verb_guide`, the experiment line mentions the optional `"name"`.
6. **Persistence.** `to_dict`/`from_dict` include `culture_names`; a missing key restores as `{}`.
7. **Views.** In `views.knowledge_table`, each world entry gains `local_name` (a str or None). In the Knowledge
   tab (`web/src/ui/SidePanel.tsx`), show the local name in quotes under each world's cell.

## Done when
`python scripts/plan.py verify T05` passes.
