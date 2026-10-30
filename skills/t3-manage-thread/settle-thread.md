# Settle a thread

MCP tool `t3_thread_organize` (Claude `mcp__t3-code__…`, Codex `t3_code.…`); fleet-wide audit: [t3-maintenance](../t3-maintenance/SKILL.md).

| Need | Call |
|---|---|
| Settle yourself ("…then settle this thread") | `{"action":"settle"}`, no threadId, as the **LAST** tool call |
| Settle another thread after verifying it | `{"action":"settle","threadId":"<id>"}` |
| Unsettle (bring back) | `{"action":"unsettle","threadId":"<id>"}` |

## Settle = stop

Stops the provider session, incl. background shells and in-session sub-agents (Agent tool): only after the final result is verified. A `delegate_task` child isn't stopped (`task_cancel` or stopping the parent is), needs no settle, and its result wakes and unsettles the parent ([workers.md](workers.md)).

## Settle yourself

Only on the user's explicit request or an authorized routing policy in the brief ([completion footer](#completion-footer-for-t3_thread_launch)). Applies when the turn ends; a failed/interrupted turn or queued message keeps it open.

Finish all work (no background shells, sub-agents or monitors left: they'd wake it), settle as the last tool call, then the final answer.

Needs the user → stay open: unsettled finished threads are the inbox.

## Completion footer for `t3_thread_launch`

Fire-and-forget launches (`t3_thread_launch`, `t3-relay launch`, t3-schedule `settle_when_done`) append to the message:

```text
---
Conditional self-settlement. Explicit keep-open and later user instructions take precedence; this grants no extra authorization.
- Clean outcome (the user's whole outcome done and verified, not just the slice the brief named; nothing left for the user to do or approve; no background work, no unresolved issue): call the T3 MCP tool `t3_thread_organize` with {"action":"settle"} and no threadId as your LAST tool call, then a one-line final answer.
- Otherwise (blocked, partial, failed verification, findings or a decision for the user): don't settle; report what needs the user.
```
