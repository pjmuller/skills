# Agent skills

Self-contained skills for Claude Code, Codex and other agents. MIT licensed. This
is a **skill source repository**: it distributes reusable skills and templates,
not anyone's live personal configuration.
Register with the [`skills` CLI](https://github.com/vercel-labs/skills): `pnpm dlx skills add pjmuller/skills -s <name> [-g] -y`,
then, for skills that ship commands, run `scripts/install` and `scripts/install --check` once
(links their commands into `~/.local/bin`). Instruction-only skills need no installer.

## Registration scope

**Global registration** (`-g`) makes a skill discoverable in every repository on
one machine. **Repo-local registration** (omit `-g`) writes a tracked copy to
`.agents/skills/<name>` plus `skills-lock.json`, so worktrees, cloud sandboxes and
colleagues discover the version that repository expects. Register as little as
possible globally; this catalog recommends only `t3-manage-thread` and
`t3-schedule` globally by default.

A **personal setup repository** owns one person's machine setup, operator workflows
and periodic maintenance. A **project repository** owns product, team or domain work.
Repo-local does not mean project-specific: machine, prompt and writing-style skills
usually belong in the personal setup repository. A **bootstrap** consumes setup
instructions or templates once to establish live configuration; the installed
skills remain useful for later maintenance. Templates are reusable inputs. Live
configuration belongs outside replaceable skill installations.

Skill discovery and command availability are separate. A repo-local skill's
`scripts/install` may expose helpers globally on `PATH`; that does not globally
register its instructions. `~/.local/bin` must be on the login-shell `PATH`.
Start a new agent session after changing registration because harnesses may cache
their discovered skill list.

## Core and wrapper

Many skills here are a **core** (`*-core`, `slides`, `whatsapp-bridge`, …): copied into a repo and
replaced on update. A thin repo-owned **wrapper** skill beside it holds only that repo's or person's
DNA: accounts, resource ids, config files, brand, approval policy, facts no other user shares.

- Workflows, gotchas, recipes and lessons another user would benefit from belong in the core.
  The wrapper links the core file or section; it never restates it.
- Improvement found while using a wrapper → improve the core here (see
  [Contributing](#contributing)), then refresh the copies; edit the wrapper only for its own DNA.
- Healthy test: swap the wrapper's accounts and ids for another company's; whatever still reads true
  belongs in the core.

Most-used skills first.

| Skill | You need it when… | Scope | Register (then `scripts/install` + `--check`) |
| --- | --- | --- | --- |
| [t3-manage-thread](skills/t3-manage-thread/SKILL.md) | an agent delegates to, launches, messages, reads or settles T3 Code threads (native MCP tools), a script starts one (`t3-relay`), or provider rate limits matter | global | `pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y` |
| [t3-schedule](skills/t3-schedule/SKILL.md) | a T3 thread should start on a wall clock ("every workday 07:30 run X"); macOS launchd or Linux/WSL systemd user timers | global (with t3-manage-thread) | `pnpm dlx skills add pjmuller/skills -s t3-schedule -g -y` |
| [clickup-core](skills/clickup-core/SKILL.md) | agents in a project repo read/write ClickUp tasks (rich comments, attachments) against that repo's workspace config | project repo | `pnpm dlx skills add pjmuller/skills -s clickup-core -y` + a thin `clickup` skill holding `clickup.toml` |
| [t3-find-thread](skills/t3-find-thread/SKILL.md) | "which thread did we discuss X in?"; full-text search over local transcripts, jump to it | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-find-thread -y` |
| [google-workspace-core](skills/google-workspace-core/SKILL.md) | agents need reusable Workspace clients with repository-owned accounts and existing CLI contracts | project repo | `pnpm dlx skills add pjmuller/skills -s google-workspace-core -y` + an account wrapper |
| [t3-maintenance](skills/t3-maintenance/SKILL.md) | you orchestrate many worker threads: fleet view, stalled workers, unsent drafts, prompt mining; purge into a secret-redacted searchable archive, `t3-thread-archive check` tests whether a secret would be redacted | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-maintenance -y` |
| [recording-watcher](skills/recording-watcher/SKILL.md) | new Fathom/Leexi/Monologue calls should get follow-up threads automatically, on exactly one teammate's machine (deterministic owner election; macOS launchd or WSL systemd) | global, per machine config | `pnpm dlx skills add pjmuller/skills -s recording-watcher -g -y`, then `scripts/install` ([setup](skills/recording-watcher/setup.md)) |
| [whatsapp-voice-intake](skills/whatsapp-voice-intake/SKILL.md) | a voice note you send to your own WhatsApp chat should arrive, transcribed with its nearby text, in one T3 thread (e.g. your pinned router), without a model in the poller | global, per machine config | `pnpm dlx skills add pjmuller/skills -s whatsapp-voice-intake -g -y` (needs `whatsapp-bridge`, `video-shrink-for-gemini`, `t3-manage-thread`), then `scripts/install --schedule` ([config](skills/whatsapp-voice-intake/config.md)) |
| [t3-route](skills/t3-route/SKILL.md) | a private routing wrapper turns short requests, links or screenshots into correctly placed tasks; [onboarding](skills/t3-route/onboarding.md) establishes own accounts and routes | personal setup repo + private wrapper | `pnpm dlx skills add pjmuller/skills -s t3-route -a claude-code codex -y` (no command installer) |
| [video-shrink-for-gemini](skills/video-shrink-for-gemini/SKILL.md) | a screen recording (or Fathom call) must become a verified transcript or visual narration: shrink + Gemini API (`agy` without a key), local speech-to-text fallback | personal setup repo | `pnpm dlx skills add pjmuller/skills -s video-shrink-for-gemini -y` |
| [bitwarden](skills/bitwarden/SKILL.md) | URI-rule login discovery, one credential field, or Send creation with Touch ID/Terminal approval and CLI locking; macOS | personal setup repo | `pnpm dlx skills add pjmuller/skills -s bitwarden -y` |
| [slides](skills/slides/SKILL.md) | create, edit or review presentations: story, visual craft, notes and bundled Slidev expertise | project repo + `project-slides` wrapper | `pnpm dlx skills add pjmuller/skills -s slides -y` (no command installer) |
| [claude-cloud](skills/claude-cloud/SKILL.md) | a local agent must drive Claude Code **cloud** sessions headlessly: create, send, wait, read, archive; cloud dry runs and browser fallback (undocumented API experiment) | project repo where local agents drive its cloud sessions | `pnpm dlx skills add pjmuller/skills -s claude-cloud -y` |
| [mailbox-review-core](skills/mailbox-review-core/SKILL.md) | research every unsent ReplyPen draft in a Google mailbox, replace weak ones with a better version, open a fix thread per confirmed bug, and hand the operator an inline Markdown report (Gmail links, folded evidence) + ledger | project repo + a thin `mailbox-review` wrapper (mailbox, accounts, repos, policy) next to `google-workspace-core` | `pnpm dlx skills add pjmuller/skills -s mailbox-review-core -y` |
| [whatsapp-bridge](skills/whatsapp-bridge/SKILL.md) | an agent must read WhatsApp chats, resolve contacts and send explicitly authorized individual texts from a locally paired account (Neonize/whatsmeow, no browser) | personal setup repo + a thin wrapper holding account/recipient policy | `pnpm dlx skills add pjmuller/skills -s whatsapp-bridge -y` |
| [agents-md](skills/agents-md/SKILL.md) | create or simplify a repo's AGENTS.md / CLAUDE.md, write, prune and merge the global cross-project prompt ([template](skills/agents-md/global-template.md)), or write a handoff ([patterns](skills/agents-md/handoff.md)) | personal setup repo; target project when explicitly wanted there | `pnpm dlx skills add pjmuller/skills -s agents-md -y` (no command installer) |
| [t3-usage-windows](skills/t3-usage-windows/SKILL.md) | you juggle several Claude/Codex accounts: warm five-hour windows and top them up during the day (T3 resumes rate-limited threads itself) | personal setup repo | `pnpm dlx skills add pjmuller/skills -s t3-usage-windows -y` |
| [leexi](skills/leexi/SKILL.md) | agents need a Leexi call by URL or "today around 14:00": transcript with speakers/timestamps, summary, recording download, recent-call list | project repo | `pnpm dlx skills add pjmuller/skills -s leexi -y` |
| [recording-followups](skills/recording-followups/SKILL.md) | a transcribed call should become a short debrief plus spawnable follow-up thread prompts, or a narrated product-feedback walkthrough should get implemented | global, with recording-watcher | `pnpm dlx skills add pjmuller/skills -s recording-followups -g -y` (no command installer) |
| [resource-audit](skills/resource-audit/SKILL.md) | the Mac is slow or hot; CPU/RAM pressure, process ownership, targeted stopping and recovery | personal setup repo | `pnpm dlx skills add pjmuller/skills -s resource-audit -y` |
| [data-enrichment](skills/data-enrichment/SKILL.md) | a task needs external data the repo has no key for: work emails, person/company enrichment, blocked web pages, social posts, SERP/keywords, reviews, image/video generation; one treg.to token, paid per call | project repo (token via its mise env) | `pnpm dlx skills add pjmuller/skills -s data-enrichment -y` |
| [gitsync](skills/gitsync/SKILL.md) | your repos should stay level with their remotes: find dirty/ahead/behind checkouts across recently active repos, fast-forward clean ones, one delegated child per repo lands finished work and protects live work | personal setup repo (with t3-maintenance) | `pnpm dlx skills add pjmuller/skills -s gitsync -y` |
| [yuki-core](skills/yuki-core/SKILL.md) | each quarter, list Yuki's bank/card payments still missing a purchase invoice and append them to the company's quarter tab in a Google Sheet (read-only Yuki client) | project repo + a thin `yuki` wrapper holding `yuki.json` | `pnpm dlx skills add pjmuller/skills -s yuki-core -y` |
| [video-frames-for-vision](skills/video-frames-for-vision/SKILL.md) | a vision-only model (Codex, Claude Code) must understand a meeting recording: deterministic frame selection (drop people-only, one frame per screen state) + annotation prompt; no Gemini, no local models | project repo | `pnpm dlx skills add pjmuller/skills -s video-frames-for-vision -y` |
| [perplexity-core](skills/perplexity-core/SKILL.md) | sourced web research (people, companies, facts) through the Perplexity Agent API; free text with retrieved sources or schema-shaped JSON | project repo (key via its mise env) | `pnpm dlx skills add pjmuller/skills -s perplexity-core -y` |
| [monologue](skills/monologue/SKILL.md) | read notes, original summaries and timestamped speaker turns; reuse the Python API client | project repo | `pnpm dlx skills add pjmuller/skills -s monologue -y` |
| [auto-mode-policy](skills/auto-mode-policy/SKILL.md) | repair user-corrected Auto denials across Claude/Codex profiles, preserving sandbox and scoped trust; provider adapters and private setup template | personal setup repo (plus `claude-auto-mode` for Claude) | `pnpm dlx skills add pjmuller/skills -s auto-mode-policy -y` |
| [claude-auto-mode](skills/claude-auto-mode/SKILL.md) | Claude Code auto mode should allow routine work without exfiltration or force-push holes: baseline plus company/personal overlays merged into every Claude home | personal setup repo (with auto-mode-policy) | `pnpm dlx skills add pjmuller/skills -s claude-auto-mode -y` (no command installer) |
| [codexbar-setup](skills/codexbar-setup/SKILL.md) | CodexBar should share native profiles with T3/Codex and keep Claude credentials fresh (macOS) | personal setup repo | `pnpm dlx skills add pjmuller/skills -s codexbar-setup -y` |
| [microphone-calibration](skills/microphone-calibration/SKILL.md) | before dictation: repeat one sentence at several input gains, get levels/clipping/noise/SNR, local STT accuracy, playable clips and a recommended gain in Markdown; fixed-level A/B samples (macOS) | personal setup repo | `pnpm dlx skills add pjmuller/skills -s microphone-calibration -y` |
| [ui-before-after](skills/ui-before-after/SKILL.md) | someone will judge UI changes by eye: same screens in the same state before and after, as an HTML report plus ticket table | project repo | `pnpm dlx skills add pjmuller/skills -s ui-before-after -y` |
| [disk-audit](skills/disk-audit/SKILL.md) | the Mac is filling up; deterministic audit, cleanup only of self-regenerating caches | personal setup repo | `pnpm dlx skills add pjmuller/skills -s disk-audit -y` |
| [tls-trust-audit](skills/tls-trust-audit/SKILL.md) | a CA distrust/compromise advisory lands: which trust stores and clients on this Mac still accept the bad CA, live-probed, plus package-only remediation | personal setup repo | `pnpm dlx skills add pjmuller/skills -s tls-trust-audit -y` |
| [migration-parity](skills/migration-parity/SKILL.md) | migrate a working system with independent old/new data, UI and side-effect verification | project repo, while migration is active | `pnpm dlx skills add pjmuller/skills -s migration-parity -y` (no command installer) |
| [text-to-speech](skills/text-to-speech/SKILL.md) | find and audition voices, generate clips with ElevenLabs or Gemini, normalize and compare takes offline | project repo where speech is produced | `pnpm dlx skills add pjmuller/skills -s text-to-speech -y` |
| [tone-of-voice](skills/tone-of-voice/SKILL.md) | create or refresh `tone-of-voice.md` from an interview and real samples ([starter](skills/tone-of-voice/template.md)) | personal setup repo; target project when explicitly wanted there | `pnpm dlx skills add pjmuller/skills -s tone-of-voice -y` (no command installer) |
| [public-footprint-audit](skills/public-footprint-audit/SKILL.md) | audit a consenting person’s public web exposure and produce a sourced privacy-lockdown checklist | personal setup repo | `pnpm dlx skills add pjmuller/skills -s public-footprint-audit -y` (no command installer) |

Dependencies: t3-schedule and t3-manage-thread are installed together by setup; t3-maintenance and t3-usage-windows need t3-manage-thread's helpers; t3-usage-windows also needs t3-maintenance;
claude-cloud needs t3-manage-thread for profile → Keychain resolution (macOS only).
T3 Code must be running for the T3 skills. Thread helpers work on macOS and Linux/WSL; launchd scheduling and the top-up daemon are macOS-only.

First thing to set up once t3-manage-thread and t3-usage-windows are installed (macOS):
`t3-usage-windows topup install`. The five-hour clock starts on the first turn, so opening windows from
05:00 and re-opening them as they expire lands resets early and chains them through the day; Codex
weekly windows get one morning turn.

Paste-to-your-agent version:

```
Register the skill <name> from github.com/pjmuller/skills in the repository that owns the work with
`pnpm dlx skills add pjmuller/skills -s <name> -y`; use `-g` only for t3-manage-thread, t3-schedule or an explicitly
chosen machine-wide skill. If it ships commands, run scripts/install and scripts/install --check and
fix what --check reports; PATH availability does not change the skill's discovery scope. Then read SKILL.md.
```

## Update

The daily `skills-refresh` job applies new release tags of t3-manage-thread + t3-schedule
(stamp `~/.agents/pjmuller-skills.version`, `skills-refresh --version`). Repo-local copies:
`pnpm dlx skills update -p` inside the repo (commit the diff + lockfile), then rerun
`scripts/install` and `--check` for updated skills that ship commands. That follows `main`; to match
your global release instead, add by tag URL
(`pnpm dlx skills add https://github.com/pjmuller/skills/tree/vX.Y.Z/skills/<name> -y`): the
lockfile records `ref`, `update -p` keeps it, and the same command with a newer tag moves it.
Installers refuse to replace commands from another checkout; use `--relink` to choose a new canonical copy.
`--check` prints its resolved source directory first.
Updates replace installed files; keep personal customizations outside them. After updating
t3-schedule run `t3-schedule refresh`; with an enabled top-up daemon rerun `t3-usage-windows topup install`.
Releases and breaking changes: [CHANGELOG.md](CHANGELOG.md).
Maintainers: after tests and pushing `main`, publish with
`skills/t3-manage-thread/scripts/release vX.Y.Z`; it requires an SSH signature
accepted by the consumer's pinned verifier before pushing the tag.

Dependabot opens weekly Python (including transitive pins) and GitHub Actions updates.
WhatsApp's local Neonize source stays on its documented build/update path.
Minor/patch Python updates are grouped; major updates stay separate. The dependency
workflow checks committed locks and runs the skill suite plus ClickUp's shipped environment.
Updates need review and a release; nothing auto-merges. Fix dependencies here before refreshing
consumer copies, otherwise the next refresh restores the source's older lock.

## Multiple Claude homes

`skills add -g` writes to the active `CLAUDE_CONFIG_DIR/skills` and `~/.agents/skills` only. With
several isolated Claude homes, symlink every home's `skills` directory and `~/.agents/skills` to one
directory first (the one-time setup below does this). A committed `.claude/skills -> ../.agents/skills`
symlink in a repo works with project installs (verified with skills CLI 1.5.24, 2026-09-09).

## One-time machine setup

Give your agent the bootstrap URL and your parameters (accounts, which skills, prompt base):
https://raw.githubusercontent.com/pjmuller/skills/main/setup/t3-setup/SKILL.md
It detects existing setup, unifies Claude homes, installs helpers, verifies a launchd smoke job and
ends with a feedback block. Tool-free fallback: clone this repo and read `setup/t3-setup/SKILL.md`.

## Contributing

Maintained mainly for the teams of the owner's companies; collaborators have write access. Small,
clearly-better-for-everyone changes go straight to `main` after the checks in [AGENTS.md](AGENTS.md);
anything uncertain or consequential goes through a pull request for human review. `main` refuses
deletion and force-push. Everyone else forks and opens a PR. Add a CHANGELOG line; releases are
tags, see [Update](#update).
