---
name: t3-manage-thread
description: Delegate, launch, message, read or settle T3 Code threads (T3 >= 0.1). Use for round-trip workers and opposite-model reviews (delegate_task), standalone threads/hand-offs (t3_thread_launch), cross-thread messages, reading another thread, settling a finished thread or this one, picking the account with capacity (t3-pick-instance, t3-limits), letting scripts outside T3 start or message threads (t3-relay), or linking a Gmail thread so new mail wakes a T3 thread (t3-mail-link). Not for Claude Desktop or Codex cloud tasks.
---

# T3 Manage Thread

Agents use T3's MCP tools (Claude `mcp__t3-code__*`, Codex `t3_code.*`). The scripts here only add
account routing and an outside-T3 entry point.

| Need | Tool |
|---|---|
| 🏓 ping-pong inside this task (planning opinion, research, review; any provider) | `delegate_task`: no sidebar row, the result wakes you ([which one](workers.md#which-one)) |
| 📤 independent topic, other repo, selected recording follow-up | `t3_thread_launch` ([workers.md](workers.md#-t3_thread_launch)) |
| Model + account with capacity | `t3-pick-instance MODEL` → `<instanceId> <modelId> <effort>` ([routing.md](routing.md)) |
| Message a thread | `t3_thread_send` (`mode` auto/queue/steer; `clientRequestId` for retries) |
| Read / find threads | `t3_thread_read` · `t3_thread_list` (`currentThreadId` = your own id) · `t3_thread_search` |
| Rename · switch model on a thread | `t3_thread_update {action:"rename"}` · `t3_thread_configure` |
| Settle yourself / another thread | `t3_thread_organize {action:"settle"}` ([settle-thread.md](settle-thread.md)) |
| A script outside T3 starts/messages a thread | `t3-relay launch\|send` ([relay.md](relay.md)) |
| Gmail case thread woken by new mail | `t3-mail-link` ([mail-link.md](mail-link.md)) |
| Which T3 thread already works on this Gmail URL | `t3-mail-link find` ([mail-link.md](mail-link.md)) |

- Nothing needs hiding. 🏓 children have no row, and T3's **Working section** (Settings → General) folds busy
  threads until they finish or need you. Snooze is for the user, not for workers.
- Opposite-model review: [code-review.md](code-review.md). Dispatching tickets/findings as threads:
  [dispatch-workers.md](dispatch-workers.md). Rate limits: [limits.md](limits.md).
- Fleet audit, purge, find old threads: [t3-maintenance](../t3-maintenance/SKILL.md),
  [t3-find-thread](../t3-find-thread/SKILL.md). Scheduled threads: [t3-schedule](../t3-schedule/SKILL.md).
  Browser / computer use: [browser.md](browser.md).

## Model tier

A standalone thread (`t3_thread_launch`, `t3-relay launch`, a `t3-schedule` launch) orchestrates:
run it on a frontier model (Opus/Fable/Sol/Astra) that hands chores to Haiku/Luna sub-agents or
`delegate_task` workers. Always pass `modelSelection`: without it the new thread inherits the
caller's model. `t3-relay` and `t3-schedule` refuse haiku/luna unless `--allow-small-model`
(orchestration already done, e.g. a script decides everything); before passing a small model to
`t3_thread_launch` yourself, warn the user and launch it only if they insist.

## Personal config (optional)

Beside T3's `settings.json` in `${T3CODE_HOME:-~/.t3}/userdata/`:
- `t3-manage-thread.json` → `{"instructions": "/abs/path/notes.md"}`: agents read it before routing.
- `t3-plan-multipliers.json` ([limits.md](limits.md)), `t3-routing-override.json`
  ([routing.md](routing.md#temporary-override)): read by the scripts.

## Install

`scripts/install` links `t3-pick-instance`, `t3-relay`, `t3-limits`, `t3-list-profiles`,
`t3-mail-link` and `skills-refresh` into `~/.local/bin`. It also drops links to helpers that no longer
exist. `scripts/install --check` verifies deps, logins, T3 and the relay task. Colleagues:
`skills-refresh schedule` ([skills-refresh.md](skills-refresh.md)). macOS, Linux, WSL2.
