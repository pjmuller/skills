# Install CodexBar alongside T3 Code

macOS recipe extracted from a working machine on 2026-09-18: CodexBar 0.60.4,
claude-swap 0.26.0, isolated Claude homes, five-minute polling, refresh on menu
open, bidirectional Keychain sync and daily refresh-expiry reminders.
Inspect installed versions before adapting; upstream behavior changes.

## Install and share profiles

```bash
brew install --cask codexbar
uv tool install claude-swap
pnpm dlx skills add pjmuller/skills -s codexbar-setup -g -y
~/.agents/skills/codexbar-setup/scripts/install
~/.agents/skills/codexbar-setup/scripts/install --check
open -a CodexBar
```

If already installed, use `uv tool upgrade claude-swap` when an upgrade is needed.
Enable launch at login, refresh every five minutes, and refresh all providers on
menu open in CodexBar. These are the working machine's preferences; avoid
background restart loops or aggressive polling. Verify the displayed timestamp
advances after manual refresh.

**Codex:** keep T3 and the terminal using the same intended Codex home; default
is `~/.codex`. Inspect T3's provider configuration and existing `CODEX_HOME`
before changing anything. In CodexBar enable Codex and choose Auto/OAuth for
native usage; use CLI source to diagnose. Do not copy `auth.json` into parallel
stores or apply the Claude Keychain helper to it. For multiple existing homes,
current upstream supports `providers[].codexProfileHomePaths` on the `id: codex`
entry in `~/.codexbar/config.json`; merge those paths without replacing other
settings, only when the installed version supports it. Each points to the same
home T3 uses, not a new login. Verify account **and workspace** match in all three
clients. CodexBar-managed accounts are separate homes, not automatic T3 sharing.
Native renewal belongs to Codex: run `codex login` with the affected home's
`CODEX_HOME`. Leave external OAuth sources and browser extras off unless needed.
[Upstream Codex behavior](https://github.com/steipete/CodexBar/blob/main/docs/codex.md).

**Claude:** use one authenticated home per T3 provider. Default has no
`CLAUDE_CONFIG_DIR`; isolated providers use T3 `config.homePath`, not environment
rows. Share prompts/skills through symlinks, not credentials. For isolated CLI
commands export the same absolute home string used at login; don't resolve a
symlink differently. The exact string determines its Keychain service hash.
Leave `CLAUDE_SECURESTORAGE_CONFIG_DIR` unset for this recipe; custom secure-store
overrides need their own mapping support.

A T3 Claude provider with empty `config.homePath` still uses the default login;
its display name and model selection do not bind an account. Treat default-account
switches as irrelevant only after every used Claude provider has an isolated home.

Register existing Claude logins in cswap, without switching the default:

```bash
env -u CLAUDE_CONFIG_DIR -u CLAUDE_SECURESTORAGE_CONFIG_DIR cswap add
env -u CLAUDE_SECURESTORAGE_CONFIG_DIR CLAUDE_CONFIG_DIR="$HOME/.claude_work_home" cswap add
cswap list --json | jq '{accounts: [.accounts[] | {number,email,usageStatus}], warnings: (.duplicateAccountWarnings // [])}'
```

Confirm each slot's email against that home's `claude auth status --json` and
`.claude.json` identity, including intended organization/subscription. Current
0.26.0 capture reads the hashed isolated Keychain service. Older local notes
recommended temporarily staging default credentials; upgrade instead. Do not
blindly assume a slot number or use `cswap switch`, automatic switching, or
CodexBar's Switch/Re-authenticate action for these shared Claude accounts.
Enable Claude Swap in CodexBar and select the absolute path from `command -v cswap`.
[Upstream Claude integration](https://github.com/steipete/CodexBar/blob/main/docs/claude.md).

**Antigravity (Gemini):** needs CodexBar 0.60.2+ and a signed-in `agy`
(`brew install --cask antigravity-cli`, run `agy` once). `agy` 1.2.2+ rejects
CodexBar's local HTTPS probe, so CodexBar runs `agy -p /usage` instead; older
CodexBar shows "Offline". Enable with `codexbar config enable --provider
antigravity` (same toggle as Settings), verify with
`codexbar usage --provider antigravity`. Shows the two weekly pools (Gemini,
Claude/GPT) with reset time, whichever Google account `agy` is signed into; the
report carries no account email and no five-hour bucket. Each refresh writes an
`agy` log under `~/.gemini/antigravity-cli/log/`. Antigravity.app is not needed.
[Upstream Antigravity notes](https://github.com/steipete/CodexBar/blob/main/docs/antigravity.md).

Diagnose only the provider you are working on: `codexbar usage --provider claude`
or `--status` from a shell runs the Claude probe under the CLI helper and can
raise Keychain/login prompts in the app; the menu itself is unaffected.

**Quota-only Claude view:** Settings → Menu → Multi-account layout → **Stacked**
shows all three accounts vertically (four or more use compact rows). This global
preference replaces account chips; Overview and menu-bar metric choices are separate.
Since [0.57.0 / #3498](https://github.com/steipete/CodexBar/pull/3498), Claude Swap
honors the default Segmented layout. Its inactive-account chips **activate
credentials**, not merely inspect quota. Avoid them, Switch Account and
Re-authenticate when preserving native account state.

In 0.60.4, activation disabled every chip and left the previous account highlighted
beside the target's “Details for” / “Loading…” for over a minute. Refresh/reopen
eventually recovered; waiting alone was inconclusive. No relevant fix in 0.60.5
or main's 0.60.6 snapshot on 2026-09-18. [Report #3736](https://github.com/steipete/CodexBar/issues/3736).
For read-only diagnostics, inspect `~/Library/Application Support/CodexBar/claude-swap-retained-usage.json`
and `~/Library/Group Containers/Y5PE65HELJ.com.steipete.codexbar/widget-snapshot.json`;
cached quota does not prove current authentication.

## Keep Claude credentials and quota fresh

`cswap list` can refresh OAuth tokens; it is not a read-only inventory. A refresh
can leave an isolated T3 home with an older token, or a CLI refresh can leave
cswap stale. The local mitigation copies the credential with the later access
expiry in **either** direction. This is a heuristic, not a transaction across
external writers; a 60-second watcher reduces drift but cannot eliminate the
race with Claude/cswap. No refresh requests are made by the helper.

Create `~/.config/codexbar-profiles.json` privately, with verified mappings:

```json
{
  "profiles": [
    {"name": "personal", "home": null},
    {"name": "work", "home": "~/.claude_work_home", "slot": 2, "email": "person@example.org"}
  ]
}
```

`home: null` means the unsuffixed default Keychain item. Omit `slot` for
expiry-only monitoring (normally the active default account). Optional
`keychain_account` overrides the macOS login username. Never put tokens here.
The helper checks the home identity against the mapped email, preserves unrelated
Keychain fields (including MCP logins), refuses unreadable items, defers if either changed during its read,
and refuses to guess when equal expiries carry different refresh tokens.
A readable blanked credential can be repaired; a missing item requires manual
login/inspection first. Expired refresh tokens require browser login.

```bash
codexbar-profiles check
codexbar-profiles expiry
codexbar-profiles sync                # preview; inspect every direction
codexbar-profiles sync --apply
codexbar-profiles install-jobs
```

First inventory `~/Library/LaunchAgents/*keychain-sync*` and `*token-expiry*`.
If migrating old watchers, unload their exact labels before enabling this one;
preserve the old files for rollback. Never run two sync implementations for the
same mappings. Don't change a working machine merely to document its setup.

New labels: `com.t3-skills.codexbar-profiles.sync` (60 seconds + login),
`com.t3-skills.codexbar-profiles.expiry` (09:05 daily). Jobs use absolute uv,
script and config paths, so launchd doesn't depend on interactive shell PATH.
Logs: `~/Library/Logs/com.t3-skills.codexbar-profiles.{sync,expiry}.{log,err}`.
Aligned sync runs are quiet; logs contain no tokens. Check logs after wake.

Expiry alerts start below five days or if expiry is unavailable. The original
machine observed roughly 30-day absolute refresh-token expiry; read the actual
`refreshTokenExpiresAt` field, never assume activity extends it. Missing expiry
metadata is unknown, not proof of expiration. Stop the jobs with
`codexbar-profiles remove-jobs` **before** intentional logout, account changes or
re-login: otherwise the watcher can restore the login you just removed. Re-login the affected native home
in the correct browser account, verify organization/plan, repeat `cswap add`
under that home, then recheck sync and both apps and run `install-jobs` again. Clear globally inherited API
key/token variables before native subscription login.

If cswap has a fallback `.enc` file under `~/.claude-swap-backup/credentials`,
it takes precedence over Keychain. The helper refuses that mapping until you
reconcile through cswap; never delete the fallback blindly. Writes use stdin,
not process arguments. Credentials exceeding the macOS stdin limit are refused;
use native login/cswap reconciliation (large default-home MCP stores can hit this).

## Verify, update, roll back

- `codexbar-profiles check` / `expiry`: correct mapping and expiry, no secrets.
- `cswap list --json`: correct distinct accounts, no duplicate warnings or login
  errors. Check before/after sync; this probe may rotate tokens.
- `claude auth status --json` under every home; `t3-limits` (Claude/Codex only,
  not Antigravity) and a small real T3 turn per provider. For Codex, verify intended workspace and a fresh usage
  timestamp in CodexBar. A successful cached quota read alone isn't proof of login.
- `launchctl print gui/$(id -u)/com.t3-skills.codexbar-profiles.sync`, then
  `launchctl kickstart gui/$(id -u)/com.t3-skills.codexbar-profiles.sync`; inspect
  last exit status/log. Do not force a token rotation just to test the watcher.

Updates: `pnpm dlx skills update codexbar-setup -g`, rerun installer/check and
`codexbar-profiles install-jobs` to refresh absolute paths. Config stays outside
installed files. `codexbar-profiles remove-jobs` unloads only these two jobs;
credentials/config remain. Restore legacy jobs only after the replacement stops.

Reassess the workaround when claude-swap fixes isolated-home publication:
[write-side #206](https://github.com/realiti4/claude-swap/issues/206),
[read-side #217](https://github.com/realiti4/claude-swap/issues/217).
A new capture fix alone doesn't prove inactive refreshes update the live home.
