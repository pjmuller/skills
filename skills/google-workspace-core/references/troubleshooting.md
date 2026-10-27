# Workspace credential setup

Never grep or print `.env`, `client.json`, `token.json` or an offline-token file. Run
`gws.py --config <wrapper>/workspace.json doctor [--live] [--json]`: sources, paths, redacted client
fingerprints and the one command that fixes the first problem (`scripts/gws_core/doctor.py`). Offline
by default (no network, writes, refresh or consent); `--live` refreshes in memory and verifies the
account. Exit 0 only when healthy. Follow its printed fix; never edit tokens by hand.

**First machine:** put the desktop OAuth client where `workspace.json` says (`client_env` files, or
`client.json` in `config_dir`; `auth configure --client-env PATH` imports one), then `auth mint` and
approve every scope. Never copy credentials into a repository or worktree.

| Situation | Fix |
| --- | --- |
| Worktree lacks the ignored `.env` | Use `config_dir/client.json`; don't copy credentials into the worktree. |
| Variables come from mise or a shell env file | Run through `mise exec --` from the repo root. |
| `invalid_grant` on refresh | Token revoked/expired ([lifetime](#token-lifetime-and-unverified-apps)): the account owner runs `auth mint --force` (replaces the existing, dead cache). |
| Network failure | Retry later; don't re-consent. |

## Token lifetime and unverified apps

An External OAuth app in **Testing** issues refresh tokens that die after 7 days; publish it (**In
production**) for long-lived ones. In production a refresh token still dies when the user revokes it,
it goes unused for 6 months, the password changes **and** it carries Gmail scopes, or the account
exceeds 100 live tokens per client ([Google](https://developers.google.com/identity/protocols/oauth2#expiration)).
An unverified production app asking sensitive/restricted scopes (Gmail, full Drive) shows a "Google
hasn't verified this app" notice before consent and is capped at 100 new users
([Google](https://support.google.com/cloud/answer/7454865)): fine for a handful of own accounts,
verification needed beyond that. A separate Cloud project is just as unverified.

## API disabled or missing scope?

A 403 alone does not diagnose OAuth: read Google's error reason and project number first.

- `SERVICE_DISABLED`: resolve the reported project number in Cloud Console and confirm it is the
  OAuth client's project (old inventories and similarly named projects mislead). A project admin
  enables the API there; that login may differ from the token's account. Existing tokens, including
  colleagues' env variables on the same client, need no replacement: retry the failed read through
  each affected wrapper.
- Missing scope: update the complete `mint_scopes` in every wrapper sharing that token (`scopes` is
  the minimum), then `auth mint --force`, keeping it running for the localhost callback. Changing the
  Console consent-screen scopes alone grants nothing.
- Console links: `authuser=<URL-encoded-email>`, never numeric (a browser slot; nor does callback `hd`
  prove the email). Verify with `doctor --live` / `whoami` after consent.

After a repair, report API enablement and token minting separately. Record the verified account,
project and credential location in the private wrapper/setup docs, never this public core. Only
environments adopting a newly minted token need their secret store updated (`auth export-env`); API
enablement needs no redistribution. Local success does not verify a colleague's environment
([evidence levels](drafts.md#access-checks)).

References: [enable Workspace APIs](https://developers.google.com/workspace/guides/enable-apis),
[OAuth scopes and offline access](https://developers.google.com/identity/protocols/oauth2/web-server).
