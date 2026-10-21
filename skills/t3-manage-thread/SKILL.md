---
name: t3-manage-thread
description: Delegate, launch, message, read or settle T3 Code threads (T3 >= 0.1). Use for round-trip workers and opposite-model reviews (delegate_task), standalone threads/hand-offs (t3_thread_launch), cross-thread messages, reading another thread, settling a finished thread or this one, picking the account with capacity (t3-pick-instance, t3-limits), scripts outside T3 starting or messaging threads (t3-relay), or a Gmail thread whose new mail wakes a T3 thread (t3-mail-link). Not for Claude Desktop or Codex cloud tasks.
---

# T3 Manage Thread

T3 MCP tools (Claude `mcp__t3-code__*`, Codex `t3_code.*`); scripts add only account routing and an outside-T3 entry.

| Need | Tool |
|---|---|
| 🏓 ping-pong inside this task (opinion, research, review; any provider) | `delegate_task`: no row, result wakes you ([which one](workers.md#which-one)) |
| 📤 independent topic, other repo, selected recording follow-up | `t3_thread_launch` ([workers.md](workers.md#-t3_thread_launch)) |
| Model + account with capacity | `t3-pick-instance MODEL` → `<instanceId> <modelId> <effort>` ([routing.md](routing.md)) |
| Message a thread | `t3_thread_send` (`mode` auto/queue/steer; `clientRequestId` for retries) |
| Read / find threads | `t3_thread_read` · `t3_thread_list` (`currentThreadId` = your own id) · `t3_thread_search` |
| Rename · switch model | `t3_thread_update {action:"rename"}` · `t3_thread_configure` |
| Settle yourself / another thread | `t3_thread_organize {action:"settle"}` ([settle-thread.md](settle-thread.md)) |
| Script outside T3 starts/messages a thread | `t3-relay launch\|send` ([relay.md](relay.md)) |
| Gmail case thread woken by new mail (drafting claims it) · which thread owns a Gmail URL | `t3-mail-link` · `t3-mail-link find` ([mail-link.md](mail-link.md)) |

- Nothing needs hiding: 🏓 children have no row; **Working section** (Settings → General) folds busy threads until done or needing input. No snoozing workers.
- Opposite-model review: [code-review.md](code-review.md) · tickets/findings as threads: [dispatch-workers.md](dispatch-workers.md) · rate limits: [limits.md](limits.md) · browser / computer use: [browser.md](browser.md).
- Fleet audit, purge, old threads: [t3-maintenance](../t3-maintenance/SKILL.md), [t3-find-thread](../t3-find-thread/SKILL.md) · scheduled threads: [t3-schedule](../t3-schedule/SKILL.md).

## Model tier

Standalone threads (`t3_thread_launch`, `t3-relay launch`, `t3-schedule`) orchestrate: Opus (Claude) or Astra (OpenAI) by default; explicit choices win (incl. Sol).
Always pass model, account and effort: native inheritance differs from the [helper defaults](routing.md#models). `t3-relay`/`t3-schedule` refuse haiku/luna unless `--allow-small-model` (a script already decides everything); small model in your own `t3_thread_launch` → warn the user, launch only if they insist.

## Personal config (optional)

Beside T3's `settings.json` in `${T3CODE_HOME:-~/.t3}/userdata/`:
- `t3-manage-thread.json` → `{"instructions": "/abs/path/notes.md"}`: agents read it before routing.
- Scripts read `t3-plan-multipliers.json` ([limits.md](limits.md)), `t3-routing-override.json` ([routing.md](routing.md#temporary-override)).

## Install

`scripts/install` links `t3-pick-instance`, `t3-relay`, `t3-limits`, `t3-list-profiles`, `t3-mail-link`, `skills-refresh` into `~/.local/bin` (drops stale links); `--check` verifies deps, logins, T3 and relay (`t3-relay check`). Colleagues: `skills-refresh schedule` ([skills-refresh.md](skills-refresh.md)). macOS, Linux, WSL2.
