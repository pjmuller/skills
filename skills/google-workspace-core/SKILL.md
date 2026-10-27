---
name: google-workspace-core
description: "Use for Google Drive, Docs, Sheets, Slides or Gmail work: a pasted Google link, a Doc as Markdown, a Sheet range, a deck edit, searching or exporting old mail, a Gmail draft. Read the repository's Workspace wrapper first; it names the account and scopes."
---

The repository's wrapper owns the account, scopes, credential locations and what may be written or
sent. This core owns config, auth, the commands and their implementations; it has no account
defaults. **Never borrow one account's token for another.**

```sh
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json --help   # or $GWS_CONFIG
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json whoami
```

`--help` needs no credentials. Every account has the same commands (Drive, Docs, Sheets incl.
native Tables, Slides, Gmail, raw `api`); availability is not authorization: a command also needs
the account's scopes, the user's request and the wrapper's policy.

Hard rules:

- **Secrets:** data commands refresh an existing offline token and verify the account; only `auth
  mint` opens browser consent. `auth export-env` prints secrets, `auth export-token` writes the refresh token to an owner-only
  file: provisioning only, never log, paste or commit. Never cat/grep `token.json`, `client.json` or a `.env`; use `doctor`.
- **Writes:** only requested ones; preserve unrelated content; read the result back. Drive deletion
  is trash; `slides-delete` needs `--yes`; Gmail sends are not idempotent. Never send mail or edit a
  document just to prove access.

Gmail output lines to pass on, never filter:

- `Mail-ref: gmail:<thread id> <account>` (draft/send commands): in T3 it claims the mail case for
  the running thread so replies wake it ([mail cases](https://github.com/pjmuller/skills/blob/main/skills/t3-manage-thread/mail-link.md)).
  Never put it in the mail itself.
- `Open: <Gmail link>` (also `gmail-get`/`gmail-thread`): in every report about a mail.
- `Draft: <compose link>` (`gmail-draft`, `-draft-update`, `-draft-get`, `-draft-list`): **every
  report that creates, edits or reads back a draft hands it to the human**; the thread link alone
  costs a second round trip.

A pasted print link (`view=pt&permthid=thread-f:…`) or Mail-ref → `gmail-url <ref>`; `gmail-thread`
takes the same refs. Links you hand out name the account by email, never `/u/<N>/`: [links](references/links.md).

Conventions: compact text, `--json` for the raw payload (machine callers always pass it). Commands
take a Google URL or bare id; slide arguments a 1-based number, objectId or pasted `?slide=id.X` URL
(`slides-resolve` translates). Python callers import the client instead of re-implementing OAuth:
`from gws_core import Workspace, credentials, load_config` ([importable API](references/integration.md#importable-api)).

Open when needed:

- New wrapper, `workspace.json` keys, credential resolution → [integration](references/integration.md)
- Dropping to `*-batch` / `api` (pagination, Calendar); Slides, Docs, Sheets, Drive API gotchas → [rest](references/rest.md)
- Writing or editing a draft (HTML twin, From, `--attach`, signatures, draft vs send), what an access check proves → [drafts](references/drafts.md)
- Gmail link that names no account; the user's mailbox inventory → [accounts](references/accounts.md)
- Finding old mail (`gmail-search` → `gmail-export` → grep), query cheat sheet → [gmail-search](references/gmail-search.md)
- Credential errors, 403, first machine, token lifetime → [troubleshooting](references/troubleshooting.md)
- Google My Maps (no content API) → [mymaps](references/mymaps.md)

Offline tests: `uv run --project <core> pytest <core>/scripts/tests -q`; `scripts/install --check`
verifies dependencies.
