---
name: t3-schedule
description: Run a T3 Code thread on a recurring wall-clock schedule (e.g. every workday 07:30 open a thread in project X with prompt Y) via a macOS LaunchAgent. Use for "schedule a daily/weekly T3 job", "every morning run the fleet report", "list/remove scheduled T3 jobs", "/t3-schedule". Not for one-shot in-session timers (CronCreate, /loop) or resuming rate-limited threads (t3-resume-limited).
---

# t3-schedule

```bash
t3-schedule add --name fleet-report-work --at 07:30 --weekdays \
  --project ~/code/example/example-app --model fable \
  -- "Run the fleet-report-work skill for yesterday, end to end (ClickUp ticket included)."
t3-schedule pick-profile    # Claude profile with the most spare room now (capacity rule, scripted)
t3-schedule list            # jobs · loaded? · profile/model · last run + result
t3-schedule list --markdown # same as a table — use this when the user asks "what's scheduled?"
t3-schedule run-now NAME    # launchctl kickstart + prints the runner's log (real spawn)
t3-schedule show NAME       # spec + prompt
t3-schedule set-at NAME HH:MM  # move a slot (keeps prompt/profile/model); keep jobs ≥15 min apart
t3-schedule remove NAME
t3-schedule catch-up [--dry-run]  # the poller's tick: re-kick jobs whose slot passed today without a spawn
t3-schedule refresh         # regenerate all runners/plists after a template change; re-arms the poller
```

Use `add --settle-when-done` for unattended jobs: forwards the spawn helper's
[fire-and-forget flow](../t3-manage-thread/spawn-thread.md#fire-and-forget---settle-when-done),
which hides the running thread and appends self-settlement instructions. Do not use a 🏓 title.
For Sol High, pass `--profile codex --model sol --thinking high` to bypass Claude profile selection.

One job = LaunchAgent `com.t3-skills.t3-schedule.<name>` (`~/Library/LaunchAgents`, `ProcessType=Interactive` —
`Standard` still clamps the t3 CLI to 15-25 s per call, measured 2026-09-09) → runner
`~/.t3/userdata/scheduled/t3-schedule/<name>.sh` → waits for T3 Code (≤ `--wait-max` min, default 10)
→ `t3-spawn-thread --project … --no-open --title "⏰ <name> <date>" -- "<prompt>"` → macOS
notification. Log: `~/.t3/userdata/logs/t3-schedule.<name>.log`. Prompt lives in `<name>.prompt.md`
(or `--prompt-file`). `--days mon,thu` / `--weekdays` / default daily. `--title` accepts `{date}`.

Install: `scripts/install` (symlink into `~/.local/bin`, needs the
`t3-manage-thread` helpers on PATH).

## Contract
- **Spawn is a root thread.** The runner unsets `CODEX_THREAD_ID` etc. and `run-now` goes through
  launchd, so no parent thread is inherited even when fired from inside a T3 agent.
- **Profile.** Omit `--profile` → the runner asks `t3-schedule pick-profile` at fire time: capacity-based routing (skip session ≥90 % / weekly ≥95 % used; rank by long-window room + ½
  session room, minus 15 points per scheduled job that profile already got in the last 3 h —
  `picks.log` — so near-equal profiles alternate while exhausted ones stay skipped; all blocked →
  soonest session reset). `t3-limits` down → project default, logged.
- **Spacing.** Slots are ≥15 min apart and the
  catch-up poller kicks **one job per tick** (earliest slot first, never while another runner is
  spawning), so limits are re-read between jobs even after a long power-off.
- **Missed or failed slot ⇒ catch-up, not tomorrow.** One extra LaunchAgent
  `com.t3-skills.t3-schedule.catch-up` (every 15 min + at login, armed by `add`/`refresh`) kickstarts
  any job whose slot passed today, has no `<name>.last` for today and is not running — until
  slot+10h, same calendar day. Covers lid-closed wakes, reboots (launchd never replays after a
  power-off), T3 down/updating, a broken spawn. **At most one spawn per day** (`<name>.last`,
  written on success only).
- **T3 Code not running** ⇒ runner waits `--wait-max` (default 10 min), exits, catch-up retries.
  Failures notify once per day (`<name>.failed`); success always notifies. Helpers fall back to
  `~/.t3/userdata/last-server-origin` when `server-runtime.json` is missing but the server answers.
- **Provider limits / auth** are the thread's problem, same as a manual spawn: a rate-limited
  thread shows the banner and `t3-limited` handles it; expired `rc`/Claude OAuth surfaces in the
  thread. The daily notification + sidebar thread `⏰ name date` is the ack; nothing else pings the user.
- Never edit `<name>.sh` by hand — `add --force` (one job) or `refresh` (all) regenerates it.
