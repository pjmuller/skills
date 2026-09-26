# Provider and T3 limitations

- Rolling windows are provider behavior, not a T3 defect. Workday gate, tick interval and grace
  period: constants in `scripts/topup.py`; system timezone with DST.
- Codex OAuth sometimes reports no session row even after a turn (2026-09-08). A missing or error
  row is unknown, not expired: skip it, or warm-up repeats forever.
- A reset inside the next poll interval gets one bounded wait until reset + grace. Dry-run never
  waits; after waiting, the workday gate is checked again.
- LaunchAgents use `ProcessType=Interactive`: `Standard` got utility QoS, making T3 CLI calls take
  15–25 s and leaving children visible ~90 s (2026-09-09); a multi-GB store plus Chromium draft
  scan can then miss the operational window.
- Launchd, not in-thread timers: T3's ProviderSessionReaper stops idle provider sessions after
  30 min and Mac idle-sleep kills in-memory timers. Evidence: a 2 h `CronCreate` vanished while the
  LaunchAgent ran on time (2026-09-05); a 25 min `ScheduleWakeup` never fired after idle-sleep
  (2026-09-07). For waits > ~15 min use a LaunchAgent or have the worker `t3-ping-thread` back.
- Limit detection reads the last message because limit hits leave sessions ready and turns
  completed. Monthly-plus-session banners follow their session reset; plain monthly caps need the
  operator. Explicit banner timezones win.
- Logs: `~/.t3/userdata/logs/t3-usage-windows-{topup,limited}.log`.
- Retire recovery once T3 supports it natively; the upstream quota failover issue #2471 was
  closed not-planned.
- `reset` uses Codex CLI's experimental app-server methods `account/rateLimits/read` and
  `account/rateLimitResetCredit/consume` (verified with 0.155.0). There is no public HTTP API; keep
  the native protocol and fail when credit details are missing rather than consume an unspecified
  reset.
