# Settle a thread

T3 ≥ 0.1.0 settles natively through the T3 MCP tool `t3_thread_organize`
(Claude: `mcp__t3-code__t3_thread_organize`, Codex: `t3_code.t3_thread_organize`).
`t3-settle-thread` is retired: it only prints this call and exits 3.

| Need | Call |
|---|---|
| Settle yourself ("…then settle this thread") | `{"action":"settle"}`, no threadId, as the **LAST** tool call |
| Settle another thread after verifying it | `{"action":"settle","threadId":"<id>"}` |
| Bring a thread back | `{"action":"unsettle","threadId":"<id>"}` |

## Settle = stop

Settling stops the thread's provider session, including background shells and
sub-agents inside it. Settle only after the final result is in and verified.
A `delegate_task` child needs no settle: it has no sidebar row and its result
wakes the parent ([native-workers.md](native-workers.md)).

## Settle yourself

Self-settle takes effect when your turn ends; a failed or interrupted turn or a
queued message keeps the thread open. Only on the user's explicit request or an
authorized routing policy in the brief (the
[completion footer](spawn-thread.md#fire-and-forget---settle-when-done)):

1. Finish all work. No background shells, sub-agents or monitors left: their
   completion would wake the thread again.
2. Call `t3_thread_organize {"action":"settle"}` as the last tool call.
3. End the turn with the final answer.

A thread that needs the user simply stays open: unsettled threads with a finished
turn are the inbox. With **Settings → General → Working section** on, busy threads
stay folded until they finish or need input, so nothing needs hiding.

## Completion footer for `t3_thread_launch`

`--settle-when-done` appends this mechanically; a native launch pastes it at the end of `message`:

```text
---
Conditional self-settlement. Explicit keep-open and later user instructions take precedence; this grants no extra authorization.
- Clean outcome (brief executed and verified, delivery verified at its destination, no background work, no unresolved issue or user decision): call the T3 MCP tool `t3_thread_organize` with {"action":"settle"} and no threadId as your LAST tool call, then a one-line final answer.
- Otherwise (blocked, partial, failed verification, findings or a decision for the user): don't settle; report what needs the user.
```

Fleet-wide settle/unsettle audit: [t3-maintenance](../t3-maintenance/SKILL.md).
