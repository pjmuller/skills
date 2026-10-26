---
name: codexbar-setup
description: "Use to install or troubleshoot CodexBar quota meters (macOS) next to T3 and native Codex/Claude/Antigravity profiles: a stale or wrong-account meter, Claude credential drift between isolated homes, refresh-token expiry alerts, Antigravity weekly quota."
---

# CodexBar with T3

Register repo-locally in the personal setup repository (the PATH helpers don't make the skill
globally discoverable). Discover existing homes, config and launchd jobs first; keep healthy accounts.

**Invariants**: CodexBar only displays quota; native CLI homes own authentication. Never switch a
global account to make a meter work. No credentials in reports or committed files; personal
mappings live in `~/.config/codexbar-profiles.json`, outside this skill.

- Setup, Codex/Claude/Antigravity providers, stale quota, verification → [install.md](install.md)
- **Claude (recommended)**: CodexBar's Claude Swap executable → `codexbar-claude-usage`, a read-only
  claude-swap stand-in fed by `t3-limits`; no refresher or sync jobs needed
  ([install.md](install.md#claude-quota-from-t3-limits)).
- Legacy claude-swap path (cswap slots, `codexbar-profiles` sync/expiry jobs, re-login) → [claude-swap.md](claude-swap.md)
- `scripts/install [--check|--relink]` links `codexbar-profiles` and `codexbar-claude-usage` onto
  `~/.local/bin`; `--check` covers macOS, uv, t3-limits, CodexBar.app and the links.
- Tests (`scripts/test_*.py`) use fakes only, never Keychain.
