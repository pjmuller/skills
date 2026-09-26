---
name: t3-usage-windows
description: Start provider usage windows with cheap turns, chain them during the workday, and resume or schedule recovery of rate-limited T3 Code threads. Use for warming accounts, daytime top-ups, window status, banked Codex resets, or unblocking threads after a usage reset. Ordinary stalled workers belong to t3-maintenance.
---

# T3 usage windows

A usage window is a provider's rolling quota period (commonly five hours) opened by a model turn.
Starting one early makes its reset arrive earlier; a turn inside an active window does not restart
the clock.

`t3-usage-windows <verb>`; flags, defaults and signal detection: `--help` on each subcommand.

- `start` — one cheap turn per enabled Codex/Claude profile (models: `scripts/start.sh`), verifies
  the selection, settles every child; the calling thread keeps running.
- `topup install|status|remove|run` — launchd tick that restarts only *expired* session windows
  during the workday (`scripts/topup.py`). Needs T3 running; never wakes the Mac. Decision preview:
  `topup run --dry-run --ignore-hours`.
- `status` — quota windows + blocked-thread count.
- `limited list|resume|schedule` — rate-limited thread recovery (`scripts/limited.py`). `resume`
  posts `continue`; it skips monthly caps and pending resets unless `--force` — never `--force` a
  monthly cap without the user. Run `t3-drafts list --limited` first and pass `--protect-drafts` so
  threads holding an unsent draft are not buried under a blind `continue`. Re-list right after
  resuming and report the current inventory. Timed recovery: [scheduled-resume.md](scheduled-resume.md).
- `reset` — banked reset credits of the logged-in Codex account (`scripts/reset_credit.py`).
  **Hard rule:** `--apply` spends a scarce credit (resets both the five-hour and weekly window) —
  only with explicit user authorization. Unrelated to Luna Reserve or API credits.

Ordinary stalled (not limited) workers: [t3-maintenance](../t3-maintenance/SKILL.md) `t3-fleet`.

## Install

Needs [thread helpers](../t3-manage-thread/SKILL.md) (`t3-limits`, ping/settle/spawn) and
[t3-maintenance](../t3-maintenance/SKILL.md) (store access, `t3-drafts`) on PATH, then
`scripts/install` and `--check`. `t3-limited` is a legacy alias for `t3-usage-windows limited`.
`topup install` migrates the legacy `com.t3-skills.t3-hello-world-topup` LaunchAgent
(`topup status --json` shows both). Let pending one-shot resumes
(`com.t3-skills.t3-usage-windows.limited.*`) finish before updating.

Provider quirks, why launchd over in-thread timers, logs: [notes.md](notes.md).
