# Settle a thread (t3-settle-thread)

```bash
t3-settle-thread --wait THREAD_ID   # ✓ Settle another thread — STOPS its session. Terminal.
t3-settle-thread --self             # ✓ Settle the CALLING thread once this turn ends.
```

`--unsettle`, `--only-settled-at`, `--detach`, `--dry-run`: `--help`. Every mode
prints the resulting `settledOverride` / `settledAt` / `snoozedUntil`; on refusal,
the server's reason from the trace log. Hiding a *live* worker is a different
lifecycle — [hide-thread.md](hide-thread.md); the old `--hide` / `--snooze` flags
here now exit non-zero pointing there.

## Hard rule: settle = stop (data loss)

`thread.settle` always chains `thread.session.stop` for any session not already
stopped, including `ready` (verified in T3 source, v0.0.38). The adapter closes
the query: SIGTERM/SIGKILL of the `claude`/`codex` process **and every background
sub-agent inside it**. Settling a working thread destroys unreported work. So:
settle only after a worker's final report is in and verified. The server refuses
while the session is starting/running, an approval/user-input is open, or a turn
start is queued — hence `--wait`. Not archive; idempotent.

A normal turn end is *not* a stop: the session stays `ready`, the process stays
resident, background sub-agents survive and re-wake the thread. That is why 🏓
workers are hidden rather than settled, and why blocking sub-agents aren't required.

## Settle yourself ("…then settle this thread")

`--self` resolves the calling thread (`CODEX_THREAD_ID` for Codex,
`CLAUDE_CODE_SESSION_ID` for Claude — matched against T3's provider runtime) and
arms a detached launchd worker bound to the *current turn*; it settles ~2 s after
the turn ends. Same kill semantics, so only on PJ's explicit request. Rule:

1. Finish all work. No background Bash, sub-agents or monitors may be alive —
   `--self` warns when it sees open tasks. Settle kills them (status `stopped`)
   and a later task notification would re-wake and unsettle the thread.
2. `t3-settle-thread --self` is the **LAST** tool call (foreground shell).
3. End the turn with the final answer. Nothing after — not even reading the log
   (`/tmp/t3-settle-<THREAD_ID>.log`).

`--wait <own id>` is refused (the server rejects settle while the session runs,
and the caller's turn *is* the running session — it used to time out after 120 s).
Verified 2026-09-06 (Claude haiku + Codex astra, DentAI profile): baseline,
backgrounded Bash and background sub-agent all stayed settled ≥15 min; a
`t3-ping-thread` unsettles with `reason=activity` (a real wake, expected).

Related: [spawn-thread.md](spawn-thread.md), [cross-thread-ping.md](cross-thread-ping.md),
fleet audits in `.agents/skills/t3-maintenance`. Upstream: no provider-facing
settle/snooze tool as of v0.0.38 — see the
[T3 Code reference](../../../recommendations/t3_code.md) before extending.
