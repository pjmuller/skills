# Workers: 🏓 `delegate_task` · 📤 `t3_thread_launch`

Verified T3 0.1.0 (2026-10).

## Which one

- **🏓 child** (`delegate_task`): ping-pong inside **this task** (opinion, scoped research, sub-step, opposite-model review); any provider, this checkout. Unclear → 🏓.
- **📤 standalone** (`t3_thread_launch`): independent topic, another repo's work, user said "separate / own thread / hand off", or a **selected** recording/meeting follow-up; runs its own 🏓 children. Test: result lands, does this thread's answer change? No → 📤. Distinct outcome → own standalone, even same repo.
- Independent opinion: fresh `delegate_task` with original problem, constraints, evidence, minus the lead's reasoning; don't switch the lead's model for it (only user request or authorized recovery). Several models on one task = one lead + 🏓 children, never peers the user must combine.

## 🏓 `delegate_task`

```text
read instance model effort <<< "$(t3-pick-instance sol)"     # e.g. codex_work gpt-6.1-sol high
delegate_task {task: "Read and execute /abs/brief.md", title: "<3-6 words>", mode: "async",
  role: "review", clientRequestId: "<stable per round>",
  target: {providerInstanceId: instance, model: model, options: {reasoningEffort|effort: effort}}}
→ end your turn. The completion wakes you (batched); read it with task_status.
```

- **No sidebar row** (`relationshipToParent: "subagent"`); questions/approvals show as **Input / Approval on the parent row**. Answer questions via `t3_pending_request_*` (`threadId` = `childThreadId`); only the user approves (leave `runtimeMode` unset).
- Result = its **final answer** (after background/nested work): brief it to report there; no footer, no settle. It gets **only the task text**, shares your checkout (`isolation: "worktree"` for its own); nesting works.
- **Every review round = a new `delegate_task`** (new `clientRequestId`, stable across that round's retries) carrying original brief, prior findings, your responses, open objections. `childThreadId` is storage: `t3_thread_send` to it only for a short clarification needing its conversation (new `taskId`, wakes you).
- `task_cancel` or stopping the parent stops it; settling doesn't ([settle-thread.md](settle-thread.md#settle--stop)).
- Reading a terminal result acknowledges it. Don't poll; `mode: "wait"` only for seconds-long tasks. Recovery after parent/child limit/stop/restart is unverified: keep task ids, `task_status` if a wake is overdue.

### Codex sandbox limits

Codex `delegate_task` children in `auto` mode have no outbound network and no Docker (AWS CLIs fail,
testcontainer tests hang). Brief them: inputs pre-fetched to a local path, only tests needing neither,
report "not run: needs network/Docker" instead of waiting. The lead runs the rest.
Its sandbox also keeps `.git/` and `~/.cache/uv` read-only: a `uv run --script` helper that fails on the cache
reruns as the same command with escalation (auto-reviewed), never with a `/tmp` `UV_CACHE_DIR` (each detour
re-downloads into a cache nothing shares).

### Provider unavailable or failed

- `orchestrator_capabilities` (cached health) and `t3-pick-instance` (capacity) don't prove execution. Codex **status-probe timeout** ≠ expired auth: with explicit `providerInstanceId`, `delegate_task` re-probes once before refusing, so keep the account. Transient-timeout refusal → one retry after 30 s, same `clientRequestId`; accepted → inspect its `taskId`, never resend blindly.
- Failed run → read the provider error: `ENOTFOUND` = DNS; "model at capacity" = model availability, not quota; only an auth error (after rechecking connectivity/status) warrants checking credentials.
- Resume a failed standalone owner only if authorized and still failed/inactive; keep its prompt; never duplicate a launch or restart active/completed work.
- Replacing a live owner (user-requested model switch or authorized recovery): read it, ask it to stop safely, start the replacement only after observing its turn end (a stop ping proves only "asked"); carry its partial artifacts over.

### Recover a limit-interrupted owner

1. Find them: `t3-fleet list --limited` ([fleet.md](../t3-maintenance/fleet.md), incl. children and completed runs).
2. Read owner and parent (a replacement may own the rest; never replay superseded children). Check live capacity in the authorized pool; keep thread ID, model/options, permissions ([broader-mode owner](permission-ceiling.md)).
3. `t3_queue list`: a queued child-result delivery may keep the old account → save its text, `t3_queue cancel` only that unstarted delivery, include it once in the continuation; never discard user messages/attachments.
4. Re-read right before mutating. Inactive owner → `t3_thread_configure` (new instance, original selection), one idempotent `t3_thread_send` to resume (T3 transfers context; same-provider switches may get a summary). Verify real execution and kept context, not configure acceptance.

## 📤 `t3_thread_launch`

```text
t3_thread_launch {title: "📤 <3-6 words>", projectId, message: "Read and execute /abs/brief.md",
  modelSelection: {instanceId, model, options: [{id: "effort"|"reasoningEffort", value}]},
  workspaceStrategy: {type: "root"}}            # or worktree / existing_worktree
```

- Visible thread. Fire-and-forget only on the user's go or a routing policy: append the [completion footer](settle-thread.md#completion-footer-for-t3_thread_launch).
- Pass `runtimeMode` deliberately (user's choice, else the operator's default): omitted, it inherits the caller's mode (possibly `full-access`), not the app's new-thread default. It can't exceed the caller's ([ceiling](permission-ceiling.md)); never broaden it to get past an approval failure.
- `projectId` = repo owning the work (not yours → say so in the brief). Default workspace: project **root**, not your worktree.
- **Retry key** (T3 ≥ 0.1.4, [#16654](https://github.com/pingdotgg/t3code/pull/16654)): pass `clientRequestId`; after an error or lost response, retry with the same key: it returns the same thread instead of a second one. Older T3: check `t3_thread_list` before relaunching.
- Report the tool's `link` verbatim (T3 ≥ 0.1.4: `<t3-thread://v2/<environmentId>/<threadId>>`, shows the current title, [#26239](https://github.com/pingdotgg/t3code/pull/26239)). Hand-built `[title](t3-thread://v1/<threadId>)` still opens: `threadId` verbatim incl. prefix (`mcp:287f…`), never strip `mcp:` or URL-encode.

## Briefs and titles

- Brief = markdown file on disk, path in the task/message (`Read and execute /abs/brief.md`), never a long inline string; images at a stable path named in it. Ticket/finding/meeting threads: [brief shapes](dispatch-workers.md#brief).
- Title `<emoji> <3-6 words the user recognises>`, user's language (an operator's convention wins): `📤` standalone, `🏓` children only. No ticket ids (they go in the brief), repo names, phase words or invented emojis (🎫, 🔧: they confuse the fleet views). Good `📤 Annulatiepolicy toepassen`; bad `🎫 869f4kx78 annulatiepolicy: numeric fields, conditional profile, playbook, dashboard tile`.
- Sustained build (hours of tool-heavy work)? Put `routing-load: heavy` as its own line in the `task`/`message` text itself (not only the brief file, not quoted or fenced): routing counts that owner as 3 instead of 1. Default 1; never infer it from project or title.
- Model and account per spawn: [routing.md](routing.md).
