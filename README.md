# Agent skills

Self-contained skills for Claude Code, Codex and other agents. MIT licensed.

## T3 Code orchestration

| Skill | Purpose |
| --- | --- |
| [t3-manage-thread](skills/t3-manage-thread/SKILL.md) | Spawn, ping, read, hide, rename, settle/delete threads; provider limits |
| [t3-schedule](skills/t3-schedule/SKILL.md) | macOS launchd recurring jobs; requires thread helpers |
| [t3-maintenance](skills/t3-maintenance/SKILL.md) | Fleet, drafts, prompt mining and purge; requires thread helpers |
| [t3-find-thread](skills/t3-find-thread/SKILL.md) | Local transcript search and opening a match |
| [t3-usage-windows](skills/t3-usage-windows/SKILL.md) | Start windows, chain daytime top-ups, recover limited threads; requires thread helpers and maintenance |

## Misc

| Skill | Purpose |
| --- | --- |
| [video-shrink-for-gemini](skills/video-shrink-for-gemini/SKILL.md) | Smaller recordings + transcript, visual-first or mixed prompt |
| [disk-audit](skills/disk-audit/SKILL.md) | macOS disk measurements and separately authorized cache cleanup |

## Install

T3 must be running. Thread helpers support macOS and Linux/WSL; launchd scheduling
and the usage-window top-up daemon are macOS-only. See each skill's dependency checks.
Put `~/.local/bin` on the login-shell PATH.

Before global installation, merge existing skills into your personal setup repo's
`ai/skills/`, then make `~/.agents/skills`, `~/.claude/skills`, and every isolated
Claude home's `skills` symlink to that **one directory**. Preserve originals first.
`skills add -g` writes to the active `CLAUDE_CONFIG_DIR/skills` and `~/.agents/skills`;
it does not update other Claude homes automatically.

```sh
pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y
~/.agents/skills/t3-manage-thread/scripts/install
~/.agents/skills/t3-manage-thread/scripts/install --check
# From the project/setup repository:
pnpm dlx skills add pjmuller/skills -s t3-schedule -y
.agents/skills/t3-schedule/scripts/install
.agents/skills/t3-schedule/scripts/install --check
```

Replace the skill name for other installs; run each command-shipping skill's
`scripts/install` and `--check`. Install dependencies first. Usage windows uses
`t3-maintenance` for read-only store access and draft protection.
Select named skills: `setup/t3-setup` is a one-time bootstrap, never an installed skill.

Verified with skills CLI **1.5.24 on 2026-09-09**: project installs create
`.agents/skills/<name>`, a Claude link, and `skills-lock.json`. An existing committed
`.claude/skills -> ../.agents/skills` directory symlink **works**: preserved along
with an unrelated sentinel skill, with the new skill visible through both paths.
Commit the skill files, lockfile and Claude link so worktrees inherit them.

## Update

```sh
pnpm dlx skills update t3-manage-thread -g
pnpm dlx skills update t3-schedule -p
```

Then rerun each updated skill's `scripts/install` and `scripts/install --check`.
Updates wipe and replace installed files; keep personal customizations outside them.
For scheduler updates run `t3-schedule refresh`; for an enabled top-up daemon rerun
`t3-usage-windows topup install`. These migrate the old personal launchd labels to
`com.t3-skills.*`; scheduler specs, prompts and daily markers stay in
`~/.t3/userdata/scheduled/t3-schedule/`. Check `launchctl list` for duplicates.
The hide keeper already uses neutral `t3-hide.*` labels. Existing one-shot limited
resume jobs should finish before updating; new ones use `com.t3-skills.t3-usage-windows.limited.*`.

## One-time machine setup

Give your agent the permanent bootstrap URL:
https://raw.githubusercontent.com/pjmuller/skills/main/setup/t3-setup/SKILL.md

Supply desired accounts, scopes and optional prompt base. It detects and merges
existing setup, unifies Claude homes, installs helpers and verifies a launchd smoke job.
[Bootstrap instructions](setup/t3-setup/SKILL.md) resolve supporting links from main
and record the source commit in the consumer's SETUP.md and feedback block.
Tool-free fallback: clone this repository and read `setup/t3-setup/SKILL.md` locally.
Plugin marketplace packaging and submodules are deferred.

The merged skill replaces `t3-hello-world` and `t3-resume-limited`. Update
`t3-maintenance` too (draft discovery now uses the merged CLI), run both installers,
then `t3-usage-windows topup install` to unload the old top-up label before loading
`com.t3-skills.t3-usage-windows.topup`. `t3-limited` remains a compatibility alias.
