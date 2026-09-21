---
name: google-workspace-core
description: Reusable Google Workspace auth, REST commands and Python clients for Drive, Docs, Sheets, Slides and Gmail. Read the repository's account wrapper first for credentials, enabled commands and mutation policy.
---

Use the repository’s Google Workspace wrapper. It selects the account, scopes, credential
locations and compatibility interface; this replaceable core contains no account defaults.
Never borrow a personal token for a team account or copy credentials into this directory.

Wrappers and this committed core work without global skills or sibling checkouts. Python ≥3.11
and uv required. `scripts/install --check` verifies dependencies without Google access; each
wrapper’s PEP 723 header supports direct `uv run --script <wrapper> --help` execution.

## Choose the existing interface

| Wrapper interface | Core implementation | Contract |
| --- | --- | --- |
| `gws.py`, `gws_auth.py` | `scripts/gws.py`, `scripts/gws_auth.py` | Compact REST commands, separate explicit consent; cloud `GWS_*` token env supported |
| `google_workspace.py` / `gmail_cli.py`, imported client modules | `scripts/modular/` | Local argparse surface; preserved Python methods and signatures |
| Read-only `google_workspace.py` | `scripts/readonly.py` | JSON reads, Markdown export, protected local outputs; authenticated client available for authorized custom work |

Use `--help` on the wrapper for its command set. Reads require existing offline credentials;
missing credentials require explicit `auth`/mint, never implicit browser consent. Account checks
precede client use; refreshing preserves extra scopes. Writes require the user’s requested
operation and local policy; a broad token or raw API method is not authorization.

- [REST details](references/rest.md): compact reads, batch indexes, Slides/Drive workarounds.
- [Draft preservation and access checks](references/drafts.md): existing drafts, MIME and races.
- [Integration contract](references/integration.md): configuration, compatibility and verification.
- [Troubleshooting](references/troubleshooting.md): secret-safe doctor and first-machine setup.

For offline tests: `uv run --project <core-dir> pytest <core-dir>/scripts/tests -q`.
Live verification should use identity and bounded reads, never send mail or edit documents just
to prove access. Keep account, refreshability, scopes and resource access separate in reports.
