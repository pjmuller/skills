# Agent skills

Self-contained skills for Claude Code, Codex and other agents. MIT licensed. This
is a **skill source repository**: it distributes reusable skills and templates,
not anyone's live personal configuration.
Register with the [`skills` CLI](https://github.com/vercel-labs/skills): `pnpm dlx skills add pjmuller/skills -s <name> [-g] -y`,
then, for skills that ship commands, run `scripts/install` and `scripts/install --check` once
(links their commands into `~/.local/bin`). Instruction-only skills need no installer.

## Registration scope

**Global registration** (`-g`) makes a skill discoverable in every repository on
one machine. **Repo-local registration** (omit `-g`) writes a tracked copy to
`.agents/skills/<name>` plus `skills-lock.json`, so worktrees, cloud sandboxes and
colleagues discover the version that repository expects. Register as little as
possible globally; this catalog recommends only `t3-manage-thread` globally by
default.

A **personal setup repository** owns one person's machine setup, operator workflows
and periodic maintenance. A **project repository** owns product, team or domain work.
Repo-local does not mean project-specific: machine, prompt and writing-style skills
usually belong in the personal setup repository. A **bootstrap** consumes setup
instructions or templates once to establish live configuration; the installed
skills remain useful for later maintenance. Templates are reusable inputs. Live
configuration belongs outside replaceable skill installations.

Skill discovery and command availability are separate. A repo-local skill's
`scripts/install` may expose helpers globally on `PATH`; that does not globally
register its instructions. `~/.local/bin` must be on the login-shell `PATH`.
Start a new agent session after changing registration because harnesses may cache
their discovered skill list.

| Skill | You need it when… | Scope | Register (then `scripts/install` + `--check`) |
| --- | --- | --- | --- |
| [slides](skills/slides/SKILL.md) | create, edit or review presentations: story, visual craft, notes and bundled Slidev expertise | project repo + `project-slides` wrapper | `pnpm dlx skills add pjmuller/skills -s slides -y` (no command installer) |
| [migration-parity](skills/migration-parity/SKILL.md) | migrate a working system with independent old/new data, UI and side-effect verification | project repo, while migration is active | `pnpm dlx skills add pjmuller/skills -s migration-parity -y` (no command installer) |
| [agents-md](skills/agents-md/SKILL.md) | create or simplify a repo's AGENTS.md / CLAUDE.md, write, prune and merge the global cross-project prompt ([template](skills/agents-md/global-template.md)), or write a handoff ([patterns](skills/agents-md/handoff.md)) | personal setup repo; target project when explicitly wanted there | `pnpm dlx skills add pjmuller/skills -s agents-md -y` (no command installer) |
| [tone-of-voice](skills/tone-of-voice/SKILL.md) | create or refresh `tone-of-voice.md` from an interview and real samples ([starter](skills/tone-of-voice/template.md)) | personal setup repo; target project when explicitly wanted there | `pnpm dlx skills add pjmuller/skills -s tone-of-voice -y` (no command installer) |
| [t3-manage-thread](skills/t3-manage-thread/SKILL.md) | an agent must spawn, message, read, hide or settle another T3 Code thread, or read provider rate limits | global | `pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y` |
| [claude-cloud](skills/claude-cloud/SKILL.md) | a local agent must drive Claude Code **cloud** sessions headlessly: create, send, wait, read, archive; cloud dry runs and browser fallback (undocumented API experiment) | project repo where local agents drive its cloud sessions | `pnpm dlx skills add pjmuller/skills -s claude-cloud -y` |
| [codexbar-setup](skills/codexbar-setup/SKILL.md) | CodexBar should share native profiles with T3/Codex and keep Claude credentials fresh (macOS) | personal setup repo | `pnpm dlx skills add pjmuller/skills -s codexbar-setup -y` |
| [t3-schedule](skills/t3-schedule/SKILL.md) | a T3 thread should start on a wall clock ("every workday 07:30 run X"); macOS launchd | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-schedule -y` |
| [t3-maintenance](skills/t3-maintenance/SKILL.md) | you orchestrate many worker threads: fleet view, stalled workers, unsent drafts, purge, prompt mining | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-maintenance -y` |
| [t3-find-thread](skills/t3-find-thread/SKILL.md) | "which thread did we discuss X in?"; full-text search over local transcripts, jump to it | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-find-thread -y` |
| [t3-usage-windows](skills/t3-usage-windows/SKILL.md) | you juggle several Claude/Codex accounts: warm five-hour windows, top up during the day, resume rate-limited threads | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-usage-windows -y` |
| [video-shrink-for-gemini](skills/video-shrink-for-gemini/SKILL.md) | a screen recording (or Fathom/Leexi call) must be small enough for Gemini and come with a context-rich prompt | personal setup repo | `pnpm dlx skills add pjmuller/skills -s video-shrink-for-gemini -y` |
| [disk-audit](skills/disk-audit/SKILL.md) | the Mac is filling up; deterministic audit, cleanup only of self-regenerating caches | personal setup repo | `pnpm dlx skills add pjmuller/skills -s disk-audit -y` |
| [resource-audit](skills/resource-audit/SKILL.md) | the Mac is slow or hot; CPU/RAM pressure, process ownership, targeted stopping and recovery | personal setup repo | `pnpm dlx skills add pjmuller/skills -s resource-audit -y` |
| [clickup-core](skills/clickup-core/SKILL.md) | agents in a project repo read/write ClickUp tasks (rich comments, attachments) against that repo's workspace config | project repo | `pnpm dlx skills add pjmuller/skills -s clickup-core -y` + a thin `clickup` skill holding `clickup.toml` |
| [google-workspace-core](skills/google-workspace-core/SKILL.md) | agents need reusable Workspace clients with repository-owned accounts and existing CLI contracts | project repo | `pnpm dlx skills add pjmuller/skills -s google-workspace-core -y` + an account wrapper |

Dependencies: t3-schedule, t3-maintenance and t3-usage-windows need t3-manage-thread's helpers; t3-usage-windows also needs t3-maintenance;
claude-cloud needs t3-manage-thread for profile → Keychain resolution (macOS only).
T3 Code must be running for the T3 skills. Thread helpers work on macOS and Linux/WSL; launchd scheduling and the top-up daemon are macOS-only.

Paste-to-your-agent version:

```
Register the skill <name> from github.com/pjmuller/skills in the repository that owns the work with
`pnpm dlx skills add pjmuller/skills -s <name> -y`; use `-g` only for t3-manage-thread or an explicitly
chosen machine-wide skill. If it ships commands, run scripts/install and scripts/install --check and
fix what --check reports; PATH availability does not change the skill's discovery scope. Then read SKILL.md.
```

## Update

Nothing auto-updates. `pnpm dlx skills update -g` (global) or `pnpm dlx skills update -p` inside the
repo (commit the diff + lockfile), then rerun `scripts/install` and `--check` for updated skills that ship commands.
Installers refuse to replace commands from another checkout; use `--relink` to choose a new canonical copy.
`--check` prints its resolved source directory first.
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
