---
name: google-workspace-core
description: Use when an agent reads or writes Google Drive, Docs, Sheets, Slides or Gmail (search, export, drafts) through the shared CLI or Python client. Read the repository's Workspace wrapper first; its workspace.json supplies the account, scopes and credential locations.
---

Split: the repository's wrapper owns the account, scopes, credential locations and what may be
written or sent. This core owns config loading, auth, the command surface and generic
implementations; it has no account defaults. Never borrow one account's token for another.

```sh
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json --help   # also $GWS_CONFIG
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json whoami
```

`--help` needs no credentials. Every account gets the same commands (Drive, Docs, Sheets incl.
native Tables, Slides, Gmail, plus raw `api`); availability is not authorization. A command still
needs the account's scopes, the user's request and the wrapper's policy.

Hard rules:

- Data commands refresh an existing offline token and verify the account; only `auth mint` opens
  browser consent. `auth export-env` / `auth export-token` print secrets: provisioning only, never
  log, paste or commit. Never cat/grep `token.json`, `client.json` or a `.env`; use `doctor`.
- Only requested writes; preserve unrelated content; read the result back. Drive deletion is
  trash; `slides-delete` needs `--yes`; Gmail sends are not idempotent. Never send mail or edit a
  document just to prove access.

Gmail draft/send commands print `Mail-ref: gmail:<thread id> <account>` on their own line: in T3
that claims the mail case for the running thread, so replies wake it ([mail cases](../t3-manage-thread/mail-link.md)).
Don't filter that line away; never put it in the mail itself.
They, plus `gmail-get`/`gmail-thread`, also print `Open: <normal Gmail link>`: put it in every
report about a mail so the human can click straight to the thread. A pasted print link
(`view=pt&permthid=thread-f:…`) or Mail-ref → `gmail-url <ref>` gives that link; `gmail-thread`
accepts the same refs. Link shape `mail/?authuser=<account>#all/<hex id>` (`/mail/u/<email>/` 404s).

Conventions: compact text output, `--json` for the raw payload (machine callers always pass it).
Commands take a Google URL or bare id. Slide arguments take a 1-based number, an objectId or a
pasted `?slide=id.X` URL (which alone names deck and slide); `slides-resolve` translates.

Python callers import the same client instead of re-implementing OAuth:
`from gws_core import Workspace, credentials, load_config` (usage in `scripts/gws_core/__init__.py`;
contract in [integration](references/integration.md#importable-api)).

- [Wrapper configuration and migration](references/integration.md): `workspace.json`, install
  contract, credential resolution, importable API.
- [REST details](references/rest.md): read order, Slides/Docs/Sheets/Drive API gotchas.
- [Drafts and access checks](references/drafts.md): plain-text vs HTML composition, `--attach`
  files (invoice PDFs), editing existing drafts, what an access check proves.
- [Finding mail](references/gmail-search.md): `gmail-search` → `gmail-export` → local `grep`;
  query cheat sheet.
- [Troubleshooting](references/troubleshooting.md): `doctor`, first-machine setup.

Offline tests: `uv run --project <core> pytest <core>/scripts/tests -q`. `scripts/install --check`
verifies dependencies.
