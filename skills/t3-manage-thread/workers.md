# Workers: 🏓 `delegate_task` · 📤 `t3_thread_launch`

Verified on T3 0.1.0 (2026-10-16; evidence: macbook_setup `decissions/t3_native_workers.md`).

## Which one

- **🏓 round-trip**: the result feeds **this thread's deliverable** (review, sub-step, second opinion,
  other ecosystem). Unclear sub-step → 🏓.
- **📤 standalone**: the user said "separate / own thread / hand off", or it's a new orthogonal scope
  the user follows on its own. Test: would this thread's answer change when the result lands? No → 📤.
- One topic + several models = one lead (this thread) with 🏓 workers. Never standalone peers the
  user must combine.

## 🏓 `delegate_task`

```text
read instance model effort <<< "$(t3-pick-instance sol)"     # e.g. codex_dentai gpt-6.1-sol high
delegate_task {task: "Read and execute /abs/brief.md", title: "<3-6 words>", mode: "async",
  role: "review", clientRequestId: "<stable per round>",
  target: {providerInstanceId: instance, model: model, options: {reasoningEffort|effort: effort}}}
→ end your turn. The completion wakes you (batched); read it with task_status.
```

- **No sidebar row** (`relationshipToParent: "subagent"`, visible in the parent's lineage). Questions
  and approvals show as **Input / Approval on the parent row**. Answer questions with
  `t3_pending_request_*` (`threadId` = `childThreadId`). Only the user can approve, so leave `runtimeMode` unset.
- The result is the child's **final answer**, after its background and nested work. Brief it to put
  the report there. No footer, no settle.
- The child gets **only the task text** and shares your checkout (`isolation: "worktree"` for its own).
  Nesting works.
- Same-context follow-up: `t3_thread_send` to `childThreadId` (new `taskId`). A new review round =
  a new `delegate_task` whose brief carries prior findings and replies.
- `task_cancel` stops it. Stopping the parent stops its tasks. Settling the parent does not: a later
  child result wakes and unsettles it.
- Reading a terminal result acknowledges it. Don't poll, and use `mode: "wait"` only for seconds-long tasks.
- Unverified: recovery when parent or child is limited, stopped or restarted. Keep the task ids and
  check `task_status` if a wake seems overdue.

## 📤 `t3_thread_launch`

```text
t3_thread_launch {title: "📤 <3-6 words>", projectId, message: "Read and execute /abs/brief.md",
  modelSelection: {instanceId, model, options: [{id: "effort"|"reasoningEffort", value}]},
  workspaceStrategy: {type: "root"}}            # or worktree / existing_worktree
```

- Visible top-level thread. Fire-and-forget only with the user's go or a routing policy: append the
  [completion footer](settle-thread.md#completion-footer).
- `projectId` = the repo that owns the work. Another project than yours → say so in the brief.
  Default workspace = project **root**, not your worktree.
- **No retry key**: after an error or lost response, check `t3_thread_list` before launching again.
- Report the id as a link: `[title](t3-thread://v1/<threadId>)`.

## Briefs and titles

- Brief = a markdown file, path in the task/message ([dispatch-workers.md](dispatch-workers.md)).
  Images: copy to a stable path and name it in the brief.
- Title: `<emoji> <3-6 words>` in the user's language, no ticket ids.
- Model and account: [routing.md](routing.md). No explicit account/effort unless the user names one.
