# Fleet diagnostics (`t3-fleet list --limited` / `--lineage`)

Read-only, children included; recovery and relaunch stay with the caller and native tools.

**Usage limits (`--limited`):**
- `actionable` = structured root `usage_limit` on the latest **executed** failed run of a top-level or
  launched owner. Queued/cancelled submissions that never started can't hide it; active or later
  successful work and settled threads clear it. `limitRecovery` metadata alone is history, never a
  current limit.
- `suspected` = terminal assistant limit text (even on a completed run): never actionable.
- `review_needed` = a failed delegated task or native child, including runless children with
  rate-limit/HTTP 429 text. Its parent (`recovery_owner_id`) may already have recovered or replaced it:
  never resume those children blindly.

**Lineage (`--lineage`, `--descendants ID`):** parent evidence comes only from structured
subagent/lineage data or the first user message's sender, never project or time proximity; a missing
sender stays unknown.
