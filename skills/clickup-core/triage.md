# Solve first, escalate late

For a product owner (PO) or support person working a ticket with their coding agent. The
developer's attention is the bottleneck: a ticket reaches them only when it needs them. Defaults,
not gates: the wrapper owns scope, review and deploy policy.

**Incidents first:** an active outage, security or data-loss risk follows the project's escalation
policy immediately; investigate in parallel, don't delay the alert.

## Default: agent + PO take the first attempt
- **UI/UX**: copy, layout, flow, defaults, convenience actions ("import all fields").
- **Specific bug**: exact error, 500/503, failing upload/embed, wrong value on one screen.
  Reproduce → logs/trace → root cause → fix + test.

Implement when the expected behavior (and a bug's cause) is clear in plain words, regression risk
is low and the change can be checked (browser or test); then the project's review/deploy policy.
Implementing grants no production access. A PO who can't merge hands off a **fix to review**, not
a problem to solve.

## Escalate, after a real attempt, when
- material doubt remains about cause, fix or regression risk (no repro, several plausible causes);
- the change crosses project boundaries (code/APIs shared with other products);
- the environment blocks you (below).

Escalate unless the investigation clears it: caching/state sync, background jobs, concurrency,
auth/permissions, billing, stored data (migration, backfill, bulk edit), infra. Example: "new
fields don't appear in the builder" smells like cache → investigate, escalate with findings unless
the cause is clear and local.

## The escalation carries the investigation
First line, gradable by the developer and a later retro: **Needs developer because:**
`env gap` · `authority` · `cross-boundary` · `unresolved doubt` · `incident`, plus five words of
why. Without it the ticket goes back to the PO's agent. Then: symptoms + repro, what was checked
(logs, data, recent commits), hypotheses ruled in/out, the branch/diff of any attempt, the doubt
that made you stop. Shape: skill `agents-md` → `handoff.md`.

## Name environment gaps
Blindfolded (missing env var/secret, no log/DB/staging access, app won't run locally, no test
data) → one line: **Env gap: missing X, would have unlocked Y.** The developer picks the fix
(access, a safe alternative, or none: missing deploy rights may be deliberate).

## Before assigning to the developer
Only escalate-bucket work gets assigned. A developer's agent receiving a default-bucket ticket
checks the evidence, then hands it back in one line naming the env gap that blocked the PO's agent,
if any.
