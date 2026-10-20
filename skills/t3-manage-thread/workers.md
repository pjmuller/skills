# Workers: 🏓 `delegate_task` · 📤 `t3_thread_launch`

Verified on T3 0.1.0 (2026-10-16; evidence: macbook_setup `decissions/t3_native_workers.md`).

## Which one

- **🏓 native child** (`delegate_task`): ping-pong inside **this thread's task**: second planning
  opinion, scoped research, sub-step, opposite-model code review. Any provider/model (cross-provider
  is native). Runs in this thread's project/checkout. Unclear sub-step → 🏓.
- **📤 standalone** (`t3_thread_launch`): independent topic the user follows on its own, work owned
  by another repo, the user said "separate / own thread / hand off", or a **selected** recording or
  meeting follow-up. Each standalone thread delegates its own 🏓 children. Test: would this
  thread's answer change when the result lands? No → 📤.
- A distinct outcome gets a new standalone even within the same topic/repo. For an independent
  opinion, give a fresh `delegate_task` the original problem, constraints and evidence, withholding
  the lead's reasoning. Never switch the lead's model for a second opinion; model replacement
  remains available for an explicit user switch or authorized recovery.
- One task + several models = one lead (this thread) with 🏓 children. Never standalone peers the
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
- **Every review round = a new `delegate_task`** (new `clientRequestId`, stable across retries of
  that round) whose task carries the original brief, prior findings, your responses and open
  objections. `childThreadId` is storage, not the target of a new round. `t3_thread_send` to it only
  for a short clarification that needs that child's own conversation (new `taskId`, result wakes you).
- `task_cancel` stops it. Stopping the parent stops its tasks. Settling the parent does not: a later
  child result wakes and unsettles it.
- Reading a terminal result acknowledges it. Don't poll, and use `mode: "wait"` only for seconds-long tasks.
- Unverified: recovery when parent or child is limited, stopped or restarted. Keep the task ids and
  check `task_status` if a wake seems overdue.

### Provider unavailable or failed

`orchestrator_capabilities` reports cached health; `t3-pick-instance` reports capacity.
Neither proves execution. A Codex **status-probe timeout** does not prove expired auth:
with an explicit `providerInstanceId`, `delegate_task` re-probes an unavailable instance
once before refusing (verified T3 0.1.0). Keep the selected account; let that recheck run.
If dispatch refuses for a transient timeout, retry once after 30 s with the same
`clientRequestId`. An accepted task is different: inspect its `taskId`, never blindly resend.

For a failed run, read the concrete provider error first: `ENOTFOUND` means DNS failed;
“model at capacity” is model availability, not subscription quota; only an authentication
error warrants investigating credentials. Recheck connectivity/status before reauth.
Resume a failed standalone owner only when authorized and still failed/inactive; preserve
its prompt and never duplicate a launch or restart active/completed work.

## 📤 `t3_thread_launch`

```text
t3_thread_launch {title: "📤 <3-6 words>", projectId, message: "Read and execute /abs/brief.md",
  modelSelection: {instanceId, model, options: [{id: "effort"|"reasoningEffort", value}]},
  workspaceStrategy: {type: "root"}}            # or worktree / existing_worktree
```

- Visible top-level thread. Fire-and-forget only with the user's go or a routing policy: append the
  [completion footer](settle-thread.md#completion-footer-for-t3_thread_launch).
- `projectId` = the repo that owns the work. Another project than yours → say so in the brief.
  Default workspace = project **root**, not your worktree.
- **No retry key**: after an error or lost response, check `t3_thread_list` before launching again.
- Report the id as a link: `[title](t3-thread://v1/<threadId>)`, the `threadId` verbatim as the tool returned it, prefix included (`t3-thread://v1/mcp:287f…`); never strip `mcp:` or URL-encode it.

## Briefs and titles

- Brief = a markdown file, path in the task/message ([dispatch-workers.md](dispatch-workers.md)).
  Images: copy to a stable path and name it in the brief.
- Title: `<emoji> <3-6 words>` in the user's language, no ticket ids.
- Model and account: [routing.md](routing.md). No explicit account/effort unless the user names one.
