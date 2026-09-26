# Workspace credential setup

Never grep or print `.env`, `client.json`, `token.json` or an offline-token file. Run
`gws.py --config <wrapper>/workspace.json doctor [--live] [--json]` instead: it reports sources,
paths, redacted client fingerprints and the one command that fixes the first problem
(`scripts/gws_core/doctor.py`). Offline mode: no network, writes, refresh or consent. `--live`
refreshes in memory and verifies the account. Exit 0 only when healthy.

## First machine

Put the desktop OAuth client where `workspace.json` says (`client_env` files, or `client.json` in
`config_dir`; `auth configure --client-env PATH` imports one), then `auth mint` and approve every
scope. Never copy credentials into a repository or worktree.

## Symptoms

Follow the doctor's printed fix (`auth mint [--force]`, `chmod 600`, client source) and don't edit
tokens by hand. Also:

| Situation | Fix |
| --- | --- |
| Worktree lacks the ignored `.env` | Use `config_dir/client.json`; don't copy credentials into the worktree. |
| Variables come from mise or a shell env file | Run through `mise exec --` from the repo root. |
| `invalid_grant` on refresh | Token revoked/expired: the account owner runs `auth mint --force`. |
| Network failure | Retry later; don't re-consent. |
