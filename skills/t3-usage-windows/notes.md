# Provider and T3 limitations

- Rolling windows are provider behavior. Hour gate, tick, grace: constants in `scripts/topup.py`;
  system timezone with DST.
- Codex OAuth reports no session row even after a turn (2026-09-08), only a weekly window. A
  missing row isn't expired (would re-fire every tick), so topup gives it one morning turn a day.
  Error rows are skipped.
- A reset inside the next tick gets one bounded wait (reset + grace); dry-run never waits.
- LaunchAgent uses `ProcessType=Interactive`: `Standard` got utility QoS, making T3 CLI calls take
  15–25 s (2026-09-09).
- Launchd, not in-thread timers: idle-sleep and T3's session reaper kill in-memory timers
  (2026-09-05/07).
- Warm-ups use `t3-relay --settle-after-run 90`: the launcher waits and settles a completed
  first run through MCP, without relying on the model to discover a tool. Failed, unfinished,
  snoozed or repurposed threads stay open. Launch acceptance remains successful if cleanup
  fails, so cleanup errors don't relaunch an account. `status` shows quota windows.
  The project must be a registered T3 project.
- Log: `~/.t3/userdata/logs/t3-usage-windows-topup.log`.
- `reset` uses Codex CLI's experimental app-server methods `account/rateLimits/read` and
  `account/rateLimitResetCredit/consume` (verified 0.155.0). No public HTTP API; fail when credit
  details are missing rather than consume an unspecified reset.
