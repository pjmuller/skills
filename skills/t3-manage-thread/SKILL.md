---
name: t3-manage-thread
description: "Use to delegate to, launch, message, read or settle T3 Code threads: round-trip workers and opposite-model reviews (\"have Sol review this\"), \"start a separate thread / hand this off\", \"settle this thread\", picking an account with capacity, a script starting threads (t3-relay), a Gmail thread whose new mail should wake a T3 thread, or finding a past thread (\"which thread did we…\", \"where did I ask about X\", a short thread id, reading or reviving an old or purged one; works from vague memory and dictated typos). Not Claude Desktop or Codex cloud tasks."
---

# T3 Manage Thread

North star: the lead keeps the human out of the loop. Fan work out (🏓 for answers you need back
this turn, 📤 for independent tasks the user follows in the sidebar), get an opposite-model review
before anything consequential, spread load across accounts. Every handoff drops context: brief
like a peer, verify what comes back.

T3 MCP tools (Claude `mcp__t3-code__*`, Codex `t3_code.*`); scripts add only account routing and an outside-T3 entry.

| Need | Tool |
|---|---|
| 🏓 ping-pong inside this task (opinion, research, review; any provider) | `delegate_task`: no row, result wakes you ([which one](workers.md#which-one)) |
| 📤 independent topic, other repo, selected recording follow-up | `t3_thread_launch` ([workers.md](workers.md#-t3_thread_launch)) |
| Model + account with capacity | `t3-pick-instance MODEL` → `<instanceId> <modelId> <effort>` ([routing.md](routing.md)) |
| Message a thread | `t3_thread_send` (`mode` auto/queue/steer; `clientRequestId` for retries); target in a broader permission mode (Auto → Full Access) → [permission-ceiling.md](permission-ceiling.md) |
| Read / find threads | `t3_thread_read` · `t3_thread_list` (`currentThreadId` = your own id) · `t3_thread_search`; vague memory, a short id or a purged thread → `t3-find-thread` · open/link one → `t3-open-thread` ([find-thread.md](find-thread.md)) · own context use → `t3-context` |
| Rename · switch model | `t3_thread_update {action:"rename"}` · `t3_thread_configure` (model/account only, never permission mode) |
| Settle yourself / another thread | `t3_thread_organize {action:"settle"}` ([settle-thread.md](settle-thread.md)) |
| Script outside T3 starts/messages a thread | `t3-relay launch\|send` ([relay.md](relay.md)) |
| Gmail case thread woken by new mail (drafting claims it) · which thread owns a Gmail URL | `t3-mail-link` · `t3-mail-link find` ([mail-link.md](mail-link.md)) |

- Nothing needs hiding: 🏓 children have no row; T3's **Working section** (Settings → General) folds busy threads until done or needing input. No snoozing workers.
- Opposite-model review: [code-review.md](code-review.md) · ticket/finding threads: [dispatch-workers.md](dispatch-workers.md) · rate limits: [limits.md](limits.md) · browser / computer use: [browser.md](browser.md) · replace a routing thread: [routing-reset.md](routing-reset.md).
- Fleet audit, purge: [t3-maintenance](../t3-maintenance/SKILL.md) · scheduled threads: [t3-schedule](../t3-schedule/SKILL.md).

## Model tier

Standalone threads (`t3_thread_launch`, `t3-relay launch`, `t3-schedule`) orchestrate: Opus or Astra unless the user picks (incl. Sol), never a small model unasked. Always pass model, account and effort explicitly ([routing.md](routing.md#models)).

## Personal config (optional)

Beside T3's `settings.json` in `${T3CODE_HOME:-~/.t3}/userdata/`:
- `t3-manage-thread.json` → `{"instructions": "/abs/path/notes.md"}`: agents read it before routing.
- Scripts read `t3-plan-multipliers.json` ([limits.md](limits.md)), `t3-routing-override.json` ([routing.md](routing.md#temporary-override)).

## Install

`scripts/install` links the helpers into `~/.local/bin`; `--check` verifies deps, logins, T3 and `t3-relay check`. Colleagues keep current with `skills-refresh schedule` ([skills-refresh.md](skills-refresh.md)). macOS, Linux, WSL2.
