---
name: t3-usage-windows
description: Start provider usage windows with cheap turns and chain them through the day. Use for warming accounts, daytime top-ups, window status, or banked Codex resets. Rate-limited threads need nothing: T3 0.1 marks them Limited and auto-resumes at reset.
---

# T3 usage windows

A usage window is a provider's rolling quota period (commonly five hours), opened by a model turn.
Opening one early makes its reset come earlier; a turn inside an active window doesn't restart it.

`t3-usage-windows <verb>`; flags: `--help` per subcommand.

- `start` — one `t3-relay launch` per enabled Codex/Claude profile (Luna/Haiku, low effort,
  `scripts/start.sh`); each warm-up thread settles itself. `--dry-run` prints the commands.
- `topup install|status|remove|run` — launchd tick every 10 min, 05:00–21:00 (`scripts/topup.py`).
  Expired session windows get `start`; accounts without a session window (Codex: weekly only) get
  one turn per local day from 05:00 (state file beside the log). Needs T3 running; never wakes the
  Mac. Preview: `topup run --dry-run [--ignore-hours]`.
- `status` — quota windows (`t3-limits`).
- `reset` — banked reset credits of the logged-in Codex account (`scripts/reset_credit.py`).
  **Hard rule:** `--apply` spends a scarce credit (resets five-hour + weekly window), only with
  explicit user authorization. Unrelated to Luna Reserve or API credits.

Rate-limited threads: T3 0.1 shows them as Limited and resumes them at reset; no helper needed.

## Install

Needs `t3-relay` (with the relay task, [relay.md](../t3-manage-thread/relay.md)),
`t3-pick-instance`, `t3-limits` ([t3-manage-thread](../t3-manage-thread/SKILL.md)) on PATH, then
`scripts/install` and `--check`. Quirks, logs: [notes.md](notes.md).
