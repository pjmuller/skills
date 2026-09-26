# Upstream replacement checkpoint

Before extending these helpers, check upstream native orchestration. Last
checked 2026-09-23, T3 v0.0.42: nothing on stable (no `t3 thread` CLI, no thread
MCP tools, no provider-facing send/settle/snooze/rename tool).

- **Gate:** Orchestrator V2 [PR #2829](https://github.com/pingdotgg/t3code/pull/2829),
  unmerged, already carries native `create_threads`, `t3_thread_start/send/wait/read/list/interrupt`,
  `delegate_task` and scheduled tasks (plus the `agents/mcp-*` stack #10554–#10566).
  On 2026-09-19 the maintainer closed every main-branch orchestration/provider PR
  pending V2: settle backport [#11303](https://github.com/pingdotgg/t3code/pull/11303),
  [#11360](https://github.com/pingdotgg/t3code/pull/11360),
  [#11864](https://github.com/pingdotgg/t3code/pull/11864), rename
  [#12018](https://github.com/pingdotgg/t3code/pull/12018) (retire
  `t3-rename-thread` when `t3_thread_update` appears), snooze-wake fix #7179
  (for [#6368](https://github.com/pingdotgg/t3code/issues/6368), the reason
  `t3-hide-thread` needs a keeper), background wake #10183.
- Still open on main: [#11795](https://github.com/pingdotgg/t3code/pull/11795)
  (`create_threads`), auto-settle opt-out [#11846](https://github.com/pingdotgg/t3code/pull/11846).
  Tracker: [#8433](https://github.com/pingdotgg/t3code/discussions/8433).
- V2's blocking `delegate_task mode:"wait"` hits the 300 s HTTP ceiling
  ([#11168](https://github.com/pingdotgg/t3code/issues/11168)): keep the async 🏓
  ping-back shape even after switching.

Switch only once the tools ship on stable, appear in the active tool list, and
still hold what these helpers guarantee: visible top-level threads,
project/worktree selection, provider/model inheritance, focus, cross-project
safeguards, send/steer/queue semantics, idempotency, parent wake-up.
