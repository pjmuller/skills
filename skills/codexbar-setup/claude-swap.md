# Legacy: Claude quota through claude-swap + `codexbar-profiles` sync

Only for machines still on real claude-swap (`/login` tokens, no t3-limits stand-in;
[install.md](install.md#claude-quota-from-t3-limits) is the recommended path). Verified with
claude-swap 0.26.0. Reassess when claude-swap fixes isolated-home publication
([write-side #206](https://github.com/realiti4/claude-swap/issues/206),
[read-side #217](https://github.com/realiti4/claude-swap/issues/217)); a capture fix alone doesn't
prove inactive refreshes update the live home.

## Register logins without switching the default

```bash
uv tool install claude-swap          # or: uv tool upgrade claude-swap (≥0.26.0 reads hashed isolated Keychain items)
env -u CLAUDE_CONFIG_DIR -u CLAUDE_SECURESTORAGE_CONFIG_DIR cswap add
env -u CLAUDE_SECURESTORAGE_CONFIG_DIR CLAUDE_CONFIG_DIR="$HOME/.claude_work_home" cswap add
cswap list --json | jq '{accounts: [.accounts[] | {number,email,usageStatus}], warnings: (.duplicateAccountWarnings // [])}'
```

Confirm each slot's email against that home's `claude auth status --json` and `.claude.json`
identity (incl. organization/subscription). Never assume a slot number; never `cswap switch`,
automatic switching, or CodexBar's Switch/Re-authenticate for shared accounts. Enable Claude Swap in
CodexBar with the absolute path from `command -v cswap`.

## Keep credentials fresh (`codexbar-profiles`)

`cswap list` can refresh OAuth tokens (not a read-only inventory): a refresh can leave an isolated
T3 home with an older token, or a CLI refresh can leave cswap stale. `codexbar-profiles sync` copies
the credential with the later access expiry in **either** direction. Heuristic, not a transaction:
the 60 s watcher reduces the race with Claude/cswap, can't remove it. It never refreshes tokens.

`~/.config/codexbar-profiles.json` (private, verified mappings, never tokens):

```json
{"profiles": [
  {"name": "personal", "home": null},
  {"name": "work", "home": "~/.claude_work_home", "slot": 2, "email": "person@example.org"}
]}
```

`home: null` = the unsuffixed default Keychain item. Omit `slot` for expiry-only monitoring;
optional `keychain_account` overrides the macOS username. Refusal cases (identity mismatch,
unreadable item, concurrent change, equal expiry with different tokens, cswap fallback file,
oversized credential) live in `scripts/codexbar-profiles`; a missing item or expired refresh token
needs browser login.

Sequence: `check` → `expiry` → `sync` (preview; inspect every direction) → `sync --apply` →
`install-jobs`. Before `install-jobs`, inventory `~/Library/LaunchAgents/*keychain-sync*` and
`*token-expiry*`; unload old watchers by exact label first, keep their files for rollback: **two
sync implementations on the same mappings fight**. Jobs `com.t3-skills.codexbar-profiles.{sync,expiry}`
(every 60 s / 09:05 daily), logs `~/Library/Logs/<label>.{log,err}` (no tokens; aligned syncs are
silent); check logs after wake. Rerun `install-jobs` after a skill update (absolute paths).

Expiry alerts fire below five days or when expiry is unknown (missing metadata = unknown, not
expired). Observed ~30-day absolute refresh-token expiry: read `refreshTokenExpiresAt`, never assume
activity extends it.

**Re-login / account change**: `codexbar-profiles remove-jobs` **first**, else the watcher restores
the login you just removed. Clear inherited API key/token variables, re-login the affected home in
the correct browser account, verify organization/plan, repeat `cswap add` under that home, recheck
sync and both apps, then `install-jobs`.

A cswap fallback `.enc` under `~/.claude-swap-backup/credentials` takes precedence over Keychain;
the helper refuses that mapping until reconciled through cswap. **Never delete it blindly.**
Keychain writes go over stdin (never argv); credentials beyond the `security -i` line limit (large
default-home MCP stores) are refused: reconcile via native login/cswap.

## Verify, roll back

- `codexbar-profiles check` / `expiry`: correct mapping and expiry, no secrets.
- `cswap list --json`: distinct correct accounts, no duplicate warnings (may rotate tokens: check before/after sync).
- `launchctl print gui/$(id -u)/com.t3-skills.codexbar-profiles.sync`, then `launchctl kickstart`
  it; inspect last exit/log. Don't force a token rotation to test the watcher.
- `remove-jobs` unloads only these two jobs; credentials/config remain. Restore legacy jobs only
  after the replacement stops.
