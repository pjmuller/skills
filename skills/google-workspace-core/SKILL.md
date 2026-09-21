---
name: google-workspace-core
description: One Google Workspace CLI and Python client for Drive, Docs, Sheets, Slides and Gmail. Every repository gets the same commands; its wrapper's workspace.json supplies the account, scopes and credential locations. Read that wrapper first for local policy.
---

Read the repository's Google Workspace wrapper first: it owns the account, scopes, credential
locations and the local rules about what may be written or sent. This core owns loading that
configuration, authentication, the command surface and the generic implementations. It contains
no account defaults. Never borrow one account's token for another account.

```sh
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json --help
uv run --script <core>/scripts/gws.py --config <wrapper>/workspace.json whoami
```

`--config` may also come from `$GWS_CONFIG`. `--help` works without credentials or config, and
every account gets the identical command set: Drive, Docs, Sheets (including native Tables),
Slides and Gmail, plus `api` for anything without a dedicated command. Availability is not
authorization: a command still needs the account's scopes, the user's request and the wrapper's
policy. Narrow accounts simply get a permission error.

- Reads and writes refresh an existing offline token and verify the account first; they never
  open browser consent. Only `auth mint` does, explicitly.
- `auth mint [--force] [--port N]` · `auth configure --client-env PATH` (import a desktop client)
  · `auth export-env` and `auth export-token` print secrets for provisioning only: never log,
  paste or commit their output.
- `doctor [--live]` diagnoses credential problems without printing secrets. Never cat or grep
  `token.json`, `client.json` or a `.env`.
- Output is compact text; `--json` (before or after the command) gives the raw API payload.
  Machine callers should always pass `--json`. Commands accept a Google URL or a bare id.
- Only perform requested writes, preserve unrelated content, read the result back. Drive deletion
  is trash; `slides-delete` needs `--yes`; Gmail sending is not idempotent.

Python callers import the same implementations instead of re-implementing OAuth:

```python
sys.path.insert(0, "<core>/scripts")
from gws_core import Workspace, credentials, load_config

config = load_config("<wrapper>/workspace.json")
with Workspace(config) as ws:
    ws.gmail.search("newer_than:1d")   # also ws.drive / ws.docs / ws.sheets / ws.slides
    ws.api("GET", "https://www.googleapis.com/drive/v3/about", params={"fields": "user"})
creds = credentials(config)            # google.oauth2 Credentials for a Google SDK client
```

- [Wrapper configuration and migration](references/integration.md): `workspace.json`, install
  contract, importable API.
- [REST details](references/rest.md): compact reads, batch indexes, Slides/Drive workarounds.
- [Draft preservation and access checks](references/drafts.md): existing drafts, MIME, races.
- [Troubleshooting](references/troubleshooting.md): the doctor and first-machine setup.

Offline tests: `uv run --project <core> pytest <core>/scripts/tests -q`. Live verification uses
identity and bounded reads: never send mail or edit a document just to prove access. Keep account,
refreshability, scopes and resource access separate when reporting.
