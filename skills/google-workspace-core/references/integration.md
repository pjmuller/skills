# Wrapper configuration and integration

Install a committed hard copy at `.agents/skills/google-workspace-core` (source recorded in
`skills-lock.json`, exposed to Claude via the relative agent link). Updates replace only the core:
never a wrapper, a `workspace.json` or a credential file.

A wrapper is `SKILL.md` + `workspace.json` (+ its own domain scripts, e.g. a repo-specific sheet
layout built on `sheet-batch` or the importable API). It owns no CLI copy, argparse or auth code.
Docs invoke the core with an explicit `--config`; for a shorter call define a shell function, not
a launcher script. Start from [templates/workspace.json](../templates/workspace.json), provide a
desktop OAuth client outside the repository, run `auth mint`.

## workspace.json

Loader: `scripts/gws_core/config.py` (`KEYS`, `REQUIRED`). Unknown keys are rejected; relative
paths resolve against the config file.

| Key | Meaning |
| --- | --- |
| `account`, `config_dir`, `scopes` (required) | Address every call is verified against; owner-only dir for `token.json` (+ optional `client.json`); scopes the token must carry (superset OK). |
| `mint_scopes` | What `auth mint` requests (default `scopes`). The core never widens consent; a token without `userinfo.email` is identified via the Gmail profile. |
| `client_env` | Env files holding `GOOGLE_WORKSPACE_CLIENT_ID`/`_SECRET`. |
| `legacy_token` / `offline_token_file` | Pre-existing token read in place / refresh-token import file and default `auth export-token` target. |
| `account_env` / `config_dir_env` | The one env variable allowed to override that value. |
| `cloud_token_env` | `true` accepts `GWS_REFRESH_TOKEN`/`GWS_CLIENT_ID`/`GWS_CLIENT_SECRET` from env (all or none). |

Hard rule: env overrides are opt-in per wrapper so a stray variable can never point one account at
another's credentials.

Credential resolution (`scripts/gws_core/auth.py`):

- client: env `GOOGLE_WORKSPACE_CLIENT_ID`/`_SECRET` → each `client_env` file →
  `config_dir/client.json`. Id and secret always come from one source; half a pair is an error.
- token: cloud env triplet (if opted in) → `config_dir/token.json` → `legacy_token` →
  `offline_token_file`. Refreshes always write `config_dir/token.json`.
- A configured client whose id disagrees with the cached token is refused; only an absent client
  is tolerated (the offline token carries its own). Symlinks anywhere in a credential path are
  refused (paths resolve lexically).

## Importable API

`from gws_core import load_config, credentials, Workspace` (`scripts/gws_core/__init__.py`).
Only `config`/`errors` load eagerly, so `credentials` alone skips httpx and the consent stack.
`Workspace` is one authenticated session (`drive`, `docs`, `sheets`, `slides`, `gmail`, `api()`,
`whoami()`); no process-global account state, so two accounts can share a process.
`gws_core.render` prints the CLI's compact tables. Errors are `WorkspaceError` subclasses
(`ConfigError`, `AuthError`, `ApiError.status`), never `SystemExit`.

Consuming scripts declare their own deps (`uv run --script` reads only the running script's
header): `google-auth` + `requests` to authenticate (auth avoids httpx so Google-SDK callers keep
working); `python-dotenv` only with `client_env`; `httpx` for the data session;
`google-auth-oauthlib` only for `auth mint`.

## Migration notes

Command names are unified across accounts; older per-repo spellings (`me`, `sheet-get`,
`gmail-create-draft`, `gws_auth.py`, …) no longer exist. Map an old call via `gws.py --help`.
