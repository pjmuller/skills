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

## API disabled or missing scope?

A 403 alone does not diagnose OAuth. Read Google's error reason and project number first.

- `SERVICE_DISABLED`: resolve the reported project number in Cloud Console and confirm the
  OAuth client's project. Old inventories and similarly named projects can be wrong. Enable the
  named API there as a project administrator; that login may differ from the token's account.
  Existing tokens with sufficient scopes need no replacement, including colleagues' environment
  variables using that same client/project. Retry the failed read through each affected wrapper.
- Missing scope: update the complete `mint_scopes` grant in every wrapper sharing that token
  (`scopes` is the required minimum), then `auth mint --force`. Keep its process running for the
  localhost callback. Updating the Console consent-screen scopes alone does not grant access.
- Console login: use `authuser=<URL-encoded-email>` in links and verify the selected account.
  Numeric `authuser` values are browser account positions; neither they nor callback `hd` prove
  the authorized email. Verify with `doctor --live` / `whoami` after consent.

After a repair, report API enablement and token minting separately. Record the verified account,
project and credential location in the private wrapper/setup docs, never this public core.
Only environments adopting a newly minted token need their matching secret store updated via
`auth export-env`; API enablement alone requires no redistribution. Local success does not verify
a colleague's environment. Follow [access-check evidence levels](drafts.md#access-checks).

References: [enable Workspace APIs](https://developers.google.com/workspace/guides/enable-apis),
[OAuth scopes and offline access](https://developers.google.com/identity/protocols/oauth2/web-server).
