# Scheduled resume ("resume rate-limited t3 threads for <profile> [at HH:MM]")

Two-phase: preview and arm now, act on a launchd timer. Flags/defaults:
`t3-usage-windows limited schedule --help`. Why launchd and not an in-thread timer: [notes.md](notes.md).

## Now

1. `t3-usage-windows limited list --profile <p> --since 7d` → show titles + kind + reset.
2. `t3-usage-windows limited schedule --profile <p> [--at HH:MM] --notify-thread <this thread id>`
   → one-shot LaunchAgent `com.t3-skills.t3-usage-windows.limited.<profile>.<YYYYMMDD-HHMM>`; it
   prints how the fire time was derived. Without `--at` the blocked rows decide: latest pending
   reset + 1 min; no pending reset (only model/api) → now + 2 min; nothing blocked → arms nothing,
   exit 0; only monthly caps → exit 1 (needs credits or `--force`). An `--at` before the latest
   reset only warns: those threads would be skipped as not resumable yet.
   Arming also runs `caffeinate -i` until the fire, so an idle Mac stays awake. A closed lid
   without an external display still sleeps; launchd then runs the missed job at the next wake.
   T3 Code must be running at fire time; the runner waits for it up to `--wait-max`.
3. Re-run the `limited list` and `t3-drafts list --limited`; report the current (not initial)
   inventory, draft-held exceptions, and timer time/label. The thread may close; the ping-back
   arrives later.

## On fire (scripted runner, no LLM)

- Before the fire time the runner exits without acting; if T3 is down it exits and launchd retries
  every 60 s until `--wait-max`, rather than one long sleeping process.
- Each attempt re-lists, re-reads drafts and runs `resume --protect-drafts`, so banners added since
  scheduling are picked up and draft-held threads are reported, not sent a blind `continue`. Draft
  discovery failing or timing out fails closed: nothing sent, retried next tick.
- Each ping has a hard timeout; a helper wedged after a successful dispatch is recognized from the
  fresh store state, a real failure is retried next tick. The first attempt freezes an inventory
  cutoff, so a thread that re-limits right after its ping is reported, not pinged every minute.
- When nothing remains (or the deadline passes): ping `--notify-thread`, macOS notification,
  self-remove. Never `--force`s a monthly limit.

`t3-limits --json --profile <p>` ([t3-manage-thread](../t3-manage-thread/SKILL.md)) is only a
cross-check.
