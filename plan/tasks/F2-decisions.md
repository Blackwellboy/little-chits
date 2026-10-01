# F2 · Decision records, a persistent objective, and stale-plan checks

**Why:** "was that really Qwen, or did instinct make that choice?" must be answerable for every plan. A chit
also needs a lasting *objective* ("somewhere warm before winter") separate from its current *plan* (gather
wood → build fire). Then reflexes can interrupt the plan without erasing the purpose, and we can watch
problem → blocker → replan → result. Finally, a prefetched plan can arrive after the world has moved on, and
that should be visible rather than look like irrational behaviour.

## Build
1. **Agent state.** Persist all of these, with defaults.
   - `Agent.rev: int = 0`, an observation revision. It is incremented by `Agent.bump_rev()` whenever:
     - the chit learns something (`World.learned`)
     - a reflex inserts a step
     - a step fails
     - its home changes
   - `Agent.objective: str = ""` and `Agent.objective_since: int = -1`.
2. **Objective from the model.**
   - `parse_plan` also returns `"objective"`, read from the key `objective` (or `purpose`, `long_term_goal`),
     capped at 140 characters, and `""` if missing.
   - On adopting a model plan: when the objective is non-empty and differs (case-insensitive) from the
     current one, set it, set `objective_since`, and emit `"objective"`, importance 2: `{name} is working
     towards: "{objective}"`. When the reply omits it, the old objective stays.
   - `scene()` shows `YOUR OBJECTIVE (since day N): …` after the YOU line. The system prompt explains
     `objective` (lasting, keep it until it's achieved or abandoned) versus `goal` (this plan).
3. **Decision records.** Every model request produces one record in `Mind.decisions`, a `deque(maxlen=5000)`,
   and is passed to `Mind.on_decision` (a callable or None; the runtime stores records in a new store table
   `decisions(world_id, tick, agent_id, data)`). Fields:
   - identity: `request_id` (uuid4 hex), `world`, `agent`, `brain`, `model`, `base_url`
   - request: `tick_requested`, `rev_requested`, `prompt_version`, `prompt_hash` (sha256 of the messages
     JSON), `temperature`, `max_tokens`
   - reply: `latency_ms`, `tokens_in`, `tokens_out`, `response_hash`, `parse` (`ok`|`repaired`|`retried`|
     `failed`), `rejected_steps`
   - outcome: `outcome` (`pending` → `adopted`|`stale`|`failed`|`discarded`), `tick_resolved`, `plan_id`
     (uuid4 hex, also stored on the agent as `a.plan_id` when adopted)

   The record is mutated in place as it resolves. No hidden chain-of-thought is stored.
4. **Stale check.** When a pending model plan is about to be adopted, it is **stale** if the agent's `rev`
   changed since the request, or more than 120 ticks have passed.
   - A stale plan is dropped (outcome `stale`) and a fresh request is made on the same tick.
   - Instinct plans are never marked stale.
5. **Plan provenance on the agent.** `a.plan_source` is one of:
   - `model:<brain id>`
   - `instinct`
   - `instinct-filler`
   - `instinct-fallback`
   - `waiting` (F1)
   - `reflex`

   `views.agent_detail` shows `plan_source`, `plan_id` and `objective`. The Inspector shows where the
   current plan came from.
6. **API.**
   - `GET /api/worlds/{wid}/decisions?agent=&limit=100` returns the newest first.
   - `GET /api/decisions.jsonl` returns every stored record, one per line.
   - The diagnostics report (diag.py) adds a stale count and a failed count.

## Done when
`python scripts/plan.py verify F2` passes.
