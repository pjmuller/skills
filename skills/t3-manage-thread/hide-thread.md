# Hide a live thread (t3-hide-thread)

```bash
t3-hide-thread --hide THREAD_ID     # keep a LIVE worker out of the sidebar
t3-hide-thread --unhide THREAD_ID   # stop the keeper + unsnooze
```

`--snooze DURATION`, `--unsnooze`, `--dry-run`: `--help`. Nothing here stops a
session; that is [settle-thread.md](settle-thread.md).

`thread.snooze` is visibility-only (collapsed Snoozed shelf; allowed while
running), but T3 pops a snoozed thread back on every completed turn
([#6368](https://github.com/pingdotgg/t3code/issues/6368), fix PR #7179
unmerged), on a pending approval/user-input, and on a fresh session error; any
`thread.turn.start` (a ping) clears it. `--hide` therefore arms a detached
**keeper** (launchd / `systemd-run --user` / `setsid`) that re-snoozes the thread.

**After a ping** the thread is visible until the pinged turn starts, or at most
120s: T3 refuses `thread.snooze` while the latest user message is "queued"
(`threadHasQueuedTurnStart`: message younger than 120s and no turn with
requestedAt/startedAt/completedAt ≥ it). Idle worker → the turn adopts the
message within ~1s → re-snoozed 1-3s after the ping (measured 2026-09-09).
Worker mid-turn → visible until its current turn completes or the 120s cap,
by T3 design; no command ordering avoids it (turn.start always unsnoozes; the
only bypass would be spoofing `createdAt` outside the ±120s skew window — not
done). The keeper evaluates the same rule locally (`hold:queued-turn`, 2s poll)
instead of spamming rejected snoozes, and `t3-ping-thread` arms it *before*
dispatching the turn.

Keepers run as a bootstrapped launchd plist with `ProcessType=Interactive`
(`t3_supervise`), not `launchctl submit`: submitted jobs get Background QoS and
every step crawls (keeper start 40-50s after arming, 2026-09-09).

The invariant the keeper exists to hold: **a hidden worker stays hidden only
while it is alive and unblocked** — the moment it dies, is settled/archived, or
needs PJ, it must become visible again. Poll interval, snooze horizon and the
keeper's own deadline are tuning, not contract: see the `hide-worker` loop in
`scripts/t3-hide-thread`. Re-arming is idempotent (🏓 spawn arms it; a ping to
an already-snoozed thread re-arms it). Log: `/tmp/t3-hide-<THREAD_ID>.log`.
