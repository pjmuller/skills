---
name: claude-cloud
description: "Use when a local agent must drive Claude Code cloud sessions (claude.ai/code): dry-run a pushed commit in a real cloud session, re-test in a warm one, list/read/export past sessions and their cost, or edit a cloud environment's allowlist/variables. Not local Claude or T3 delegation."
---

# claude-cloud

Lets a local agent verify repo/environment changes in a real Claude Code cloud session without a
human relay. One helper: `scripts/claude-cloud` (uv single-file script; `claude-cloud <cmd> --help`
for defaults, env-var fallbacks, `--since` format, exit codes).

**Experiment**: undocumented API, verified against Claude CLI 2.1.276 (2026-09-18); may break on
any CLI release. Device-attested sessions may refuse unsigned requests: never try to bypass that.

## Install

Register repo-locally only where local agents drive that project's cloud sessions
(`pnpm dlx skills add pjmuller/skills -s claude-cloud -y`), then
`scripts/install --check` (missing → `scripts/install` once per machine). One canonical checkout:
`install` refuses to repoint an existing PATH link (`--relink` overrides). Needs `uv`, `claude`,
macOS `security`, and `t3-limits` from
[t3-manage-thread](https://github.com/pjmuller/skills/blob/main/skills/t3-manage-thread/SKILL.md)
(its `lib/t3_limits.py` owns the profile → Keychain mapping).

## Pick the flow

- Pushed-commit verification (`create --gate SHA`, warm re-test `send --gate NEWER_SHA --branch B`) → [dry-run.md](dry-run.md)
- Past sessions, cost, export → [review.md](review.md)
- Permission prompts, uploads, rendered artifacts, environment edits → [browser-fallback.md](browser-fallback.md)

Per-repo defaults go in `mise.toml` `[env]` (`CLAUDE_CLOUD_*`); stderr prints each resolved choice
and its source. Environments carry no repo default: `create` without a repo has no git source.
Anthropic-hosted environments only.

## Behaviour `--help` does not show

- `create` needs no local checkout, prints ID + URL first; `--wait` then prints the full transcript.
- `wait` polls every 2 s, streams only the latest user turn (rerun replays it). Timeout/Ctrl-C leave cloud work running.
- **Mutations are never retried.** After an uncertain POST (incl. `send` "visibility unconfirmed"),
  inspect `sessions`/`read` before resending.
- Exit 5 "needs interaction" → web UI.
- Cloud startup hooks run before the prompt: read-only wording is not a sandbox; keep cloud instructions in scope.

## Auth and API

Token from the profile's Keychain item, never logged; refreshed only by one official-CLI turn,
never rotated here; still expired → exit 3. Changing the script → [protocol.md](protocol.md).
