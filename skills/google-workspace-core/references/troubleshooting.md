# Workspace credential setup

Never grep or print `.env`, `client.json`, `token.json`, or offline-token files. Run the doctor; it reports paths, checks, and redacted client fingerprints.

```sh
uv run --script .agents/skills/google-workspace-core/scripts/doctor.py [WRAPPER]
uv run --script .agents/skills/google-workspace-core/scripts/doctor.py [WRAPPER] --live
```

Offline mode reads configuration and credential metadata only. It does not use the network, write files, change permissions, refresh tokens, or open consent. `--live` refreshes only in memory and verifies the account after offline checks pass. Add `--json` for structured output.

## First machine

- REST: put the desktop `client.json` in `config_dir`, then run the wrapper's `gws_auth.py`.
- Modular: set both Workspace client variables in the configured `.env`, or put `client.json` in `config_dir`; run `<wrapper> auth`.
- Read-only: put `client.json` in `config_dir` (or use the wrapper's client import command), then run `<wrapper> auth`.

Wrapper copy-paste block (edit paths only):

```md
First machine: place the desktop client at `~/.config/example-workspace/client.json`.
Run `uv run --script .agents/skills/google-workspace-core/scripts/doctor.py .agents/skills/example-workspace`.
Then run the wrapper's explicit auth command. Never cat or grep credential files.
```

## Symptoms

| Doctor result | Fix |
| --- | --- |
| Missing client | Set both named variables from one source, or place `client.json` at the reported path. |
| Client differs from cached token | Run the reported `auth --force`; do not edit the token. |
| Missing scopes | Run the reported `auth --force` and approve every configured scope. |
| Wrong account (`--live`) | Run `auth --force` and choose the expected account. |
| No offline token | Run the reported explicit auth command. |
| Worktree lacks ignored `.env` | Use the external `config_dir/client.json`; do not copy credentials into the worktree. |
| Variables come from mise or a shell env file | From the repo root, run the doctor via `mise exec --`. |
| Refresh rejected: `invalid_grant` | The token was revoked or expired; the account owner runs the reported `auth --force`. |
| Network failure | Retry later; do not re-consent. |
