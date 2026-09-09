# Provider and T3 limitations

- Rolling windows are provider behavior, not a T3 defect. Models and effort live
  in `scripts/start.sh`; workdays (Mon–Fri 05:00–21:00), ten-minute interval and
  60-second grace live in `scripts/topup.py`. Times use the system zone with DST.
- Codex OAuth sometimes reports no session row even after a turn (2026-09-08).
  Missing rows are not evidence of expiry: skip them, or warm-up repeats forever.
  Error rows are also unknown and skipped.
- A reset inside the next poll interval gets one bounded wait until reset + grace.
  Dry-run never waits. After waiting, the workday gate is checked again.
- LaunchAgent `ProcessType=Interactive` avoids utility QoS throttling: Standard
  made T3 CLI calls take 15–25 seconds and left children visible ~90 seconds
  (2026-09-09). Keep launchd for persistence: T3's 30-minute session reaper and
  Mac sleep kill in-thread timers.
- Recovery uses the last message because limit hits leave sessions ready and
  turns completed. Monthly-plus-session banners follow their session reset;
  plain monthly caps need operator intervention. Explicit banner timezones win.
- Scheduled recovery freezes an inventory cutoff on its first attempt, protecting
  immediately re-limited threads from repeated pings. Draft discovery fails closed;
  ping timeouts re-read the store to distinguish landed dispatch from failed cleanup.
- Logs: `~/.t3/userdata/logs/t3-usage-windows-{topup,limited}.log`.
  Old logs are retained during migration. Retire recovery when T3 supports it
  natively; upstream quota failover issue #2471 was closed not-planned.
