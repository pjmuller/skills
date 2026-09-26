# Install CodexBar alongside T3 Code

Recipe from a working machine (2026-09-18: CodexBar 0.60.4, claude-swap 0.26.0, isolated
Claude homes). Check installed versions before adapting; upstream behavior changes.

## Install and share profiles

```bash
brew install --cask codexbar
uv tool install claude-swap          # or: uv tool upgrade claude-swap
# from the personal setup repository:
pnpm dlx skills add pjmuller/skills -s codexbar-setup -y
.agents/skills/codexbar-setup/scripts/install && .agents/skills/codexbar-setup/scripts/install --check
open -a CodexBar
```

CodexBar preferences on the working machine: launch at login, refresh every five minutes,
refresh all providers on menu open. Avoid restart loops or aggressive polling; verify the
displayed timestamp advances after a manual refresh.

**Codex:** T3 and the terminal must use the same intended Codex home (default `~/.codex`);
inspect T3's provider configuration and existing `CODEX_HOME` before changing anything. In
CodexBar enable Codex with Auto/OAuth; use the CLI source only to diagnose. Do not copy
`auth.json` into parallel stores or apply the Claude Keychain helper to it. For several
existing homes, add them to `providers[].codexProfileHomePaths` on the `id: codex` entry in
`~/.codexbar/config.json` (merge, don't replace; only if the installed version supports it).
Each path is the home T3 uses, not a new login; CodexBar-managed accounts are separate homes,
not T3 sharing. Verify account **and workspace** match in all three clients. Renewal belongs
to Codex: `codex login` with the affected `CODEX_HOME`. Leave external OAuth sources and
browser extras off unless needed.
[Upstream Codex notes](https://github.com/steipete/CodexBar/blob/main/docs/codex.md).

**Claude:** one authenticated home per T3 provider. Default has no `CLAUDE_CONFIG_DIR`;
isolated providers use T3 `config.homePath`, not environment rows. A provider with empty
`config.homePath` uses the default login whatever its display name or model, so default-account
switches are harmless only once every used Claude provider has an isolated home. Share
prompts/skills through symlinks, never credentials. For isolated CLI commands export the exact
absolute home string used at login (don't resolve symlinks differently): that string
determines the Keychain service hash. Leave `CLAUDE_SECURESTORAGE_CONFIG_DIR` unset; custom
secure-store overrides would need their own mapping support.

Register existing logins in cswap without switching the default:

```bash
env -u CLAUDE_CONFIG_DIR -u CLAUDE_SECURESTORAGE_CONFIG_DIR cswap add
env -u CLAUDE_SECURESTORAGE_CONFIG_DIR CLAUDE_CONFIG_DIR="$HOME/.claude_work_home" cswap add
cswap list --json | jq '{accounts: [.accounts[] | {number,email,usageStatus}], warnings: (.duplicateAccountWarnings // [])}'
```

Confirm each slot's email against that home's `claude auth status --json` and `.claude.json`
identity, including organization/subscription. cswap ≥0.26.0 captures from the hashed isolated
Keychain service; older versions needed staging default credentials, so upgrade instead.
Never assume a slot number; don't use `cswap switch`, automatic switching, or CodexBar's
Switch/Re-authenticate for these shared accounts. Enable Claude Swap in CodexBar with the
absolute path from `command -v cswap`.
[Upstream Claude notes](https://github.com/steipete/CodexBar/blob/main/docs/claude.md).

**Antigravity (Gemini):** needs CodexBar 0.60.2+ and a signed-in `agy`
(`brew install --cask antigravity-cli`, run `agy` once; Antigravity.app not needed). `agy`
1.2.2+ rejects CodexBar's local HTTPS probe, so CodexBar runs `agy -p /usage` instead; older
CodexBar shows "Offline". Enable with `codexbar config enable --provider antigravity`, verify
with `codexbar usage --provider antigravity`. Shows only the two weekly pools (Gemini,
Claude/GPT) for whichever Google account `agy` uses: no account email, no five-hour bucket.
Each refresh writes an `agy` log under `~/.gemini/antigravity-cli/log/`.
[Upstream Antigravity notes](https://github.com/steipete/CodexBar/blob/main/docs/antigravity.md).

Diagnose only the provider you are working on: `codexbar usage --provider claude` or
`--status` from a shell runs the Claude probe under the CLI helper and can raise
Keychain/login prompts in the app.

**Quota-only Claude view:** Settings → Menu → Multi-account layout → **Stacked** (global;
Overview and menu-bar metric choices are separate). Since
[0.57.0 / #3498](https://github.com/steipete/CodexBar/pull/3498) Claude Swap honors the default
Segmented layout, whose inactive-account chips **activate credentials**, not just inspect quota.
Avoid them, Switch Account and Re-authenticate when preserving native account state. In
0.60.4 activation also froze the chips for over a minute
([#3736](https://github.com/steipete/CodexBar/issues/3736), unfixed as of 0.60.6 snapshot).
Read-only diagnostics: `~/Library/Application Support/CodexBar/claude-swap-retained-usage.json`
and `~/Library/Group Containers/Y5PE65HELJ.com.steipete.codexbar/widget-snapshot.json`;
cached quota does not prove current authentication.

## Keep Claude credentials and quota fresh

`cswap list` can refresh OAuth tokens; it is not a read-only inventory. A refresh can leave an
isolated T3 home with an older token, or a CLI refresh can leave cswap stale.
`codexbar-profiles sync` copies the credential with the later access expiry in **either**
direction. It is a heuristic, not a transaction across external writers: the 60-second
watcher reduces drift but cannot remove the race with Claude/cswap. The helper never makes
refresh requests.

Create `~/.config/codexbar-profiles.json` privately, with verified mappings (never tokens):

```json
{
  "profiles": [
    {"name": "personal", "home": null},
    {"name": "work", "home": "~/.claude_work_home", "slot": 2, "email": "person@example.org"}
  ]
}
```

`home: null` = the unsuffixed default Keychain item. Omit `slot` for expiry-only monitoring
(normally the active default account); optional `keychain_account` overrides the macOS
username. Refusal cases (identity mismatch, unreadable item, concurrent change, equal expiry
with different tokens, cswap fallback file, oversized credential) are in
[scripts/codexbar-profiles](scripts/codexbar-profiles); a missing item or expired refresh token
needs browser login.

Sequence: `codexbar-profiles check` → `expiry` → `sync` (preview; inspect every direction) →
`sync --apply` → `install-jobs`.

Before `install-jobs`, inventory `~/Library/LaunchAgents/*keychain-sync*` and `*token-expiry*`.
When migrating old watchers, unload their exact labels first and keep their files for
rollback: two sync implementations on the same mappings fight. Don't change a working machine
merely to document it. Jobs: `com.t3-skills.codexbar-profiles.{sync,expiry}` (every 60 s /
09:05 daily), logs `~/Library/Logs/<label>.{log,err}` (no tokens; aligned syncs are silent).
Check logs after wake.

Expiry alerts fire below five days or when expiry is unknown. The original machine saw a
roughly 30-day absolute refresh-token expiry; read the actual `refreshTokenExpiresAt`, never
assume activity extends it. Missing metadata is unknown, not expired.

**Re-login / account change:** `codexbar-profiles remove-jobs` **first**, otherwise the watcher
restores the login you just removed. Clear inherited API key/token variables, re-login the
affected native home in the correct browser account, verify organization/plan, repeat
`cswap add` under that home, recheck sync and both apps, then `install-jobs` again.

A cswap fallback `.enc` under `~/.claude-swap-backup/credentials` takes precedence over
Keychain; the helper refuses that mapping until reconciled through cswap. Never delete it
blindly. Keychain writes go over stdin (never argv); credentials beyond the `security -i`
line limit are refused (large default-home MCP stores can hit this): use native login/cswap
reconciliation.

## Verify, update, roll back

- `codexbar-profiles check` / `expiry`: correct mapping and expiry, no secrets.
- `cswap list --json`: distinct correct accounts, no duplicate warnings or login errors
  (this probe may rotate tokens; check before/after sync).
- `claude auth status --json` under every home; `t3-limits` (Claude/Codex only) and a small
  real T3 turn per provider. For Codex, verify workspace and a fresh usage timestamp in
  CodexBar. A cached quota read alone isn't proof of login.
- `launchctl print gui/$(id -u)/com.t3-skills.codexbar-profiles.sync`, then `launchctl
  kickstart` the same target; inspect last exit status/log. Don't force a token rotation just
  to test the watcher.

Update: `pnpm dlx skills update codexbar-setup -p` from the personal setup repository, rerun
the installer/`--check` and `codexbar-profiles install-jobs` (refreshes absolute paths).
`remove-jobs` unloads only these two jobs; credentials/config remain. Restore legacy jobs only
after the replacement stops.

Reassess this workaround when claude-swap fixes isolated-home publication
([write-side #206](https://github.com/realiti4/claude-swap/issues/206),
[read-side #217](https://github.com/realiti4/claude-swap/issues/217)). A capture fix alone
doesn't prove inactive refreshes update the live home.
