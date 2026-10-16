# Working here

Public MIT skill source. Each `skills/<name>/SKILL.md` has name/description
frontmatter and owns its scripts/docs. `setup/t3-setup` is consumed raw once,
never installed. Keep skills self-contained; cross-skill commands resolve via PATH.
Every skill that ships commands has an idempotent `scripts/install` plus `--check` covering its
dependencies and, when it exposes commands on PATH, their links. Shared thread
plumbing stays inside `t3-manage-thread/scripts/lib/`. No configuration file; personal settings live
outside installed skills because CLI updates replace them.

Use neutral examples/fixtures; preserve useful upstream workaround explanations.
Keep entrypoints short and link specialized docs. Dependencies: uv for Python,
pnpm for Node, mise for runtime versions. Test before tagging:
`uv run --with pytest pytest skills -q`, shell syntax checks, relevant installer
checks, `t3-pick-instance <model>` / `t3-relay check`, and a launchd smoke job for scheduling changes.
Verify Markdown relative links. Never exercise destructive purge/cleanup in tests.
Commit logical changes to main; update CHANGELOG and tag only verified releases.

Targets T3 Code ≥ 0.1.0 (Orchestrator V2) only: agents use its MCP tools, scripts `t3-relay`.
Linux/WSL thread helpers are supported by code paths but not live-tested here.

## Domain vocabulary

| Term | Meaning here |
| --- | --- |
| **Skill** | Discoverable instructions in `SKILL.md`, optionally bundled with scripts/docs; not itself a CLI command. [Distribution](README.md). |
| **Global / repo-local registration** | Discovery in every repository on one machine versus a tracked repository copy and lockfile. Helper availability on `PATH` is separate. Both registrations are replaceable; this repo owns the source. [Scope](README.md#registration-scope). |
| **Personal setup / project / skill source repository** | One person's machine and operator maintenance / product-team-domain work / reusable public distribution rather than live configuration. [Scope](README.md#registration-scope). |
| **Bootstrap** | One-time consumption of setup instructions/templates from `setup/`; not an installed skill and not a claim that maintenance skills are one-time-only. [T3 setup](setup/t3-setup/SKILL.md). |
| **Helper / installer** | A helper performs work; `scripts/install` exposes its commands and `--check` verifies readiness. Installing instructions alone does not install commands. |
| **T3 project** | T3's repository/workspace entry, selected when launching a thread. [Workers](skills/t3-manage-thread/workers.md). |
| **Thread / session / turn** | T3 task conversation / its provider runtime / one agent response cycle. A finished turn can leave the session alive. [Lifecycle](skills/t3-manage-thread/settle-thread.md). |
| **Profile** | A provider instance/account used to run a thread; distinct from the model and thinking effort. [Routing](skills/t3-manage-thread/routing.md#accounts). |
| **Round-trip worker** | 🏓 a `delegate_task` child: no sidebar row, its final answer wakes the parent. Not an in-session sub-agent. [Workers](skills/t3-manage-thread/workers.md). |
| **Settle** | Stops a thread's session and sub-agents and moves it out of the inbox; history stays. No hiding: busy threads fold into T3's Working section, 🏓 workers are `delegate_task` children. [Settle](skills/t3-manage-thread/settle-thread.md). |
| **Scheduled job** | A wall-clock launcher that spawns a T3 thread (or wakes an existing one: continuation); distinct from that thread's work or an in-session timer. [Scheduling](skills/t3-schedule/SKILL.md). |
