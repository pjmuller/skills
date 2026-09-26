---
name: claude-cloud
description: Drive Claude Code cloud sessions headlessly from a local agent (discover environments, create, send, wait, read, archive, export). Use to verify a pushed commit in a real cloud session (dry run), review past sessions, or fall back to the browser for interactive work and environment edits. Personal-account experiment over an undocumented API; no native T3 integration.
---

# claude-cloud

Lets a local agent verify repo/environment changes in a real Claude Code cloud session without a
human relay. One helper: `scripts/claude-cloud` (uv single-file script; `claude-cloud <cmd> --help`).

**Experiment.** Personal-account use of an undocumented API, verified against Claude CLI
**2.1.276, 2026-09-18**; it may break on any CLI release. Not an approved public SDK.
Device-attested sessions may refuse unsigned requests; do not attempt to bypass that.

## Install

```sh
pnpm dlx skills add pjmuller/skills -s claude-cloud -y
.agents/skills/claude-cloud/scripts/install --check   # missing command → run install once per machine
```

Register repo-locally only where local agents drive that project's cloud sessions. The command is
machine-wide: `install` refuses to repoint an existing PATH link to another checkout (`--relink`
overrides), so keep one canonical copy. `--check` verifies the dependencies: `uv`, the official
`claude` CLI (token refresh), macOS `security`, and `t3-limits` from
[t3-manage-thread](https://github.com/pjmuller/skills/blob/main/skills/t3-manage-thread/SKILL.md),
whose `lib/t3_limits.py` owns the profile → Keychain mapping.

## Usage

Pick the flow: pushed-commit verification → [dry-run.md](dry-run.md) (`create --gate SHA`, warm
re-test via `send --gate NEWER_SHA --branch B`); past sessions, cost, export → [review.md](review.md);
permission prompts, uploads, rendered artifacts, environment edits → [browser-fallback.md](browser-fallback.md).

Defaults; stderr prints each resolved choice and its source:
- Profile: `--profile` (case-insensitive substring of a T3 Claude instance id or display name, same
  rule as `t3-spawn-thread --profile`) → `CLAUDE_CLOUD_PROFILE` → `CLAUDE_CONFIG_DIR` → the only
  T3 Claude profile; ambiguity → exit 2 listing candidates.
- `create`: `--env`/`CLAUDE_CLOUD_ENV` (exact name or ID) → the only environment; `--repo`/`CLAUDE_CLOUD_REPO`
  → none (environments carry no repo default, so the session starts without a git source);
  `--branch`/`CLAUDE_CLOUD_BRANCH` → `main`. Put per-repo defaults in `mise.toml` `[env]`.
  Anthropic-hosted environments only.

Behaviour `--help` does not show:
- `create` needs no local checkout, prints ID + URL first; `--wait` then prints the full transcript.
- `wait` polls every 2s and streams only the latest user turn; rerunning replays it. Timeout/Ctrl-C
  leave cloud work running.
- Mutations are never retried. After an uncertain POST (incl. `send` "visibility unconfirmed"),
  inspect `sessions`/`read` before resending.
- Interaction requests (exit 5 "needs interaction") require the web UI.
- Cloud startup hooks run before the prompt: read-only wording is not a sandbox, keep cloud
  instructions in scope.

Exit: 0 success; 1 transport/schema/API error; 2 arguments/profile/environment ambiguity; 3 auth;
4 missing session; 5 failed/archived/interaction-required turn; 124 timeout; 130 interrupted.

## Auth

Reads the macOS Keychain item for the profile's config dir (`Claude Code-credentials[-hash]`),
falling back to its `.credentials.json`; uses `claudeAiOauth.accessToken`, never logs it. Within
10 minutes of expiry it runs one official-CLI Haiku turn for that profile and rereads; still
expired → exit 3. The helper never rotates refresh tokens itself.

## API surface

Endpoints, headers and bodies: `scripts/claude-cloud` (`API`, `main`). Gotchas observed in the CLI
that the code cannot explain:
- `/v1/code/*` needs no `anthropic-beta` header; `/v1/environment_providers` additionally needs
  `x-organization-uuid` from the profile's `.claude.json`.
- Event payloads carry a different internal worker session UUID: keep the outer `cse_…` ID for requests.
- `config:auto-create-pr:off` is server-stamped (400 if supplied).
- There is no environment-edit endpoint ([browser-fallback.md](browser-fallback.md#editing-a-cloud-environment-allowlist-variables)).
- SSE, `/auth/refresh`, `/mark_read`, `/bridge`, `/triggers` exist in the CLI but are unused/unverified here.
