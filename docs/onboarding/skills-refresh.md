# Skills refresh: stay current on the T3 helpers

Your machine gets new releases of `t3-manage-thread` + `t3-schedule` by itself: a daily 06:30 job applies the newest
`vX.Y.Z` tag of `pjmuller/skills` (never `main`), then shows you once what changed. Nothing updates mid-task.

## Upgrade (you already have t3-manage-thread)

Paste to your agent (Claude Code or Codex):

```text
Run these in order and show me any failing line (exit 0 and exit 10 are both success for skills-refresh):
pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y -a claude-code   # add -a codex when Codex is installed
~/.agents/skills/t3-manage-thread/scripts/install
pnpm dlx skills add pjmuller/skills -s t3-schedule -g -y -a claude-code
~/.agents/skills/t3-schedule/scripts/install --relink     # --relink replaces an older repo-local copy
skills-refresh                                                     # exit 10 = applied newest release tag, writes ~/.agents/pjmuller-skills.version
skills-refresh schedule --project <my personal setup repo path>
t3-schedule list                                                   # must show skills-refresh at 06:30
t3-schedule run-now skills-refresh                                 # one real run; expect "up to date" and a thread that settles itself
t3-spawn-thread --version                                          # must print v0.4.0 or higher
```

- Both platforms: T3 Code must be running; the job is a hidden T3 thread on a cheap model.
- macOS uses launchd; Linux/WSL uses persistent systemd user timers. Run the installer check
  to verify the service manager and runner PATH. Windows execution stays inside WSL.
- Keep the computer awake and WSL running (T3 connected to its WSL backend). A systemd
  timer cannot start a stopped WSL distribution. Times use the machine zone (`date +%Z`).
- Rerun `skills-refresh schedule` to migrate the old Linux cron entry; it removes only
  its tagged cron line after the new timer has been armed successfully.

## What you will see

- Nothing changed (most days): no thread, no notification.
- A release was applied: one thread `⏰ skills-refresh <date>` with `Skills vX.Y.Z applied` and the CHANGELOG entries since your previous version. Read, close.
- Something failed: the same thread with the error; old helpers keep working. Run `skills-refresh` by hand to retry.

Don't run `pnpm dlx skills update` or `skills check` on these two skills: they re-fetch `main` and bypass the release gate.
Bug report? Include the output of `t3-spawn-thread --version`.
How the job works (staging, rollback, lock, env overrides): [skills-refresh](../../skills/t3-manage-thread/skills-refresh.md).
