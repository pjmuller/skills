# Skills refresh: stay current on the T3 helpers

Your machine gets new releases of `t3-manage-thread` + `t3-schedule` by itself: a daily 06:30 job applies the newest
`vX.Y.Z` tag of `pjmuller/skills` (never `main`), then shows you once what changed. Nothing updates mid-task.

## Upgrade (you already have t3-manage-thread)

Paste to your agent (Claude Code or Codex):

```text
Run these in order and show me any failing line (exit 0 and exit 10 are both success for skills-refresh):
pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y
~/.agents/skills/t3-manage-thread/scripts/install
pnpm dlx skills add pjmuller/skills -s t3-schedule -g -y          # macOS only
~/.agents/skills/t3-schedule/scripts/install --relink             # macOS only; --relink replaces an older repo-local copy
skills-refresh                                                     # exit 10 = applied newest release tag, writes ~/.agents/pjmuller-skills.version
skills-refresh schedule --project <my personal setup repo path>
t3-schedule list                                                   # macOS: must show skills-refresh at 06:30
t3-schedule run-now skills-refresh                                 # macOS: one real run; expect "up to date" and a thread that settles itself
t3-spawn-thread --version                                          # must print v0.4.0 or higher
```

- Mac + Claude Code: T3 Code must be running for `run-now`; the job is a hidden T3 thread on a cheap model.
- WSL + Codex: skip the macOS lines; `skills-refresh schedule` installs a cron line instead (`sudo service cron start` once if cron is not running); output lands in `~/.agents/pjmuller-skills.log`.

## What you will see

- Nothing changed (most days): no thread, no notification.
- A release was applied: one thread `⏰ skills-refresh <date>` with `Skills vX.Y.Z applied` and the CHANGELOG entries since your previous version. Read, close.
- Something failed: the same thread with the error; old helpers keep working. Run `skills-refresh` by hand to retry.

Don't run `pnpm dlx skills update` or `skills check` on these two skills: they re-fetch `main` and bypass the release gate.
Bug report? Include the output of `t3-spawn-thread --version`.
How the job works (staging, rollback, lock, env overrides): [skills-refresh](../../skills/t3-manage-thread/skills-refresh.md).
