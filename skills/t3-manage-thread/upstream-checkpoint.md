# Upstream replacement checkpoint

Before extending these helpers, check upstream native orchestration. Orchestrator V2
[PR #2829](https://github.com/pingdotgg/t3code/pull/2829) is unmerged but already
contains native `create_threads`, `t3_thread_start`, `t3_thread_send`,
`t3_thread_wait/read/list/interrupt`, and `delegate_task` MCP tools. Follow-up
[PR #8678](https://github.com/pingdotgg/t3code/pull/8678) adds cross-project and
worktree launch strategies.

Switch only after they ship on stable *and* appear in the active tool list, and
only once the behaviours these helpers were built to guarantee still hold:
visible top-level threads, project/worktree selection, provider/model
inheritance, focus, cross-project safeguards, send/steer/queue semantics,
idempotency, parent wake-up. Until then this skill is the stable wrapper around
T3's internal authenticated dispatch.
