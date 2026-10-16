# Native workers (T3 ≥ 0.1.0)

Verified first-hand on T3 0.1.0, 2026-10-16 (14 disposable experiments; evidence in
macbook_setup `decissions/t3_native_workers.md`). Needs an agent running inside a T3 thread.

## 🏓 round-trip worker = `delegate_task`

```text
id = $(t3-pick-instance sol)          # capacity routing; prints e.g. codex_dentai
delegate_task {task: "Read and execute /abs/brief.md", title: "<3-6 words>",
  mode: "async", role: "review", clientRequestId: "<stable per round>",
  target: {providerInstanceId: id, model: "gpt-6.1-sol", options: {reasoningEffort: "high"}}}
→ end your turn. Completion wakes you; results arrive batched; read them with task_status.
```

- **No sidebar row.** The child is `relationshipToParent: "subagent"` and shows only in the parent's
  lineage. Its questions and approvals surface as **Input / Approval on the parent row**.
- **No ping-back footer and no settle.** The result is the child's final answer, after its background
  and nested work finishes. Brief the child to put the report in its last message.
- Child gets **only the task text** (no parent history), same checkout unless `isolation: "worktree"`.
  Any provider/account/model from `orchestrator_capabilities`; nesting works (child → grandchild).
- Questions: `t3_pending_request_list/read/respond` with `threadId = childThreadId`. Approvals: the
  parent cannot approve; the user clicks them. Leave `runtimeMode` unset.
- Follow-up with the same context: `t3_thread_send` to `childThreadId` → new `taskId`, wakes you.
  A new review round with fresh judgment → new `delegate_task` with the full history in the brief.
- Proven for normal completion only: recovery when the parent or child is limited, stopped or restarted
  is untested. Keep the task ids and check `task_status` if a wake seems overdue.
- `task_cancel` stops it (`interrupted` + partial summary). Stopping the parent stops its tasks (#16002, not tested here).
  Settling the parent does **not**: a later child completion wakes and unsettles it.
- Reading a terminal result (`task_status`, or a full read of the child) acknowledges it, and
  pending wakes for it are dropped. Don't poll; never `mode: "wait"` for long work.

## Other native replacements

| Old helper | Native tool | Note |
| --- | --- | --- |
| `t3-spawn-thread` 📤 | `t3_thread_launch` | visible top-level thread; `modelSelection.instanceId` from `t3-pick-instance` |
| `t3-ping-thread` | `t3_thread_send` | `mode: auto/queue/steer`; `clientRequestId` makes retries idempotent |
| `t3-read-thread` | `t3_thread_read` | `view: "activity"`, paginate with `afterPosition` |
| `t3-rename-thread` (deleted) | `t3_thread_update action:"rename"` | |
| `t3-settle-thread` (pointer, exit 3) | `t3_thread_organize action:"settle"` (no threadId = self) | self-settle applies when your turn ends |
| `t3-hide-thread` (deleted) | none: 🏓 = `delegate_task` (no row); Working section folds busy threads | native snooze clears on every new run, so it can't hide a live thread |
| `t3-schedule` | `schedule_task` | `fixed_time {timeOfDay, weekdays}`; no one-shot: the run deletes itself |

Shell scripts outside a thread (launchd jobs) have no native write path yet: `/mcp` refuses a plain
bearer session (`invalid_mcp_credential`, OAuth client needed).
