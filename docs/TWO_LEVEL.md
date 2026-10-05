# A two-level mind: a fast decision model and a planner

A cascade brain already works in two steps. Most moments are one-letter choices among drafted options. A choice the model is unsure of, or "my own idea", escalates to a full written plan.

With `escalate_to`, the two steps can be **different models**:
- a fast decision model answers the letters (JevK5, a letter-readout decision model; see docs/research/model-landscape-2026-10.md)
- a general planner writes the escalated plans (Gemma 4, Qwen, ...)

```json
"brains": {
  "jev":   {"id": "jev", "prompt_style": "cascade", "escalate_to": "gemma", "base_url": "...", "model": "jevk5-9b-v0.3.3-Q8_0.gguf"},
  "gemma": {"id": "gemma", "base_url": "...", "model": "gemma-4-12b-it-Q4_K_M.gguf"}
}
```

- **No other model stands in for the planner.** If the planner is missing or down, the choice doesn't escalate. The chosen option runs, and the decision record says `denial: "planner unavailable"`.
- **Provenance.** The escalated plan is `model_plan` (docs/PROVENANCE.md). Its record names both the decision brain and the `planner` with its `planner_model`.
- **In the Lab:**
  - the planner's exact config is sealed in `protocol.brains`, and its server is checked before anything runs
  - it is lockstepped and seeded like the decision brain, and taped on the same BrainTape
  - its requests and tokens are reported apart (`compute.planner`), so thinking cost stays visible per level
  - when blind, its name, model file and server are redacted as the arm's own
  - `escalate_to` must name another brain, only a cascade brain may escalate, and a planner doesn't escalate further

## The comparison (plan section 7)

Pre-registered as `docs/protocols/two-level-jev-gemma.json`. Same seeds, island, culture, rules and sampling; the arms differ only in how the mind is built.

The protocol declares `"compare": "architecture"`. Research item 71 lets model arms differ only in the model. A declared architecture comparison may also differ in prompt style and escalation (`ARCHITECTURE_FIELDS`), but sampling, tokens, timeouts and concurrency must still match. The declaration is in the fingerprint.


| Arm | Decides | Writes plans |
|---|---|---|
| `planner_only` | Gemma 4 12B (full prompt) | Gemma 4 12B |
| `jev_plus_gemma` | JevK5 9B (cascade) | Gemma 4 12B |
| `gemma_cascade` | Gemma 4 12B (cascade) | Gemma 4 12B |
| `jev_cascade` | JevK5 9B (cascade) | JevK5 9B |
| `jev_choose` | JevK5 9B (choose: menu only) | none (instinct's drafted options) |

**Outcomes:**
- **Civilisation quality:** discoveries, era, population, starvation, failed steps, loops.
- **Thinking cost:** requests and tokens per chit-day, for each level.
- **Who drove it:** strategic decisions by the model, and the share it wrote itself.

The `jev_choose` arm keeps the menu-only architecture visible. Its plans are all instinct's, which `model_authored_strategic_share` shows. Nothing assumes the two-level mind wins.
