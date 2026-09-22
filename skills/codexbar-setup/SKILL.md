---
name: codexbar-setup
description: Install and troubleshoot CodexBar alongside T3 Code and native Codex/Claude/Antigravity profiles on macOS, including shared account homes, Claude credential synchronization, expiry alerts and Antigravity (Gemini) weekly quota.
---

# CodexBar with T3

Register this skill repo-locally in the personal setup repository. Its helper may
be linked onto the machine's PATH; that does not make the skill globally discoverable.

Read [installation and profile sharing](install.md) for setup, migration or stale
quota/login problems. Discover existing homes and jobs first; retain healthy
accounts. CodexBar is the quota display; native CLI homes remain authentication
owners. Never switch a global account to make a meter work. Antigravity quota comes
from the signed-in `agy` CLI (weekly pools only); see install.md.

`scripts/install` links `codexbar-profiles`; `--check` checks dependencies/link.
Personal mappings live in `~/.config/codexbar-profiles.json`, outside this skill.
`codexbar-profiles check` and `expiry` read Keychain without refreshing tokens;
`sync` previews changes, `sync --apply` writes, `install-jobs` enables scheduling.
No credentials in reports or committed files.

Implementation: [scripts/codexbar-profiles](scripts/codexbar-profiles) owns
mapping validation, Keychain service hashing, newer-expiry selection, expiry
alerts and launchd jobs. Tests use fake credentials and never touch Keychain.
