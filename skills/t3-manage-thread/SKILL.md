---
name: t3-manage-thread
description: Spawn, ping, read, rename, or settle a separate T3 Code thread from an agent or terminal. Use when the user asks to spawn/delegate/hand off an independent task in T3 Code, to send a cross-thread message (ping-back) to another T3 thread, to read another thread's transcript/brief/progress, to run an opposite-model code review as a worker thread, or to settle/clear/acknowledge a finished thread so it leaves the "needs you" inbox. Do not use for Claude Desktop or Codex tasks.
---

# T3 Manage Thread

Helpers on PATH; use them before touching T3's raw API, cookies or SQLite.
Every flag: `--help`. Spawn uses the current git root, inherits model/thinking,
picks a Claude profile by capacity, runs full-access in the local checkout and
prints project + thread IDs — report those.

## Commands

```bash
# 🏓 round-trip worker (hidden while running, pings the parent back, parent settles it)
t3-spawn-thread --title "🏓 <task>" -- "Read and execute /abs/path/brief.md"
# other provider: --model picks the driver; account = inherited sibling (Claude side: by capacity, ties prefer the sibling)
t3-spawn-thread --model astra --thinking med --source-thread <parent-id> --title "🏓 …" -- "<brief>"   # from Claude → OpenAI
t3-spawn-thread --model fable --thinking med --source-thread <parent-id> --title "🏓 …" -- "<brief>"   # from Codex → Claude
# 📤 standalone (visible, never hidden/settled by helpers); add --settle-when-done for fire-and-forget
t3-spawn-thread --title "📤 <task>" -- "<brief>"

t3-ping-thread --thread <parent-id> --from "<label>" -- "<report>"   # arrives as a user turn, wakes the agent
t3-read-thread <id>                                                   # transcript/brief/progress (read before pinging)
t3-settle-thread --wait <id>                                          # settle = kill session + its sub-agents; terminal
t3-settle-thread --self                                               # "…then settle this thread": last tool call
t3-hide-thread <id> · t3-rename-thread <id> --title "…" · t3-limits · t3-delete-thread --yes <id>
```

Rules of thumb: brief = file on disk, path in the argument (no backticks or
`$(...)` inline: the shell expands them). `--thinking` only when a level is
named. `--profile` = account label (`probackup`, `dentai`), never a driver: add it
only to switch accounts or when routing says "Choose --profile". `--source-thread` when the parent is not auto-detected (Codex CLI
sessions have no T3 address). Default to 🏓 unless the user said standalone.
Hidden ≠ stopped; settle only after the ping-back is verified.

## Which doc

| Need | Read |
| --- | --- |
| Spawn: profiles, models, thinking, 🏓/📤/fire-and-forget, images in a brief, routing policy | [spawn-thread.md](spawn-thread.md) |
| Dispatch tickets/findings as worker threads: titles, thinker model, brief shapes, bookkeeping | [dispatch-workers.md](dispatch-workers.md) |
| Opposite-model code review as a 🏓 worker: when, brief, reviewer output, builder push-back | [code-review.md](code-review.md) |
| Ping an existing thread (ping-back, quoting trap, visibility) | [cross-thread-ping.md](cross-thread-ping.md) |
| Read a thread's transcript / brief / progress | [read-thread.md](read-thread.md) |
| Settle / unsettle / settle yourself (settle = kill) | [settle-thread.md](settle-thread.md) |
| Hide / unhide a live worker (snooze keeper) | [hide-thread.md](hide-thread.md) |
| Rename (hard-set title, `--prefix`, wait for auto-title) | [rename-thread.md](rename-thread.md) |
| Rate-limit windows per Claude profile + Codex | [limits.md](limits.md) |
| Bulk select + hard purge of threads | `t3-maintenance` skill → `t3-purge-threads` |
| Fleet view of workers (`t3-fleet list --title-prefix 🏓` / `--stalled`) | `t3-maintenance` skill |
| Native upstream tools (when to retire these helpers) | [upstream-checkpoint.md](upstream-checkpoint.md) |

## Install

```bash
scripts/install          # symlinks the helpers into ~/.local/bin
scripts/install --check  # deps + T3 Code reachable
```

Deps: `jq`, `curl`, `uuidgen`, `sqlite3`, `pnpm`, `uv`, `git`, T3 Code running.
macOS, Linux, WSL2. Debugging: `T3_SPAWN_DEBUG=1` traces the shell helpers.
