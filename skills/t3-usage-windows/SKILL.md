---
name: t3-usage-windows
description: "Use for \"warm up my accounts\", \"start the usage windows\", \"when do my windows reset\", the daytime top-up daemon, or spending a banked Codex reset. Not rate-limited threads (T3 resumes them at reset)."
---

# T3 usage windows

A usage window is a provider's rolling quota period (commonly five hours), opened by a model turn.
Opening one early makes its reset come earlier; a turn inside an active window doesn't restart it.

`t3-usage-windows <verb>` (`--help` per verb):

- `start`: one `t3-relay launch` per enabled Codex/Claude profile (Luna/Haiku, low effort,
  `scripts/start.sh`); the relay waits up to 90 seconds and settles completed, untouched first
  runs. Failed, unfinished or repurposed threads stay open. `--dry-run` prints the commands.
- `topup install|status|remove|run`: launchd tick every 10 min, 05:00–21:00 (`scripts/topup.py`).
  Expired session windows get `start`; accounts without a session window (Codex: weekly only) get
  one turn per local day from 05:00. Successful morning launches are recorded per account,
  so a failed account doesn't restart the others. Needs T3 running; never wakes the Mac. Preview:
  `topup run --dry-run [--ignore-hours]`.
- `status`: quota windows (`t3-limits`).
- `reset`: banked reset credits of the logged-in Codex account (`scripts/reset_credit.py`).
  **Hard rule:** `--apply` spends a scarce credit (resets five-hour + weekly window), only with
  explicit user authorization. Unrelated to Luna Reserve or API credits.

Rate-limited threads: authorized recovery onto another account → `t3-fleet list --limited`, then
[t3-manage-thread recovery](../t3-manage-thread/workers.md#recover-a-limit-interrupted-owner).
Never infer completion from the sidebar status alone.

Needs `t3-relay`, `t3-pick-instance`, `t3-limits` ([t3-manage-thread](../t3-manage-thread/SKILL.md))
on PATH; then `scripts/install` (`--check`). Quirks, logs: [notes.md](notes.md).
