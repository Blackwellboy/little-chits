# T26 · Leaders, elections and laws

**Why:** who leads, and how, is one of the biggest ways civilisations differ. World A can hold elections and
speak laws aloud. World B can't talk, so leadership there can only be *recognised*: the elder everyone gravitates
to. When a model-driven chief issues a decree, it's that model's idea of good government, in its own words.

## Build
1. **State.** Persist all of these; old snapshots load with defaults.
   - `World.leader: str = ""` (an agent id)
   - `World.leader_since: int = -1`
   - `World.laws: List[dict]`, where each law is `{"id","text","by","by_name","tick"}`, at most 10 (the oldest
     drops)
2. **`World.choose_leader(reason)`.** Called from `_new_day` when `day % 10 == 0`, when there is no leader,
   or when the leader has died (check in `kill`, then choose at the next day boundary).
   - Only adults (not `is_child`) can lead or vote.
   - **World A** (`flags["say"]`): an election. Each adult votes for the other adult it likes most, if that
     affinity is ≥ 10. The most votes wins; a tie goes to the older chit. With no votes at all, keep the
     current leader.
     - Emit `"election"`, importance 4: `{name} was elected chief with {n} of {m} votes`.
   - **World B**: no speech, so no votes. The elder is the adult with the highest total affinity from
     others (`sum(o.affinity.get(a.id, 0) for o in adults)`).
     - Emit `"elder"`, importance 4: `{name} is now looked to as the elder`.
   - Emit only when the leader changes. Set `leader_since`.
3. **Decrees** (World A only, where `flags["say"]`). T06's `parse_reflection` also returns `"decree"`: a
   string of 8–120 characters, or `""`. It is also read from the keys `law`/`rule`.
   - `apply_reflection`: if the agent is the leader and there's a decree, append a law, and emit `"law"`,
     importance 5: `Chief {name} decreed: "{text}"`.
   - `reflection_messages` tells a leader that it is chief and may add `"decree": "..."`: a rule for everyone,
     in its own words, only if it believes one is needed.
4. **Everyone sees it.**
   - `scene()` adds `- Your chief is {name}.` (World B: `- {name} is the elder everyone looks to.`).
   - For each law, newest first, at most 3: `- LAW (by {by_name}): {text}`.
   - Laws are soft. The simulator doesn't enforce them; each chit's mind decides whether to follow.
5. **Views and web.**
   - `views.snapshot`/`world_meta` include `leader` and `laws`.
   - The Inspector shows a 👑 on the leader.
   - The People tab pins the leader at the top.
   - The Stats tab lists the laws.
6. **Moments (T11):** `election` 70, `elder` 70, `law` 88.

**Honesty (added after review):** elections every 10 days and elders are an **authored institution**. What
emerges inside it is real: who wins, what the laws say. The chronicle describes it as "World A held its
scheduled election", never as "democracy emerged".

## Done when
`python scripts/plan.py verify T26` passes.
