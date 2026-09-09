# Working here

Public MIT skill source. Each `skills/<name>/SKILL.md` has name/description
frontmatter and owns its scripts/docs. `setup/t3-setup` is consumed raw once,
never installed. Keep skills self-contained; cross-skill commands resolve via PATH.
Every command-shipping skill has an idempotent `scripts/install` plus `--check`
covering its command links and dependencies. Shared thread plumbing stays inside
`t3-manage-thread/scripts/lib/`. No configuration file; personal settings live
outside installed skills because CLI updates replace them.

Use neutral examples/fixtures; preserve useful upstream workaround explanations.
Keep entrypoints short and link specialized docs. Dependencies: uv for Python,
pnpm for Node, mise for runtime versions. Test before tagging:
`uv run --with pytest pytest skills -q`, shell syntax checks, relevant installer
checks, `t3-spawn-thread --dry-run`, and a launchd smoke job for scheduling changes.
Verify Markdown relative links. Never exercise destructive purge/cleanup in tests.
Commit logical changes to main; update CHANGELOG and tag only verified releases.

Tested: macOS arm64, T3 Code 0.0.40, skills CLI 1.5.24 (2026-09-09).
Linux/WSL thread helpers are supported by code paths but not live-tested here.
