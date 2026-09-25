# Keeping colleagues current on shared skills (2026-09-25)

**Verdict:** a skill that updates *itself* (helper runs `git pull`/`skills update` on use) is an anti-pattern. A *machine-owned, scheduled, release-gated* updater that applies before the workday and tells the human what changed is not. Same split Homebrew, rustup (`check-only`) and Claude Code plugin auto-update make: the package manager updates, the package never does.

## Facts (measured today)

| Skill (60 d file changes) | Mode | Who depends on it |
| --- | --- | --- |
| t3-manage-thread (125) | global | Willem, Thomas (both pinned at commit `4d03fd0`, 2026-09-09) |
| google-workspace-core (112) | hard-copied | all product repos |
| video-shrink-for-gemini (49) | hard-copied | dentai, redcell |
| clickup-core (37) | hard-copied | all product repos, 4 different lock hashes today |
| t3-maintenance (32) · t3-usage-windows (28) | PJ-only (macbook_setup symlink) | nobody else |
| t3-schedule (26) | repo-local in Willem's setup repo | Willem |

121 commits / 6 release tags in 60 days. Colleague harnesses: Thomas = Codex CLI in WSL + T3; Willem = Claude Code/Desktop → T3; Karel = Claude Code (leerheld copies); Astrid/Tobias/Jelle not yet set up.

Tooling as of 2026-09-25:
- `skills` CLI 1.7.0: `update [-g|-p] -y` re-fetches HEAD, hash-compares; lockfile = content hash, no version, no pin. **`skills check` silently runs `update`** (probe rewrote rootcause's clickup-core; reverted).
- Claude Code plugin marketplaces: background auto-update per marketplace (opt-in for non-official), plain git repo, skills ship inside. Claude-only; Codex marketplaces have no auto-update; `~/.local/bin` helpers still need `scripts/install`.
- `shared-skill-sync` (macbook_setup) already fans source → consumer repos via `/tmp` worktrees with digest check and `push`. Manual only. `CHANGELOG.md` per-skill entries exist.
- Bug: `whatsapp-bridge/SKILL.md` description has an unquoted colon; the `skills` CLI skips it, so nobody can `skills add` it.

## Why not self-update inside the skill
Mid-task surprise (helper swaps its own docs/binaries under a running agent, skips `t3-schedule refresh`), supply chain (every push to `main` executes unreviewed on colleagues' machines), no version to quote in bug reports, and one hook per harness instead of one machine job.

## Proposal

| | Mode 1: hard-copied in repos | Mode 2: global on colleague machines |
| --- | --- | --- |
| Runs where | PJ's Mac | colleague's machine |
| Mechanism | `shared-skill-sync apply` + `push`, scheduled | `skills-refresh` job (new, ~60 lines) shipped by `setup/t3-setup` |
| Trigger | daily 06:30 via `t3-schedule`, fan-out only when `origin/main` has a **new release tag** | daily 06:30 launchd (Mac) / cron (WSL); only when a new tag exists |
| Apply | auto: commit `[skip ci] chore: skills vX.Y.Z` to each consumer repo | auto: `pnpm dlx skills update -g -y` + rerun each changed skill's `scripts/install --check` |
| Colleague sees | nothing; next `git pull` carries it. Optional: ClickUp/T3 note listing repos touched | a T3 thread "Skills vX.Y.Z" holding the CHANGELOG entries since their previous tag (rendered from `CHANGELOG.md`), plus one line per install warning |
| Failure | sync fails on a dirty worktree → skips repo, reports; nothing breaks for colleagues | update fails offline → retries tomorrow; install `--check` fails → thread says "run `scripts/install --relink`", old helpers keep working |
| Effort | S (½ day): tag gate + `t3-schedule add`; also fixes PJ's own 4-hash drift | M (1–2 days): script, launchd+cron installers, tag-diff of CHANGELOG, test on Willem's Mac and Thomas's WSL |

Design points:
- **Release tag = the unit of distribution.** PJ keeps pushing to `main` at will; only `git tag vX.Y.Z` (already the rule: "tag only verified releases") reaches colleagues. Tag cadence sets colleague churn, not commit cadence.
- **Apply, don't nag.** Non-technical colleagues will never act on "update available". Auto-apply at 06:30 avoids mid-task surprise; the changelog thread replaces the nag with "here is what is new".
- **Human change log stays `CHANGELOG.md`** (`## Unreleased` → moved under the tag on release). The refresh job diffs `previous tag..new tag` sections; no new format.
- **Version stamp:** the job writes `~/.agents/pjmuller-skills.version` (tag + date) so bug reports and `scripts/install --check` can print it.
- **Stage, validate, activate** (Astra): fetch the tag into a staging dir, run each `scripts/install --check` there, then swap; keep last-good for rollback; lock against concurrent runs; running sessions keep the version they loaded (same as Claude Code plugins).

## Do not
- `git pull` in any helper, `SessionStart` hooks that hit the network, updating from `main` HEAD, forced resets in colleague checkouts.
- Rely on `skills check` (it updates). Verify `skills add pjmuller/skills#vX.Y.Z` tag support before building the tag gate on it; fallback = clone at tag, copy.
- Git submodules/subtrees in colleague repos; a second mechanism (plugin marketplace) next to the `skills` CLI.
- Sync on every commit (100+ chore commits per two months).

## Ranked next steps
1. Fix `whatsapp-bridge` frontmatter; run `shared-skill-sync apply && push` once to clear today's drift (minutes).
2. Mode 1 scheduling with tag gate (S).
3. Mode 2 `skills-refresh` job in `setup/t3-setup`, roll out to Willem and Thomas via a 3-line prompt (M).
4. Later: Claude plugin marketplace for Claude-only colleagues (Karel).

## Astra's review (🏓 thread, 2026-09-25)
Same verdict: "automate distribution, not self-modification inside a skill". Extra points folded in: the `skills` CLI's `check` dispatches to the same updater as `update` (confirmed in v1.5.24 source, still true in 1.7.0), so pin the CLI version in the job; a content hash proves change, not publisher authenticity, so pin the source commit/tag; stage + validate + activate with last-good rollback; never assume `skills add` installs PATH helpers. Astra prefers update PRs with auto-merge for Mode 1; with shared `main` and no feature branches here, a direct `[skip ci]` commit after a green smoke test is the equivalent.

## Status 2026-09-25 (evening)
Mode 2 shipped: `skills-refresh` in t3-manage-thread ([doc](../../skills/t3-manage-thread/skills-refresh.md)), wired into `setup/t3-setup`; colleague note in [docs/onboarding/skills-refresh.md](../onboarding/skills-refresh.md). The job clones the tag with git and copies the skill directories itself, so no `skills` CLI version needs pinning (`skills check` never runs).

Mode 1 follow-up (not done: >30 lines, needs `shared-skill-sync` changes in macbook_setup):
1. `update.py`: `--ref TAG` for `plan`/`apply` — compare consumers against `archived(SOURCE, TAG, …)` instead of `HEAD`, and install with `skills add pjmuller/skills#TAG` (CLI tag refs: see the probe result in the same-day build thread; fallback `git archive TAG | tar -x` into the worktree).
2. State file `~/.agents/shared-skill-sync.last-tag`; `plan` exits 0 "no new tag" when `git ls-remote --tags` has nothing newer.
3. `t3-schedule add --name shared-skill-sync --at 05:30 --project ~/code/pjmuller/macbook_setup --model haiku,luna --settle-when-done -- "…plan → apply → check → push; surface only when repos were touched"`; 06:30 is taken by fleet-kampadmin-support on PJ's Mac (slots ≥15 min apart).
