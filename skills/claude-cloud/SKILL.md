---
name: claude-cloud
description: Drive Claude Code cloud sessions headlessly from a local agent (discover environments, create, send, wait, read, archive). Personal-account experiment over an undocumented API; no native T3 integration.
---

# claude-cloud

Run cloud Claude Code sessions from a local coding agent: create a session in a cloud
environment, send turns, wait for completion, read the transcript, archive. Useful when a
local agent must verify repo/environment changes in a real cloud session without a human relay.

**Experiment.** Personal-account use of an undocumented API, verified against Claude CLI
**2.1.276, 2026-09-18**; it may break on any CLI release. Not an approved public SDK.
Device-attested sessions may refuse unsigned requests; do not attempt to bypass that.

## Install

```sh
pnpm dlx skills add pjmuller/skills -s claude-cloud -g -y
<skill dir>/scripts/install && <skill dir>/scripts/install --check
```

Needs [t3-manage-thread](../t3-manage-thread/SKILL.md) installed: `--profile` resolution and the
Keychain service name come from its `t3-limits` lib. Add or inspect Claude profiles with
[T3 setup](../../setup/t3-setup/SKILL.md). Also needs `uv` and macOS `security`.

## Usage

`--profile NAME` = case-insensitive substring of a T3 Claude provider instance id or display
name (same rule as `t3-spawn-thread --profile`); ambiguous or unknown → exit 2 listing candidates.
Omitted: `$CLAUDE_CONFIG_DIR` if set, else T3's default Claude profile (`~/.claude`).

```sh
claude-cloud --profile <profile> envs
claude-cloud --profile <profile> sessions
claude-cloud --profile <profile> create --env '<env name>' --repo owner/repo --branch main 'List top-level directories; no changes, commits, pushes or PRs.'
claude-cloud wait cse_ID --timeout 1800
claude-cloud read cse_ID
claude-cloud send cse_ID 'reply with the single word pong'
claude-cloud archive cse_ID
```

`create` prints ID + URL and needs no local checkout; environment records carry no repo default,
so without `--repo` the session starts with no git source. `sessions` lists the latest 20.
`wait` polls every 2s, prints assistant messages/tool names for the latest user turn and exits on
its result/end-turn; repeated waits replay that turn. `send` confirms its UUID is readable (up to
10s). `read` renders the whole transcript, skipping thinking, tool output and lifecycle noise.
No local state or credential writes. Timeout/Ctrl-C leave cloud work running; interaction
requests require the web UI. Cloud startup hooks run before the prompt — read-only wording is not
a sandbox, keep cloud instructions in scope.

Exit: 0 success; 1 transport/schema/API error; 2 arguments/profile/environment ambiguity; 3 auth;
4 missing session; 5 failed/archived/interaction-required turn; 124 timeout; 130 interrupted.
Mutations are never retried: after an uncertain POST, inspect `sessions`/`read` before resending.

## Auth

Reads the macOS Keychain item for the profile's config dir (`Claude Code-credentials[-hash]`,
hashed by t3-manage-thread's `keychain_service`), falling back to the profile's
`.credentials.json`; uses `claudeAiOauth.accessToken`, never logs it. No refresh-token rotation
here: an expired or denied token needs a login/turn with the official CLI for that profile.

## API surface

Base `https://api.anthropic.com`; headers `Authorization: Bearer …`, `Content-Type: application/json`,
`anthropic-version: 2023-06-01`, `anthropic-client-platform: claude_code_cli`. **No beta header needed.**

| Method / endpoint | Shape / purpose |
|---|---|
| GET `/v1/environment_providers` | Add `x-organization-uuid` from the profile's `.claude.json`; response `environments[]` with `environment_id,name,kind,state`. |
| GET `/v1/code/sessions?limit=20` | Recent `data[]`; `status` + `worker_status`. |
| POST `/v1/code/sessions` | `{title,environment_id,events:[{payload:USER}],config:{sources:[{type:"git_repository",url,revision}],outcomes:[]}}` → `session.id`. |
| GET `/v1/code/sessions/{id}` | `session` (CLI also accepts `response_shape`); lifecycle + worker state. |
| POST `/v1/code/sessions/{id}/events` | `{events:[{payload:USER}]}`; accepted asynchronously. |
| GET `/v1/code/sessions/{id}/events?sort_order=asc&cursor=N` (or `sort_order=desc&limit=1`) | `data[]` envelopes with `sequence_num,payload`; paginate `next_cursor`, resume from last sequence; descending read anchors sends. |
| POST `/v1/code/sessions/{id}/archive` | `{}`; 409 accepted only after metadata confirms archived. |

`USER = {uuid,session_id,type:"user",parent_tool_use_id:null,message:{role:"user",content:"…"}}`;
`session_id` is empty on create. Event payloads carry a different internal worker session UUID:
keep the outer `cse_…` ID for requests. `config:auto-create-pr:off` is server-stamped (400 if
supplied). SSE, `/auth/refresh`, `/mark_read`, `/bridge`, `/triggers` exist in the CLI but are
unused/unverified here.
