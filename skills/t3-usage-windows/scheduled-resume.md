# Scheduled resume ("resume rate-limited t3 threads for <profile> [at HH:MM]")

Two-phase: preview now, act on a timer. Times use the system timezone. Limit banners with an explicit timezone keep that timezone.

## Now (preview + arm — two commands)
1. `t3-usage-windows limited list --profile <p> --since 7d` → show the user the titles + kind + reset.
2. `t3-usage-windows limited schedule --profile <p> [--at HH:MM] --notify-thread <this thread id>`
   → one-shot LaunchAgent `com.t3-skills.t3-usage-windows.limited.<profile>.<YYYYMMDD-HHMM>`.
   **No `--at`** → fire time derived from those same blocked rows: latest pending `reset_at` + 1 min;
   no pending reset (only `model`/`api`) → now + 2 min; nothing blocked → prints so, arms nothing,
   exit 0; only `monthly` → exit 1 (needs credits or `--force`). It prints the derivation.
   **`--at` given** → obeyed; a time before the latest pending reset only prints a warning (those
   threads would be skipped as "not resumable yet").
   `--dry-run` prints plist + script · `--list` / `--cancel LABEL` manage pending ones ·
   `--wait-max` (default 180 min) · `--ping-timeout` (default 120 s per thread) · log
   `~/.t3/userdata/logs/t3-usage-windows-limited.log`.
   `t3-limits --json --profile <p>` (skill `t3-manage-thread`) is only a cross-check now.
   - Optional secondary (only if you want the agent to *reason* in-thread at fire time): harness
     `CronCreate` (`recurring: false`, cron `"M H D Mo *"`) with the "On fire" block as prompt.
     Fragile: T3's ProviderSessionReaper stops idle provider sessions after 30 min, killing the
     in-memory cron — never rely on it alone. (Confirmed 2026-09-05: a 30-min CronCreate fired
     +9 s; a 2h-later one vanished without firing while the LaunchAgent ran on time.)
     Same for `ScheduleWakeup` (/loop dynamic): a 20-min wake fired, the next 25-min one never did
     (2026-09-07, Mac idle-slept in between). For waits > ~15 min, have the worker `t3-ping-thread`
     you when done, or use this LaunchAgent — never an in-memory timer.
   - Sleeping Mac: arming also spawns `caffeinate -i` until the fire (+3 min), so an idle Mac —
     lid open or clamshell, AC or battery — stays awake; `--no-caffeinate` skips it, `--cancel`/
     `--list` kill/report it (`awake=yes|no`). Lid closed without an external display still sleeps;
     launchd then runs the missed job at the next wake (2026-09-05: 16:51 job ran 16:57 on a Power
     Nap dark-wake). T3 Code must be running — the runner waits up to 3 h for it.
3. Immediately re-run `t3-usage-windows limited list --profile <p> --since 7d` and
   `t3-drafts list --limited`. Report the current—not initial—inventory, draft-held exceptions, and
   timer time/label. You can close the thread; the ping-back arrives later.

## On fire (fully scripted by the runner — no LLM involved)
1. Before the fire time, the runner exits without acting. At/after it, T3 being down exits quickly;
   launchd retries every 60 s until `--wait-max` rather than leaving one sleeping process.
   The plist uses `ProcessType=Interactive`; lower launchd QoS can throttle T3's multi-GB store and
   Chromium draft scan enough to miss the operational window.
2. Log `list`, re-read limited-thread drafts, run `resume`, then log/list again. Every attempt
   therefore discovers banners added since scheduling and proves which threads remain blocked.
   Draft-held threads are excluded and reported rather than receiving a blind `continue`.
3. Each ping has a hard timeout. A helper wedged after a successful dispatch is recognized by the
   fresh store state; an actual failure remains blocked and is retried on the next launchd tick.
   The first attempt freezes an inventory cutoff: a successfully pinged thread that immediately
   posts a newer limit banner is reported but not pinged every minute as part of the old limit cycle.
4. When none remain (or the deadline expires), ping `--notify-thread`, show a macOS notification,
   and self-remove. Never `--force` a monthly limit.

The runner fails closed when draft discovery itself fails or times out; it sends no blind
`continue`, remains armed, and retries on the next launchd tick.
