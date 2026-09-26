# Hide a live thread (t3-hide-thread)

Flags: `t3-hide-thread --help` (`--hide` default, `--unhide`, one-shot
`--snooze`). Hiding never stops a session; stopping is [settle-thread.md](settle-thread.md).

**Invariant the keeper holds:** a hidden worker stays hidden only while it is
alive and unblocked; the moment it dies, is settled/archived, or needs the user,
it becomes visible again. Poll interval, snooze horizon and deadline are tuning:
see the `hide-worker` loop in `scripts/t3-hide-thread`. Log:
`/tmp/t3-hide-<THREAD_ID>.log`. Idempotent; 🏓 spawn arms it, a ping to a
snoozed thread re-arms it.

Why a keeper instead of one snooze: `thread.snooze` is visibility-only (allowed
while running), but T3 pops a snoozed thread back on every completed turn
([#6368](https://github.com/pingdotgg/t3code/issues/6368)), a pending
approval/user input, or a fresh session error, and any `thread.turn.start`
clears it. `thread.create` has no hidden field, so a fresh thread can flicker
into the sidebar before the keeper's first snooze.

**After a ping** the thread is visible until the pinged turn starts, at most
120 s: T3 refuses `thread.snooze` while the latest user message is queued
(`threadHasQueuedTurnStart`). Idle worker → re-snoozed within seconds; mid-turn
worker → visible until that turn ends or the cap. No command ordering avoids it;
the only bypass would be spoofing `createdAt`, which is deliberately not done.
The keeper mirrors that rule locally (`hold:queued-turn`) instead of spamming
rejected snoozes, and `t3-ping-thread` arms it before dispatching.

Gotchas:
- Keepers run under `t3_supervise` in `scripts/lib/t3-common.sh`; its comment
  explains why launchd jobs must be interactive (Background QoS delays the keeper).
- Compare completion times with `snoozedAt` at full fractional precision
  (`scripts/test_hide_thread.py`): a completion 1 ms later wakes the UI.
- A derived snooze wake makes a thread an auto-settle candidate
  ([#11788](https://github.com/pingdotgg/t3code/issues/11788); default 3 idle
  days, per-project). An active keeper prevents that; a thread whose keeper died
  can eventually be stopped by T3.

Keep this wrapper small: T3 owns thread/session/attention state; the keeper only
reconciles visibility. No worker registry or cached lifecycle state. Fixing the
120 s exposure needs native T3 send/snooze semantics
([upstream-checkpoint.md](upstream-checkpoint.md)), not faster polling.
