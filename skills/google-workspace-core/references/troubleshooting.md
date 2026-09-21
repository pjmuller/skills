# Workspace credential setup

Never grep or print `.env`, `client.json`, `token.json` or an offline-token file. Run the doctor:
it reports paths, checks and redacted client fingerprints.

```sh
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json doctor
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json doctor --live [--json]
```

Offline mode reads configuration and credential metadata only: no network, no writes, no
permission changes, no refresh, no consent. `--live` refreshes in memory and verifies the account
after the offline checks pass. The exit code is 0 only when the configuration is healthy.

## First machine

Place the desktop OAuth client where the wrapper's `workspace.json` says (its `client_env`
variables, or `client.json` in `config_dir`; `auth configure --client-env PATH` imports one from
a local env file). Then run `auth mint` and approve every scope. Never copy credentials into a
repository or a worktree.

## Symptoms

| Doctor result | Fix |
| --- | --- |
| Missing client | Set both named variables from one source, or place `client.json` at the reported path. |
| Client differs from cached token | Run the reported `auth mint --force`; do not edit the token. |
| Missing scopes | Run `auth mint --force` and approve every configured scope. |
| Wrong account (`--live`) | Run `auth mint --force` and choose the expected account. |
| No offline token | Run `auth mint`. |
| Worktree lacks the ignored `.env` | Use `config_dir/client.json`; do not copy credentials into the worktree. |
| Variables come from mise or a shell env file | Run the command through `mise exec --` from the repo root. |
| Refresh rejected: `invalid_grant` | The token was revoked or expired; the account owner runs `auth mint --force`. |
| Network failure | Retry later; do not re-consent. |
