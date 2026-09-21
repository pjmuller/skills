# Integration contract

Install a committed hard copy at `.agents/skills/google-workspace-core`, record its source in
`skills-lock.json`, and expose the same files to Claude through a relative agent link. Keep
account configuration, policies and domain helpers in a separate local wrapper. Updates replace
only the core; they must not replace wrappers or credential files.

Wrappers execute the selected core module in their original namespace with `WORKSPACE_CONFIG`.
This preserves importable names, private helper callers and monkeypatching without registering
business accounts in a process-global module cache. The core source path appears in tracebacks;
`__file__` remains the wrapper path for legacy local configuration. Use explicit repository-relative
paths, never a home skill directory, another checkout or account-discovery fallback.

For a new REST wrapper, copy the three files in [templates](../templates/) into a sibling
`google-workspace/scripts/` directory. Edit `workspace_config.py`, provide your own desktop
client outside the repository, then use `gws_auth.py`. Choose scopes for the intended workflow.

Configuration is a plain Python dict owned by the wrapper:

- All auth facades: `expected_email`, `config_dir`; credentials are external, account-specific.
- REST: `required_scopes`, `mint_scopes`, `features` (`gmail`, `upload`, `images`). `GWS_CONFIG_DIR`
  and `GWS_EXPECTED_EMAIL` preserve explicit overrides; cloud needs all three `GWS_REFRESH_TOKEN`,
  `GWS_CLIENT_ID`, `GWS_CLIENT_SECRET`. Mint uses `client.json` beside `token.json`.
- Read-only: `scopes`; `configure --client-env` imports a desktop client, explicit `auth` consents.
- Modular: `scopes`, local client-env and legacy-cache settings documented by `modular/auth.py`.
  Client resolution is environment, one wrapper/repo `.env`, then external `config_dir/client.json`;
  an ID and secret always come from the same source.
  Legacy caches are read in place; successful refresh writes only the configured external cache.
  Offline-file import/export is retained where the wrapper enables it. No account substitution.

The rich Gmail interface keeps fourth positional `create_draft` argument as CC; the draft-CRUD
interface keeps it as reply-message ID. Likewise path-first and name-first Drive upload interfaces
are distinct. Do not silently merge these signatures. Local CLIs own aliases and domain commands.
Gmail sending is non-idempotent; a timeout is not permission to retry blindly.

## Migration checks

Characterize existing CLI options and imports before replacing a wrapper. Compare mock request
payloads and output shapes for reads, drafts, uploads and Sheets operations. Test rejected consent,
wrong account/client/scope, missing cache, and output/symlink protections without real tokens.
Preserve auth extras used by analytics and local MFA callers. Credential hardening intentionally
removes implicit consent and refuses wrong-account caches. `slides-move` uses pre-move insertion
indexes so `--to N` means final position N.

A scripts-free skill documenting application SDK clients need not install this runtime. Keep one
owned auth path and record that exception in the consumer registry; account/scopes and app methods
still need review during a migration.

Use the [secret-safe doctor and setup guide](troubleshooting.md) instead of inspecting credential
files or broadly grepping environment files.
