---
name: t3-manage-thread
description: Spawn, ping, read, rename, or settle a separate T3 Code thread from an agent or terminal. Use when the user asks to spawn/delegate/hand off an independent task in T3 Code, to send a cross-thread message (ping-back) to another T3 thread, to read another thread's transcript/brief/progress, to run an opposite-model code review as a worker thread, or to settle/clear/acknowledge a finished thread so it leaves the "needs you" inbox. Do not use for Claude Desktop or Codex tasks.
---

# T3 Manage Thread

Helpers on PATH; use them before touching T3's raw API, cookies or SQLite.
Every flag: `--help`. Spawn uses the current git root, inherits model/thinking,
picks the account by capacity (Claude and Codex), runs full-access in the local checkout and
prints project + thread IDs — report those.

## Commands

```bash
# 🏓 round-trip worker (hidden while running, pings the parent back, parent settles it)
t3-spawn-thread --title "🏓 <task>" -- "Read and execute /abs/path/brief.md"
# other ecosystem: --model is enough (account by capacity, ties keep the parent's account; effort follows the parent)
t3-spawn-thread --model astra --source-thread <parent-id> --title "🏓 …" -- "<brief>"   # from Claude → OpenAI
t3-spawn-thread --model fable --source-thread <parent-id> --title "🏓 …" -- "<brief>"   # from Codex → Claude
t3-list-profiles   # only when the user names an account: exact --profile values per ecosystem
# 📤 standalone (visible, never hidden/settled by helpers); --settle-when-done = fire-and-forget: self-settles on a clean outcome, surfaces if the user is needed
t3-spawn-thread --title "📤 <task>" -- "<brief>"

t3-ping-thread --thread <parent-id> --from "<label>" -- "<report>"   # arrives as a user turn, wakes the agent
t3-read-thread <id>                                                   # transcript/brief/progress (read before pinging)
t3-settle-thread --wait <id>                                          # settle = kill session + its sub-agents; terminal
t3-settle-thread --self                                               # "…then settle this thread": last tool call
t3-hide-thread <id> · t3-rename-thread <id> --title "…" · t3-limits · t3-delete-thread --yes <id>
```

Rules of thumb: brief = file on disk, path in the argument (no backticks or
`$(...)` inline: the shell expands them). Usually no `--profile` and no
`--thinking`: the helper routes the account by capacity within the model's
ecosystem (ties keep the parent's account or its sibling) and each model's house effort. Pass
them only when the user names an account or a level; `t3-list-profiles` gives
the exact `--profile` value. `--source-thread` when the parent is not
auto-detected (Codex CLI sessions have no T3 address). Default to 🏓 unless the
user said standalone. Hidden ≠ stopped; settle only after the ping-back is verified.

## Which doc

| Need | Read |
| --- | --- |
| Spawn: profiles (`t3-list-profiles`), models, thinking, 🏓/📤/fire-and-forget, images in a brief, routing policy | [spawn-thread.md](spawn-thread.md) |
| Dispatch tickets/findings as worker threads: titles, thinker model, brief shapes, bookkeeping | [dispatch-workers.md](dispatch-workers.md) |
| Opposite-model code review as a 🏓 worker: when, brief, reviewer output, builder push-back | [code-review.md](code-review.md) |
| Ping an existing thread (ping-back, quoting trap, visibility) | [cross-thread-ping.md](cross-thread-ping.md) |
| Read a thread's transcript / brief / progress | [read-thread.md](read-thread.md) |
| Settle / unsettle / settle yourself (settle = kill) | [settle-thread.md](settle-thread.md) |
| Hide / unhide a live worker (snooze keeper) | [hide-thread.md](hide-thread.md) |
| Rename (hard-set title, `--prefix`, wait for auto-title) | [rename-thread.md](rename-thread.md) |
| Rate-limit windows per Claude + Codex profile (the numbers routing uses) | [limits.md](limits.md) |
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
