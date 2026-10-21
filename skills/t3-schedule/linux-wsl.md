# Linux / Windows through WSL

Run all helpers inside Linux; Windows uses the same systemd backend through WSL (no Task
Scheduler bridge). Needs systemd, a running **user** manager and `/bin/zsh`; no cron fallback.
`install --check` / `t3-schedule check` verify it.

- Per job `~/.config/systemd/user/com.t3-skills.t3-schedule.<name>.timer` + `.service`:
  `OnCalendar` (year included for one-shots), `Persistent=true`, `AccuracySec=1s`. A persistent
  wake-up outside the catch-up window skips; a file lock prevents simultaneous manual/timed runs.
- Catch-up timer: 1 min after the user manager starts, then every 15 min.
- **systemd does not keep WSL alive or wake a suspended Windows machine.** Keep it awake; an
  overdue one-shot catches up within its window or expires visibly in `list`.
  `loginctl enable-linger "$USER"` keeps the user manager up without a login (only when needed).
- Notifications: a Windows tray balloon through `powershell.exe` (WSL interop) when available,
  else none; evidence is then the T3 thread, `list` and the log. Test: `t3-schedule notify hello`.
  `systemctl --user list-timers`, `journalctl --user -u com.t3-skills.t3-schedule.<name>.service`.

`scripts/smoke-native-scheduler` (both platforms) arms a marker-only timer/LaunchAgent, waits
for it to fire, removes only its own artefacts; no T3 needed.

Refs: [WSL systemd](https://learn.microsoft.com/en-us/windows/wsl/systemd),
[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html),
[loginctl](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).
