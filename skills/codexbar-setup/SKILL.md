---
name: codexbar-setup
description: Install and troubleshoot CodexBar alongside T3 Code and native Codex/Claude/Antigravity profiles on macOS. Use when setting up or migrating CodexBar, when quota meters are stale or show the wrong account, when Claude credentials drift between isolated homes and claude-swap, for refresh-token expiry alerts, or for Antigravity (Gemini) weekly quota.
---

# CodexBar with T3

Register repo-locally in the personal setup repository; linking the helper onto PATH does not
make the skill globally discoverable.

Setup, migration, stale quota/login: [installation and profile sharing](install.md). Discover
existing homes and jobs first; retain healthy accounts.

Invariants: CodexBar is only the quota display; native CLI homes own authentication. Never
switch a global account to make a meter work. No credentials in reports or committed files;
personal mappings live in `~/.config/codexbar-profiles.json`, outside this skill.

- `scripts/install [--check|--relink]` links `codexbar-profiles` onto `~/.local/bin`; `--check`
  covers macOS, uv, cswap, CodexBar.app and the link.
- [scripts/codexbar-profiles](scripts/codexbar-profiles) (`--help`): mapping validation,
  Keychain service hashing, newer-expiry sync, expiry alerts, launchd jobs. `check`/`expiry`/`sync`
  only read Keychain and never refresh tokens; `sync --apply` writes; `install-jobs` schedules.
- `scripts/test_profiles.py`: fake credentials, never touches Keychain.
