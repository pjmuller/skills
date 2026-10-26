# Install CodexBar alongside T3 Code

Recipe from a working machine (2026-09-18: CodexBar 0.60.4, isolated Claude homes). Check
installed versions before adapting; upstream behaviour changes. Config:
`~/.config/codexbar/config.json` (back it up before editing; `codexbar config validate` after).

```bash
brew install --cask codexbar
# from the personal setup repository:
pnpm dlx skills add pjmuller/skills -s codexbar-setup -y
.agents/skills/codexbar-setup/scripts/install && .agents/skills/codexbar-setup/scripts/install --check
open -a CodexBar
```

Preferences: launch at login, refresh every five minutes, refresh all providers on menu open. No
restart loops or aggressive polling; verify the displayed timestamp advances after a manual refresh.
Update: `pnpm dlx skills update codexbar-setup -p`, rerun the installer and `--check`.

## Codex

T3 and the terminal must use the same intended Codex home (default `~/.codex`): inspect T3's
provider config and `CODEX_HOME` before changing anything. In CodexBar enable Codex with
Auto/OAuth (CLI source only to diagnose). Never copy `auth.json` into parallel stores or apply the
Claude Keychain helper to it. Several existing homes → merge them into
`providers[].codexProfileHomePaths` on the `id: codex` entry: each path is a home T3 uses, not a new
login (CodexBar-managed accounts are separate homes). Verify account **and workspace** match in all
three clients. Renewal belongs to Codex: `codex login` with the affected `CODEX_HOME`. Leave
external OAuth sources and browser extras off.
[Upstream Codex notes](https://github.com/steipete/CodexBar/blob/main/docs/codex.md).

## Claude homes

One authenticated home per T3 provider. Default has no `CLAUDE_CONFIG_DIR`; isolated providers use
T3 `config.homePath`, not environment rows. A provider with empty `config.homePath` uses the
default login whatever its name or model, so default-account switches are harmless only once every
used Claude provider has an isolated home. Share prompts/skills through symlinks, never
credentials. For isolated CLI commands export the exact absolute home string used at login (don't
resolve symlinks differently): it determines the Keychain service hash. Leave
`CLAUDE_SECURESTORAGE_CONFIG_DIR` unset.
[Upstream Claude notes](https://github.com/steipete/CodexBar/blob/main/docs/claude.md).

### Claude quota from t3-limits

Why: with 1-year `claude setup-token` profiles, `/login` tokens are kept alive only by claude-swap,
whose refreshes can spend a refresh token (lost reply,
[claude-swap#434](https://github.com/realiti4/claude-swap/issues/434)) and die after ~30 days anyway.

Set the Claude provider's `claudeSwapExecutablePath` to the absolute path of
`codexbar-claude-usage` (keep `claudeSwapEnabled: true`), validate, restart CodexBar. Verify:
`codexbar-claude-usage --list --json` lists every T3 Claude provider with usage, and
`claude-swap-retained-usage.json` (below) updates. Readings come from `t3-limits`
([limits.md](../t3-manage-thread/limits.md)); per-model caps only while a `/login` token is valid.
Then retire claude-swap polling (`scripts/install` removes the old `codexbar-profiles` jobs); keep the credentials.

**Quota-only view**: Settings → Menu → Multi-account layout → **Stacked** (global). The default
Segmented layout's inactive-account chips **activate credentials**
([0.57.0 / #3498](https://github.com/steipete/CodexBar/pull/3498)) and froze the chips for over a
minute in 0.60.4 ([#3736](https://github.com/steipete/CodexBar/issues/3736)). Avoid them, Switch
Account and Re-authenticate.

## Antigravity (Gemini)

Needs CodexBar 0.60.2+ (older shows "Offline": `agy` 1.2.2+ rejects the HTTPS probe, so CodexBar
runs `agy -p /usage`) and a signed-in `agy` (`brew install --cask antigravity-cli`, run `agy` once).
`codexbar config enable --provider antigravity`, verify `codexbar usage --provider antigravity`.
Shows only the two weekly pools (Gemini, Claude/GPT) for `agy`'s Google account: no email, no
five-hour bucket. Each refresh writes a log under `~/.gemini/antigravity-cli/log/`.
[Upstream notes](https://github.com/steipete/CodexBar/blob/main/docs/antigravity.md).

## Diagnose and verify

- Probe only the provider you work on: `codexbar usage --provider claude` (or `--status`) runs the
  Claude probe under the CLI helper and can raise Keychain/login prompts in the app.
- Read-only caches: `~/Library/Application Support/CodexBar/claude-swap-retained-usage.json`,
  `~/Library/Group Containers/Y5PE65HELJ.com.steipete.codexbar/widget-snapshot.json`.
  **A cached quota read does not prove current login.**
- Login proof: `claude auth status --json` under every home, `t3-limits`, and a small real T3 turn
  per provider; for Codex also workspace and a fresh usage timestamp in CodexBar.
