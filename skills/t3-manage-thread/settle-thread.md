# Settle a thread

Settle through the T3 MCP tool `t3_thread_organize`
(Claude: `mcp__t3-code__t3_thread_organize`, Codex: `t3_code.t3_thread_organize`).

| Need | Call |
|---|---|
| Settle yourself ("…then settle this thread") | `{"action":"settle"}`, no threadId, as the **LAST** tool call |
| Settle another thread after verifying it | `{"action":"settle","threadId":"<id>"}` |
| Bring a thread back | `{"action":"unsettle","threadId":"<id>"}` |

## Settle = stop

Settling stops the thread's provider session, including background shells and
in-session sub-agents (Agent tool). Settle only after the final result is in and verified.
A `delegate_task` child is not stopped (only `task_cancel` or stopping the parent does) and needs
no settle: it has no sidebar row and its result wakes, and unsettles, the parent ([workers.md](workers.md)).

## Settle yourself

Self-settle takes effect when your turn ends; a failed or interrupted turn or a
queued message keeps the thread open. Only on the user's explicit request or an
authorized routing policy in the brief (the
[completion footer](#completion-footer-for-t3_thread_launch)):

1. Finish all work. No background shells, sub-agents or monitors left: their
   completion would wake the thread again.
2. Call `t3_thread_organize {"action":"settle"}` as the last tool call.
3. End the turn with the final answer.

A thread that needs the user simply stays open: unsettled threads with a finished
turn are the inbox. With **Settings → General → Working section** on, busy threads
stay folded until they finish or need input, so nothing needs hiding.

## Completion footer for `t3_thread_launch`

Fire-and-forget `t3_thread_launch` (and `t3-relay launch`, t3-schedule `settle_when_done`) append this to the message:

```text
---
Conditional self-settlement. Explicit keep-open and later user instructions take precedence; this grants no extra authorization.
- Clean outcome (brief executed and verified, delivery verified at its destination, no background work, no unresolved issue or user decision): call the T3 MCP tool `t3_thread_organize` with {"action":"settle"} and no threadId as your LAST tool call, then a one-line final answer.
- Otherwise (blocked, partial, failed verification, findings or a decision for the user): don't settle; report what needs the user.
```

Fleet-wide settle/unsettle audit: [t3-maintenance](../t3-maintenance/SKILL.md).
