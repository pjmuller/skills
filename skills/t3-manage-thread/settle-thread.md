# Settle a thread (t3-settle-thread)

Flags: `t3-settle-thread --help` (`--wait`, `--self`, `--unsettle`,
`--only-settled-at`, `--detach`, `--dry-run`). Every mode prints the resulting
`settledOverride` / `settledAt` / `snoozedUntil`, and the server's reason on
refusal. Hiding a *live* worker is [hide-thread.md](hide-thread.md); the old
`--hide` / `--snooze` flags here exit non-zero pointing there.

## Hard rule: settle = stop (data loss)

`thread.settle` always chains `thread.session.stop` for any session not already
stopped, including `ready`. That kills the `claude`/`codex` process **and every
background sub-agent inside it**, so settling a working thread destroys
unreported work. Settle only after a worker's final report is in and verified.
The server refuses while the session is starting/running, an approval or user
input is open, or a turn start is queued — hence `--wait`. Not archive; idempotent.

A normal turn end is *not* a stop: the session stays `ready` and background
sub-agents survive and re-wake the thread. That is why 🏓 workers are hidden,
not settled, while they run.

## Settle yourself ("…then settle this thread")

`--self` resolves the calling thread from `CODEX_THREAD_ID` /
`CLAUDE_CODE_SESSION_ID` and arms a detached worker (`t3_supervise`) bound to
the current turn; it settles seconds after the turn ends. Same kill semantics,
so only on the user's explicit request:

1. Finish all work. No background shells, sub-agents or monitors alive (`--self`
   warns on open tasks): settle kills them, and a later task notification would
   re-wake and unsettle the thread.
2. `t3-settle-thread --self` is the **LAST** tool call (foreground).
3. End the turn with the final answer. Nothing after, not even reading
   `/tmp/t3-settle-<THREAD_ID>.log`.

`--wait <own id>` is refused: your own turn *is* the running session.

Fleet-wide settle/unsettle repair: [t3-maintenance](../t3-maintenance/SKILL.md).
Native settle tool status: [upstream-checkpoint.md](upstream-checkpoint.md).
