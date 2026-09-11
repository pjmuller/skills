---
name: t3-manage-thread
description: Spawn, ping, read, rename, or settle a separate T3 Code thread from an agent or terminal. Use when the user asks to spawn/delegate/hand off an independent task in T3 Code, to send a cross-thread message (ping-back) to another T3 thread, to read another thread's transcript/brief/progress, or to settle/clear/acknowledge a finished thread so it leaves the "needs you" inbox. Do not use for Claude Desktop or Codex tasks.
---

# T3 Manage Thread

```bash
t3-spawn-thread --title "Short title" -- "<task brief>"
```

Use the helpers before touching T3's raw API, cookies or SQLite. Spawn uses the
current git root, inherits model/thinking, selects a Claude profile by capacity
([routing policy](spawn-thread.md#automatic-profile-routing)), runs full-access
in the local checkout, and prints the project + thread IDs — report those.

## 🏓 round-trip workers

| Step | Command / effect |
| --- | --- |
| spawn | `t3-spawn-thread --title "🏓 <task>" -- "<brief>"` — ping-back footer appended to the brief; thread **hidden** (snoozed, still running) |
| worker reports | `t3-ping-thread --thread <parent> --from <label> -- "<report>"` (the footer) |
| orchestrator verifies, then ends it | `t3-settle-thread --wait <id>` — **settle = kill** (stops the session and its sub-agents). Terminal, never automatic. |

Hidden ≠ stopped: hiding is a snooze that a keeper maintains, and a hidden
worker must resurface the moment it dies or needs the user
([hide-thread.md](hide-thread.md)); settling kills it
([settle-thread.md](settle-thread.md)). Threads without 🏓 (standalone, 📤
hand-offs, orchestrators) are never hidden or settled by the helpers — except
fire-and-forget spawns (`--settle-when-done`: hidden while running, the worker
settles itself at the end; [spawn-thread.md](spawn-thread.md#fire-and-forget---settle-when-done)). Fleet
view: `t3-fleet list --recent 12h --title-prefix 🏓` / `--stalled` (skill
`t3-maintenance`).

## Which doc

| Need | Read |
| --- | --- |
| Create a thread: profiles, models, thinking, titles, long briefs | [spawn-thread.md](spawn-thread.md) |
| Message an existing thread (ping-back, quoting pitfall) | [cross-thread-ping.md](cross-thread-ping.md) |
| Read a thread's transcript / brief / progress | [read-thread.md](read-thread.md) |
| Settle / unsettle a finished thread (settle = kill) | [settle-thread.md](settle-thread.md) |
| Settle **yourself** ("…then settle this thread"): `t3-settle-thread --self` as the last tool call, no background work alive | [settle-thread.md](settle-thread.md#settle-yourself-then-settle-this-thread) |
| Hide / unhide a live worker (snooze keeper) | [hide-thread.md](hide-thread.md) |
| Rename a thread (hard-set title, `--prefix`, wait for auto-title) | [rename-thread.md](rename-thread.md) |
| Rate-limit windows per Claude profile + Codex (before spawning / when threads hit limits) | [limits.md](limits.md) |
| Delete a thread (`t3-delete-thread --yes ID`) — soft: rows stay in SQLite; bulk select + hard purge of rows/transcripts | `t3-maintenance` skill → `t3-purge-threads` |
| Native upstream tools (when to retire these helpers) | [upstream-checkpoint.md](upstream-checkpoint.md) |

## Install

```bash
scripts/install          # symlinks the eight helpers into ~/.local/bin
scripts/install --check  # deps + T3 Code reachable
```

Deps: `jq`, `curl`, `uuidgen`, `sqlite3`, `pnpm`, `uv`, `git`, T3 Code running.
`scripts/lib/t3-common.sh` pins a global `t3` CLI to the server version and
mints/revokes its own short-lived bearer session (`desktop-managed-local` auth
is fine). macOS, Linux, WSL2; detached workers use launchd / `systemd-run --user`.

Every flag is in `--help`. Debugging: `T3_SPAWN_DEBUG=1` traces the shell
helpers (not the read-only `t3-read-thread`); failures print the CLI stderr.
