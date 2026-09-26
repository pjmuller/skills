---
name: t3-manage-thread
description: Spawn, ping, read, hide, rename, or settle a separate T3 Code thread from an agent or terminal. Use when the user asks to spawn/delegate/hand off an independent task in T3 Code, to send a cross-thread message (ping-back) to another T3 thread, to read another thread's transcript/brief/progress, to run an opposite-model code review as a worker thread, to check Claude/Codex rate-limit windows before routing work, or to settle/clear/acknowledge a finished thread so it leaves the "needs you" inbox. Do not use for Claude Desktop or Codex tasks.
---

# T3 Manage Thread

Helpers in `scripts/`, on PATH after install; use them instead of T3's raw API,
cookies or SQLite. Every flag: `<helper> --help`. Spawn prints project + thread
IDs — report those.

```bash
t3-spawn-thread --title "🏓 <task>" -- "Read and execute /abs/path/brief.md"          # round-trip worker (default)
t3-spawn-thread --model astra --source-thread <parent-id> --title "🏓 …" -- "<brief>" # other ecosystem (fable from Codex)
t3-spawn-thread --title "📤 <task>" [--settle-when-done] -- "<brief>"                 # standalone / fire-and-forget
t3-ping-thread --thread <id> --from "<label>" -- "<report>"   # arrives as a user turn, wakes the agent
t3-read-thread <id> --outline                                 # read before pinging
t3-settle-thread --wait <id>                                  # settle = kill session + its sub-agents
t3-settle-thread --self                                       # "…then settle this thread": LAST tool call
t3-hide-thread <id> · t3-rename-thread <id> -- "…" · t3-limits · t3-list-profiles · t3-delete-thread --yes <id>
```

- 🏓 unless the user said standalone; hidden ≠ stopped; settle a 🏓 worker only
  after its ping-back is verified ([spawn-thread.md](spawn-thread.md)).
- No `--profile` / `--thinking` unless the user names an account or level:
  [routing policy](spawn-thread.md#automatic-profile-routing).
- Brief = file on disk, path in the argument ([quoting trap](cross-thread-ping.md)).
- `--source-thread` when the parent is not auto-detected (a Codex CLI session
  outside T3 has no T3 address).

| Need | Read |
| --- | --- |
| Spawn: 🏓/📤/fire-and-forget, titles, models, thinking, images, account routing | [spawn-thread.md](spawn-thread.md) |
| Dispatch tickets/findings as worker threads: titles, thinker model, brief shapes | [dispatch-workers.md](dispatch-workers.md) |
| Opposite-model code review as a 🏓 worker | [code-review.md](code-review.md) |
| Ping an existing thread | [cross-thread-ping.md](cross-thread-ping.md) |
| Read a transcript / brief / progress | [read-thread.md](read-thread.md) |
| Settle / unsettle / settle yourself (settle = kill) | [settle-thread.md](settle-thread.md) |
| Hide / unhide a live worker (snooze keeper) | [hide-thread.md](hide-thread.md) |
| Rename an existing thread | [rename-thread.md](rename-thread.md) |
| Rate-limit windows per Claude + Codex profile (the numbers routing uses) | [limits.md](limits.md) |
| Fleet view of workers, bulk repair, hard purge | [t3-maintenance](../t3-maintenance/SKILL.md) |
| Stay on the newest release (`skills-refresh`) | [skills-refresh.md](skills-refresh.md) |
| Native upstream tools (when to retire these helpers) | [upstream-checkpoint.md](upstream-checkpoint.md) |

## Install

`scripts/install` symlinks the helpers into `~/.local/bin`; `scripts/install --check`
verifies deps, links and that T3 Code is reachable. Colleagues: `skills-refresh schedule`.
Debug the shell helpers with `T3_SPAWN_DEBUG=1`. macOS, Linux, WSL2.
