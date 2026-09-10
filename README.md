# Agent skills

Self-contained skills for Claude Code, Codex and other agents. MIT licensed.
Install with the [`skills` CLI](https://github.com/vercel-labs/skills): `pnpm dlx skills add pjmuller/skills -s <name> [-g] -y`,
then run that skill's `scripts/install` and `scripts/install --check` once (links its commands into `~/.local/bin`).

**Scope.** `-g` = global, one copy per machine in `~/.agents/skills`, available in every repo.
Without `-g` = repo-local: a tracked copy in `.agents/skills/<name>` + `skills-lock.json`, so cloud
sandboxes, worktrees and colleagues get the exact version the repo was tested with. Rule of thumb:
global for tools you call from any repo, repo-local for everything else.

| Skill | You need it when… | Scope | Install (then `scripts/install` + `--check`) |
| --- | --- | --- | --- |
| [t3-manage-thread](skills/t3-manage-thread/SKILL.md) | an agent must spawn, message, read, hide or settle another T3 Code thread, or read provider rate limits | global | `pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y` |
| [t3-schedule](skills/t3-schedule/SKILL.md) | a T3 thread should start on a wall clock ("every workday 07:30 run X"); macOS launchd | setup repo | `pnpm dlx skills add pjmuller/skills -s t3-schedule -y` |
| [t3-maintenance](skills/t3-maintenance/SKILL.md) | you orchestrate many worker threads: fleet view, stalled workers, unsent drafts, purge, prompt mining | setup repo | `pnpm dlx skills add pjmuller/skills -s t3-maintenance -y` |
| [t3-find-thread](skills/t3-find-thread/SKILL.md) | "which thread did we discuss X in?"; full-text search over local transcripts, jump to it | setup repo | `pnpm dlx skills add pjmuller/skills -s t3-find-thread -y` |
| [t3-usage-windows](skills/t3-usage-windows/SKILL.md) | you juggle several Claude/Codex accounts: warm five-hour windows, top up during the day, resume rate-limited threads | setup repo | `pnpm dlx skills add pjmuller/skills -s t3-usage-windows -y` |
| [video-shrink-for-gemini](skills/video-shrink-for-gemini/SKILL.md) | a screen recording must be small enough for Gemini and come with a context-rich prompt | setup repo | `pnpm dlx skills add pjmuller/skills -s video-shrink-for-gemini -y` |
| [disk-audit](skills/disk-audit/SKILL.md) | the Mac is filling up; deterministic audit, cleanup only of self-regenerating caches | setup repo | `pnpm dlx skills add pjmuller/skills -s disk-audit -y` |
| [resource-audit](skills/resource-audit/SKILL.md) | the Mac is slow or hot; CPU/RAM pressure, process ownership, targeted stopping and recovery | setup repo | `pnpm dlx skills add pjmuller/skills -s resource-audit -y` |
| [clickup-core](skills/clickup-core/SKILL.md) | agents in a product repo read/write ClickUp tasks (rich comments, attachments) against that repo's workspace config | product repo | `pnpm dlx skills add pjmuller/skills -s clickup-core -y` + a thin `clickup` skill holding `clickup.toml` |

Dependencies: t3-schedule, t3-maintenance and t3-usage-windows need t3-manage-thread's helpers; t3-usage-windows also needs t3-maintenance.
T3 Code must be running for the T3 skills. Thread helpers work on macOS and Linux/WSL; launchd scheduling and the top-up daemon are macOS-only.
`~/.local/bin` must be on the login-shell PATH.

Paste-to-your-agent version:

```
Install the skill <name> from github.com/pjmuller/skills with `pnpm dlx skills add pjmuller/skills -s <name> [-g] -y`,
run its scripts/install and scripts/install --check, fix what --check reports, then read its SKILL.md.
```

## Update

Nothing auto-updates. `pnpm dlx skills update -g` (global) or `pnpm dlx skills update -p` inside the
repo (commit the diff + lockfile), then rerun the updated skill's `scripts/install` and `--check`.
Updates replace installed files; keep personal customizations outside them. After updating
t3-schedule run `t3-schedule refresh`; with an enabled top-up daemon rerun `t3-usage-windows topup install`.
Releases and breaking changes: [CHANGELOG.md](CHANGELOG.md).

## Multiple Claude homes

`skills add -g` writes to the active `CLAUDE_CONFIG_DIR/skills` and `~/.agents/skills` only. With
several isolated Claude homes, symlink every home's `skills` directory and `~/.agents/skills` to one
directory first (the one-time setup below does this). A committed `.claude/skills -> ../.agents/skills`
symlink in a repo works with project installs (verified with skills CLI 1.5.24, 2026-09-09).

## One-time machine setup

Give your agent the bootstrap URL and your parameters (accounts, which skills, prompt base):
https://raw.githubusercontent.com/pjmuller/skills/main/setup/t3-setup/SKILL.md
It detects existing setup, unifies Claude homes, installs helpers, verifies a launchd smoke job and
ends with a feedback block. Tool-free fallback: clone this repo and read `setup/t3-setup/SKILL.md`.
