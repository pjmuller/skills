---
name: codexbar-setup
description: "Use to install or troubleshoot CodexBar quota meters (macOS) next to T3 and native Codex/Claude/Antigravity profiles: a stale or wrong-account meter, Claude credential drift between isolated homes, refresh-token expiry alerts, Antigravity weekly quota."
---

# CodexBar with T3

Register repo-locally in the personal setup repository (the PATH helpers don't make the skill
globally discoverable). Discover existing homes, config and launchd jobs first; keep healthy accounts.

**Invariants**: CodexBar only displays quota; native CLI homes own authentication. Never switch a
global account to make a meter work. No credentials in reports or committed files.

- Setup, Codex/Claude/Antigravity providers, stale quota, verification → [install.md](install.md)
- **Claude (recommended)**: CodexBar's Claude Swap executable → `codexbar-claude-usage`, a read-only
  claude-swap stand-in fed by `t3-limits`; no refresher or sync jobs needed
  ([install.md](install.md#claude-quota-from-t3-limits)).
- `scripts/install [--check|--relink]` links `codexbar-claude-usage` onto
  `~/.local/bin` (and removes the retired `codexbar-profiles` link/jobs); `--check` covers macOS, uv, t3-limits, CodexBar.app and the links.
- Tests (`scripts/test_*.py`) use fakes only, never Keychain.
