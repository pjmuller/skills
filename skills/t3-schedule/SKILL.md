---
name: t3-schedule
description: Run a T3 Code thread on a recurring wall-clock schedule (e.g. every workday 07:30 open a thread in project X with prompt Y) or once at a specific date/time (e.g. Saturday 08:00 downscale a server) via a macOS LaunchAgent. Use for "schedule a daily/weekly T3 job", "run this prompt once on Saturday at 08:00", "every morning run the fleet report", "list/remove scheduled T3 jobs", "/t3-schedule". Not for in-session timers (CronCreate, /loop) or resuming rate-limited threads (t3-usage-windows).
---

# t3-schedule

One helper, `scripts/t3-schedule` (tests: `scripts/test_t3_schedule.py`); subcommands and flags:
`t3-schedule --help` / `t3-schedule add --help`. Install: `scripts/install` (needs the
[t3-manage-thread](../t3-manage-thread/SKILL.md) helpers on PATH).

```bash
t3-schedule add --name nightly-report --at 07:30 --weekdays \
  --project ~/code/example/example-app -- "Run the nightly report skill for yesterday."
t3-schedule list --markdown   # answer "what's scheduled?" with this
```

- Unattended jobs: `add --settle-when-done` forwards the spawn helper's
  [fire-and-forget flow](../t3-manage-thread/spawn-thread.md#fire-and-forget---settle-when-done)
  (no 🏓 title). `--hide --no-notify` = hidden, no self-settle footer, no launch notification: the
  prompt or a helper it runs (e.g. `skills-refresh --job`) owns settle/unhide.
- A specific effort needs `--profile <account> --model sol --thinking high`: a root thread has no
  parent to inherit from.
- Never edit a runner by hand: `add --force` (one job) or `refresh` (all) regenerates it.

Pipeline: LaunchAgent `com.t3-skills.t3-schedule.<name>` → runner
`~/.t3/userdata/scheduled/t3-schedule/<name>.sh` (prompt in `<name>.prompt.md`) → waits for T3 Code
→ `t3-spawn-thread --no-open` → macOS notification. Log: `~/.t3/userdata/logs/t3-schedule.<name>.log`.
`ProcessType=Interactive` because `Standard` clamps each t3 CLI call to 15–25 s (2026-09-09).

## Contract

- **Root thread.** The runner unsets inherited thread env and `run-now` goes through launchd, so no
  parent is inherited even when fired from inside a T3 agent.
- **Model + profile at fire time.** `--model a,b` = ordered candidates; the first whose ecosystem is
  installed *and* has capacity wins (default `opus,sol`). Without `--profile`, `t3-spawn-thread`
  picks the account with most room ([one policy](../t3-manage-thread/spawn-thread.md#automatic-profile-routing)).
  The log shows each `-- probe model X` with the spawn helper's `--dry-run` routing decision.
  No candidate → the run fails and catch-up retries, so the job lands once a window resets instead
  of sitting as a blocked thread. No spreading across near-equal profiles: usage is re-read between
  jobs and real consumption ranks them.
- **Spacing (convention, not enforced).** Keep slots ≥15 min apart. The catch-up poller kicks one
  job per tick, earliest first, never while another runner is spawning, so limits are re-read
  between jobs even after a long power-off.
- **Missed or failed slot ⇒ catch-up, not tomorrow.** LaunchAgent `com.t3-skills.t3-schedule.catch-up`
  (armed by `add`/`refresh`; interval and grace are constants in `scripts/t3-schedule`) re-kicks any
  job whose slot passed today without a spawn, until the grace ends the same calendar day. Covers
  lid-closed wakes, reboots (launchd never replays after power-off), T3 down/updating, a broken
  spawn. At most one spawn per day (`<name>.last`, written on success only). Failures notify once
  per day (`<name>.failed`).
- **Provider limits / auth** are the thread's problem, same as a manual spawn: the banner shows and
  [t3-usage-windows](../t3-usage-windows/SKILL.md) recovers it. The notification + sidebar thread
  `⏰ <name> <date>` is the ack; nothing else pings the user.
- **One-shot (`--once`).** Same guarantees, one spawn; catch-up retries until 23:00 that day.
  launchd has no Year, so the runner skips other dates and any run after `<name>.last` exists; the
  poller then retires the job (plist + runner deleted, spec kept; `list` shows `fired <date>` or
  `expired (never fired)`).
