---
name: claude-auto-mode
description: "Deprecated alias: merged into auto-mode-policy (Claude adapter in its claude.md). Use auto-mode-policy; this stub only forwards scripts/merge.py for old setups."
---

# Moved: auto-mode-policy

Merged into [auto-mode-policy](../auto-mode-policy/SKILL.md) on 2026-10-29: Claude rules now live in its
[claude.md](../auto-mode-policy/claude.md), the merger in `scripts/merge_claude.py`, the baseline in
`claude-baseline.json`. `scripts/merge.py` here runs that merger with the same arguments, or this stub's
frozen copy (`legacy_merge.py`, `claude-baseline.json`) when auto-mode-policy is not installed.

Install `pnpm dlx skills add pjmuller/skills -s auto-mode-policy -y` (same scope as this copy), point
setup scripts and prompts at the new path, then remove this skill. The stub goes away in a later release.
