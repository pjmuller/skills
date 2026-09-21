# Wrapper configuration and integration

Install a committed hard copy at `.agents/skills/google-workspace-core`, record its source in
`skills-lock.json`, and expose the same files to Claude through a relative agent link. Updates
replace only the core: never a wrapper, a `workspace.json` or a credential file.

A wrapper is `SKILL.md` + `workspace.json` (+ its own domain scripts). It owns no copy of the
CLI, no argparse and no auth code. Docs invoke the core with an explicit `--config`; a repository
that wants a shorter call defines a shell function, not a launcher script:

```sh
GWS() { uv run --script .agents/skills/google-workspace-core/scripts/gws.py \
  --config .agents/skills/google-workspace/workspace.json "$@"; }
```

## workspace.json

| Key | Meaning |
| --- | --- |
| `account` (required) | The Google address every call is verified against. |
| `config_dir` (required) | Owner-only directory holding `token.json` and optionally `client.json`. |
| `scopes` (required) | Scopes the existing token must carry; a superset is accepted. |
| `mint_scopes` | Exactly what `auth mint` requests (default: `scopes`). The core never widens a consent screen; a token without `userinfo.email` is identified through the Gmail profile. |
| `client_env` | Files searched for `GOOGLE_WORKSPACE_CLIENT_ID`/`_SECRET`, relative to this file. |
| `legacy_token` | Pre-existing token cache, read in place; a refresh writes to `config_dir`. |
| `offline_token_file` | Refresh-token file used to import, and the default target of `auth export-token`. |
| `account_env` / `config_dir_env` | Names the one env variable allowed to override that value. |
| `cloud_token_env` | `true` lets this wrapper take `GWS_REFRESH_TOKEN`/`GWS_CLIENT_ID`/`GWS_CLIENT_SECRET` from the environment (all three or none). |

Unknown keys are rejected. Relative paths resolve against the config file. Environment overrides
are opt-in per wrapper, so a stray variable can never point one account at another's credentials.
Copy [templates/workspace.json](../templates/workspace.json) to start a new wrapper, then provide
a desktop OAuth client outside the repository and run `auth mint`.

Credential resolution, in order:

- client: `GOOGLE_WORKSPACE_CLIENT_ID`/`_SECRET` in the environment → each `client_env` file →
  `config_dir/client.json`. An id and secret always come from the same source; half a pair is an
  error, never a silent mix.
- token: cloud environment triplet (when opted in) → `config_dir/token.json` → `legacy_token`
  (read-only) → `offline_token_file`. A refresh always writes back to `config_dir/token.json`.

A configured client whose id disagrees with the cached token is refused, not warned about; only
a completely absent client is tolerated, because an existing offline token carries its own.
Paths are resolved lexically, so a symlink anywhere in a credential path is still refused.

## Importable API

`from gws_core import load_config, credentials, Workspace` — `gws_core` imports only stdlib at
module level, so a caller that needs `credentials` alone does not load the CLI or the consent
stack. `Workspace` holds one authenticated session and exposes `drive`, `docs`, `sheets`,
`slides`, `gmail`, `api()`, `token` and `whoami()`; there is no process-global account state, so
two accounts can be used in one process. `gws_core.render` (`table`, `trunc`, `out`) is available
for tools that print the same compact tables. Errors are `WorkspaceError` subclasses
(`ConfigError`, `AuthError`, `ApiError` with `.status`), not `SystemExit`.

Consuming scripts declare their own dependencies; `uv run --script` only resolves the header of
the script it runs. Authenticating needs `google-auth` and `requests` (the auth layer deliberately
avoids httpx so a Google-SDK caller keeps working); `python-dotenv` only when the config lists
`client_env` files; `httpx` only for the data session; `google-auth-oauthlib` only for `auth mint`.

## Migration notes

Command names are unified across every account, so older per-repo spellings were renamed:
`me`→`whoami`, `sheet-get`→`sheet-read`, `sheet-update`→`sheet-write`,
`sheet-batch-update`→`sheet-batch-write`, `sheet-format-default-rows`→`sheet-format-rows`,
`gmail-create-draft`→`gmail-draft`, `gmail-list/get/send/delete-draft`→`gmail-draft-*`,
`gmail-modify-labels`→`gmail-label`, `gmail-download-files`→`gmail-attachments`,
`drive-update-content`→`drive-replace`, `gws_auth.py`→`auth mint`,
`gws_auth.py export`→`auth export-env`, `export-offline-token`→`auth export-token`,
`configure`→`auth configure`. `drive-upload` is path-first everywhere. Mail bodies are `--body
TEXT` or `--body-file PATH`; `--html` marks that body as HTML and derives the plain-text
alternative, while `--html-file PATH` keeps the authored plain body and attaches that HTML.
Replies quote the original and require a matching subject (an added `Re:` is fine) so Gmail
threads them. Domain-specific formatting (for example a reminder-preview sheet layout) stays in
the owning repository and uses `sheet-batch` or the importable API.
