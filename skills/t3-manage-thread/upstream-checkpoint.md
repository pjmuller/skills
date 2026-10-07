# Upstream replacement checkpoint

Before extending these helpers, check upstream native orchestration. Last
checked 2026-10-07, T3 stable v0.0.45: nothing native on stable (no `t3 thread`
CLI, no thread MCP tools); the internal dispatch contract is unchanged since
v0.0.43 and `t3-spawn-thread --dry-run` passes. Thinking traces are message rows
(`role = 'reasoning'`, [#11784](https://github.com/pingdotgg/t3code/pull/11784)),
which every store reader here skips.

**Main is a different product since 2026-10-02:** Orchestrator V2
[#2829](https://github.com/pingdotgg/t3code/pull/2829) merged, nightly 0.0.46 only.
When it reaches stable, every helper here breaks before anything can be retired:

- `POST /api/orchestration/dispatch` is gone; commands go over the WS RPC
  `dispatchCommand` (`ORCHESTRATION_V2_WS_METHODS`, ticket from
  `/api/auth/websocket-ticket`). `thread.turn.start` → `message.dispatch`,
  `thread.meta.update` → `thread.metadata.update`; `thread.create`,
  `thread.settle`, `thread.snooze`, `thread.delete`, `thread.auto-settle.set` keep
  their names (payloads to re-check). Port `scripts/lib` `t3_dispatch` first.
- Store: V1 `state.sqlite` is copied once into `statev2.sqlite` and frozen;
  threads live in `orchestration_v2_projection_threads/messages/runs/subagents`.
  Port `t3-read-thread`, `t3-fleet`, `t3-find-thread`, `t3-usage-windows limited`,
  `t3-purge-threads`, `t3-my-prompts`.
- Native agent tools on main: `t3_thread_launch`, `create_threads`,
  `t3_thread_send/read/list/search/wait/interrupt/fork`, `t3_thread_update`
  (rename), `delegate_task` (async completion wakes the parent) + `task_status`,
  scheduled tasks (`fixed_time {timeOfDay, weekdays}`, `interval`, `webhook`),
  `t3_thread_organize` (pin/snooze/settle/unsettle/archive). Per-tool caller
  declarations [#16335](https://github.com/pingdotgg/t3code/pull/16335).
- `message.dispatch` still clears a snooze (`thread.unsnoozed`), so the
  `t3-hide-thread` keeper survives V2 ([#6368](https://github.com/pingdotgg/t3code/issues/6368)
  closed by the merge, hold-until-time snooze [#14625](https://github.com/pingdotgg/t3code/issues/14625) open).

- **History:** Orchestrator V2 [PR #2829](https://github.com/pingdotgg/t3code/pull/2829)
  carried native `create_threads`, `t3_thread_start/send/wait/read/list/interrupt`,
  `delegate_task` and scheduled tasks (plus the `agents/mcp-*` stack #10554–#10566).
  On 2026-09-19 the maintainer closed every main-branch orchestration/provider PR
  pending V2: settle backport [#11303](https://github.com/pingdotgg/t3code/pull/11303),
  [#11360](https://github.com/pingdotgg/t3code/pull/11360),
  [#11864](https://github.com/pingdotgg/t3code/pull/11864), rename
  [#12018](https://github.com/pingdotgg/t3code/pull/12018) (retire
  `t3-rename-thread` when `t3_thread_update` appears), snooze-wake fix #7179
  (for [#6368](https://github.com/pingdotgg/t3code/issues/6368), the reason
  `t3-hide-thread` needs a keeper), background wake #10183.
- [#11795](https://github.com/pingdotgg/t3code/pull/11795) (`create_threads` backport)
  closed unmerged 2026-10-02. Shipped v0.0.43: auto-settle opt-out
  [#11846](https://github.com/pingdotgg/t3code/pull/11846), command
  `thread.auto-settle.set {threadId, enabled}` behind capability
  `threadAutoSettleOptOut` — the way to keep a long-idle hidden 🏓 worker from
  being auto-settled (= killed); `t3-spawn-thread` sends it for hidden spawns.
  Tracker: [#8433](https://github.com/pingdotgg/t3code/discussions/8433).
- V2's blocking `delegate_task mode:"wait"` hits the 300 s HTTP ceiling
  ([#11168](https://github.com/pingdotgg/t3code/issues/11168)): keep the async 🏓
  ping-back shape even after switching.

Switch only once the tools ship on stable, appear in the active tool list, and
still hold what these helpers guarantee: visible top-level threads,
project/worktree selection, provider/model inheritance, focus, cross-project
safeguards, send/steer/queue semantics, idempotency, parent wake-up.
