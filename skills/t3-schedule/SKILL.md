---
name: t3-schedule
description: Run a T3 Code thread on a recurring wall-clock schedule (e.g. every workday 07:30 open a thread in project X with prompt Y) or once at a specific date/time (e.g. Saturday 08:00 downscale a server) via a macOS LaunchAgent, or wake an existing thread later to continue its work (continuation). Use for "schedule a daily/weekly T3 job", "run this prompt once on Saturday at 08:00", "every morning run the fleet report", "check back on this thread tomorrow 09:00", "list/pause/resume/remove scheduled T3 jobs", "/t3-schedule". Not for in-session timers (CronCreate, /loop) or resuming rate-limited threads (t3-usage-windows).
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

## Versioned definitions

A recurring job's definition lives in its project repo so it survives a machine reset and gets
reviewed: `<project>/.agents/schedules/<name>.json` (portable fields only: no path, no profile) +
`<name>.prompt.md`. `add` writes both; **the caller commits them** (the helper never commits).
The runtime dir keeps a machine-local pointer (`source`, `profile`), runner, plist and state.

- Prompt edits apply at the next fire (the runner reads the repo file); time/model/flag edits need
  `refresh`. `list` flags `untracked`/`uncommitted`/`MISSING` specs, stale runners and
  `local-only` jobs.
- Cloning a repo arms nothing: `t3-schedule adopt <repo | spec.json> [--profile X]` opts a machine in
  (colleagues never inherit jobs by accident).
- `remove` disarms this machine only; `git rm` the two files to drop the job for everyone.
- `pause <name> [--until YYYY-MM-DD]` marks the repo spec paused on every machine after pull;
  `resume <name>` clears it. Commit + push the spec. `--until` resumes at local midnight at the
  start of that date on each machine; the spec remains paused until `resume` clears it. LaunchAgents
  and `adopted_by` stay intact. Run `refresh` once after upgrading old runners; subsequent
  pause/resume changes need no refresh. Runners and catch-up read the spec at fire time.
  `list` and `show` display effective status. Existing spawned threads are untouched.
- `--once` and `--resume-thread` jobs stay machine-local (ephemeral).

### One machine or many

The repo spec records `machines` (`one` default; `add --many-machines` → `many`) and `adopted_by`
(`machine` label, repo `git user.name`, `since`, random `id` from `~/.t3/userdata/scheduled/t3-schedule/meta/machine.json`;
no hostname/serial; `t3-schedule machine --label X` sets a readable label). `add`/`adopt`/`remove` update it; commit + push.

- **one**: adopting a job registered to another machine asks "confirm it no longer runs there" at a terminal;
  unattended it fails unless `--takeover`. `--force` never implies takeover (also on `add`/`migrate --force`).
- **many**: every adopter is appended; no prompt.
- **Displaced**: a one-machine job whose `adopted_by` no longer lists this machine skips (runner checks before
  waiting for T3 and right before the spawn; catch-up ignores it; `list` flags it). Lost identity file = skip too;
  recover with `adopt --takeover`. `adopted_by: []` (last machine removed it) skips everywhere until someone adopts;
  specs without the key (pre-registration) run as before.
- **Limits**: registration is intent in the local checkout, not a lock. The old machine stops only after it pulls
  the takeover; an offline/stale checkout or two machines adopting at once can still double-fire until then.
  Threads already running are untouched.
- Pre-versioning jobs: `t3-schedule migrate [name…]` writes their repo files, then commit.

## Continuation (`--resume-thread ID`)

Wakes an existing thread with the prompt as a user turn (`t3-ping-thread`, framed "Scheduled
follow-up (<date>), as agreed earlier in this thread: …") instead of spawning; `--project`
defaults to that thread's. Choose it when the follow-up needs this thread's context
(investigation state, decisions, evidence); standalone when the prompt is self-contained or
recurring. Usually `--once`; recurring works too (pings the same thread daily).

- **Resumable** = `t3-read-thread` finds it, not deleted/archived, its provider instance is in
  `t3-list-profiles`, and the ping lands (settled is fine: the turn wakes it; busy is fine: T3
  queues, the ping helper retries a refused dispatch). Checked at `add` and again at fire time. A failed ping first re-reads the thread for its dated marker turn (lost ack ≠ not delivered), so a job never both resumes and spawns.
- **Otherwise fallback**: a normal spawn (`--model/--profile/--thinking/--title/--project`
  shape only this thread) whose prompt = the scheduled prompt + a bounded context pack (original
  brief, latest messages, original id). `--hide` applies to both paths; `--settle-when-done` is
  refused (the thread owns its lifecycle, say it in the prompt).
- Log/notification: `resumed <title> (<id>)` vs `fallback (<reason>): spawned …`. `.last` and
  catch-up behave as for spawns.

Pipeline: LaunchAgent `com.t3-skills.t3-schedule.<name>` → runner
`~/.t3/userdata/scheduled/t3-schedule/<name>.sh` (prompt: repo file, or `<name>.prompt.md` there for
local jobs) → waits for T3 Code
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
