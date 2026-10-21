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
skills-refresh --version                                           # prints the applied release tag
```

- Both platforms: the scheduler installs the release first, without T3 (`skills-refresh --apply`), so a
  release that repairs broken T3 tooling still lands. Then a T3 thread on a cheap model reports and settles
  itself (T3 Code ≥ 0.1). Jobs armed before v0.5.9 gain that step on their next run; nothing to redo.
- macOS uses launchd; Linux/WSL uses persistent systemd user timers. Run the installer check
  to verify the service manager and runner PATH. Windows execution stays inside WSL.
- Keep the computer awake and WSL running (T3 connected to its WSL backend). A systemd
  timer cannot start a stopped WSL distribution. Times use the machine zone (`date +%Z`).
- Rerun `skills-refresh schedule` to migrate the old Linux cron entry; it removes only
  its tagged cron line after the new timer has been armed successfully.

## What you will see

- Nothing changed (most days): no thread, no notification.
- A release was applied: one thread `⏰ skills-refresh <date>` with `Skills vX.Y.Z applied` and the CHANGELOG entries since your previous version. Read, close.
- The shared global-prompt template changed since the marker at the end of your global prompt:
  the same thread hands the merge to a frontier model, which commits clear improvements (your own
  rules win), logs skips and lists questions. Uncommitted edits in your prompt: it only recommends.
- Something failed: the same thread with the error; old helpers keep working. Run `skills-refresh` by hand to retry.
- Something only you can fix: an `ACTION NEEDED` block at the end of the thread. A scheduler that
  can't fire or a pending commit/push is re-checked every day until fixed; a command a release removed
  but your prompt or own skills still use is listed in that release's update thread.
- The scheduler itself can't start threads (T3 closed, relay broken): updates still install, and the
  report waits for the next thread. You get one notification per job per day (macOS; Windows tray under
  WSL) and the log `~/.t3/userdata/logs/t3-schedule.<job>.log`. The next release usually fixes it by
  itself; `skills-refresh` by hand applies it now and prints the same ACTION block.
- Your skills dir lives in a git repo: each update is committed there (only the refreshed skills),
  and pushed unless you have unpushed commits of your own.

Don't run `pnpm dlx skills update` or `skills check` on these two skills: they re-fetch `main` and bypass the release gate.
Bug report? Include the output of `skills-refresh --version`.
How the job works (staging, rollback, lock, env overrides): [skills-refresh](../../skills/t3-manage-thread/skills-refresh.md).
