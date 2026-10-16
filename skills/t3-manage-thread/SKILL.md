---
name: t3-manage-thread
description: Spawn, ping, read, rename, or settle a separate T3 Code thread from an agent or terminal. Use when the user asks to spawn/delegate/hand off an independent task in T3 Code, to send a cross-thread message to another T3 thread, to read another thread's transcript/brief/progress, to run an opposite-model code review as a worker, to check Claude/Codex rate-limit windows before routing work, to settle a finished thread (or this one) so it leaves the "needs you" inbox, or to link a Gmail thread to a T3 thread so new mail wakes it (t3-mail-link). Do not use for Claude Desktop or Codex tasks.
---

# T3 Manage Thread

T3 ≥ 0.1.0 (Orchestrator V2) does this natively through its T3 MCP tools (Claude
`mcp__t3-code__*`, Codex `t3_code.*`). Recipe and evidence: [native-workers.md](native-workers.md).

| Need | Native tool |
|---|---|
| 🏓 worker (result feeds this thread; other ecosystem) | `delegate_task`, account from `t3-pick-instance MODEL`. No sidebar row; its result wakes you; nothing to settle |
| 📤 standalone thread | `t3_thread_launch` (fire-and-forget: append the [completion footer](settle-thread.md#completion-footer-for-t3_thread_launch)) |
| Message a thread / follow up a finished child | `t3_thread_send` |
| Read / list / search threads | `t3_thread_read` · `t3_thread_list` · `t3_thread_search` |
| Rename | `t3_thread_update {action:"rename"}` |
| Settle yourself / another thread | `t3_thread_organize {action:"settle"}` ([settle-thread.md](settle-thread.md)) |

No hiding: busy threads fold into T3's **Working section** (Settings → General) until they finish
or need input; snooze is not a worker mechanism (it clears on every new run).

- 🏓 only when the result feeds back into this thread's deliverable; a "separate process/job" or a
  new orthogonal scope → 📤 ([return path](spawn-thread.md#-round-trip-workers)).
- One topic + multiple models = one standalone lead that delegates to 🏓 workers and owns
  synthesis/verification. Never split model roles into standalone peers for the user to combine.
- No explicit account or effort unless the user names one; several named accounts → route among
  them by capacity ([routing policy](spawn-thread.md#automatic-profile-routing)).
- Brief = file on disk, path in the argument ([quoting trap](cross-thread-ping.md)).

## Shell helpers

Still useful: `t3-pick-instance`, `t3-limits`, `t3-list-profiles`, `t3-read-thread` (frozen V1
store on 0.1). The writing helpers (`t3-spawn-thread`, `t3-ping-thread`, `t3-delete-thread`,
`t3-mail-link`) exit 3 on T3 ≥ 0.1 until a V2 transport exists; on 0.0.x:

```bash
t3-spawn-thread --title "🏓 <task>" -- "Read and execute /abs/path/brief.md"          # round-trip worker
t3-spawn-thread --title "📤 <task>" [--settle-when-done] -- "<brief>"                 # standalone / fire-and-forget
t3-ping-thread --thread <id> --from "<label>" -- "<report>"   # arrives as a user turn, wakes the agent
t3-read-thread <id> --outline · t3-limits · t3-list-profiles · t3-delete-thread --yes <id> · t3-mail-link
```

`t3-settle-thread` only prints the native call (exit 3). `--source-thread` when the parent is not
auto-detected (a Codex CLI session outside T3 has no T3 address).

## Personal config (optional, per user)

Beside T3's `settings.json` in `${T3CODE_HOME:-~/.t3}/userdata/`; absent = defaults. Keep the
sources in your private setup repo.
- `t3-manage-thread.json` → `{"instructions": "/abs/path/to/your-t3-notes.md"}`: when present,
  read that file before routing/spawning work (accounts, plan notes, runbooks). Agents only; the
  scripts never read it.
- `t3-plan-multipliers.json` (tiers, [limits.md](limits.md)) and `t3-routing-override.json`
  (temporary preference, [spawn-thread.md](spawn-thread.md#temporary-override)): read by the scripts.

| Need | Read |
| --- | --- |
| Spawn: 🏓/📤/fire-and-forget, titles, models, thinking, images, account routing | [spawn-thread.md](spawn-thread.md) |
| Dispatch tickets/findings as worker threads: titles, thinker model, brief shapes | [dispatch-workers.md](dispatch-workers.md) |
| Opposite-model code review as a 🏓 worker | [code-review.md](code-review.md) |
| Ping an existing thread; reuse it on another model/effort (same account) | [cross-thread-ping.md](cross-thread-ping.md) |
| Read a transcript / brief / progress | [read-thread.md](read-thread.md) |
| Settle / unsettle / settle yourself (settle = kill) | [settle-thread.md](settle-thread.md) |
| Link a Gmail thread so new inbound mail pings the T3 thread (mail cases) | [mail-link.md](mail-link.md) |
| Rate-limit windows per Claude + Codex profile (the numbers routing uses) | [limits.md](limits.md) |
| Fleet view of workers, bulk repair, hard purge | [t3-maintenance](../t3-maintenance/SKILL.md) |
| Stay on the newest release (`skills-refresh`) | [skills-refresh.md](skills-refresh.md) |
| Native workers (`delegate_task`), tool map, evidence | [native-workers.md](native-workers.md) |
| Native upstream tools (when to retire these helpers) | [upstream-checkpoint.md](upstream-checkpoint.md) |
| Browser / computer use: T3 preview, logged-in Chrome over CDP, native apps | [browser.md](browser.md) |

## Install

`scripts/install` symlinks the helpers into `~/.local/bin`; `scripts/install --check`
verifies deps, links, local login credentials and T3 connectivity. Colleagues: `skills-refresh schedule`.
Debug the shell helpers with `T3_SPAWN_DEBUG=1`. macOS, Linux, WSL2.
