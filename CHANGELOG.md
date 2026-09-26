# Changelog

## Unreleased

## v0.4.1 (2026-09-26)
- Docs-only skill audit across every skill and `setup/t3-setup` (~−700 lines): docs keep trigger, map, intent and gotchas; usage that `--help` prints moved to pointers. File names and `##` anchors that consumer wrappers link to are unchanged, except whatsapp-bridge (`## Map`, `## Safety (hard rules)`, `## History limits`) and removed `setup/t3-setup/codexbar.md` (→ `codexbar-setup/install.md`).
- Stale claims fixed: account routing covers Claude and Codex; an explicit `--model` gets its house effort; `--self` settles via `t3_supervise`; `transcribe-openai --hint` is ≤20 terms, and the prompt expects `--out transcript.openai.md`; `keychain_service()` lives in `lib/t3_limits.py`; t3-schedule `--once` for one-time routines; clickup appends are verified by `content_signature`; google-workspace sends `supportsAllDrives` on every Drive call and has no draft-update command.
- Public hygiene: customer, colleague and personal example names neutralized in docs, a `transcribe-openai` docstring and a `clickup.py` comment.

## v0.4.0 (2026-09-25)
- t3-manage-thread: `skills-refresh` — release-gated updater for globally installed copies of this repo's skills: applies only new `vX.Y.Z` tags (never `main` HEAD), stages a clone at the tag, `bash -n` pre-check, swaps the skill directories with a last-good rollback, reruns each updated skill's `scripts/install`, writes `~/.agents/pjmuller-skills.version` and prints the CHANGELOG entries between the two tags (exit 0 current · 10 applied · 1 failed). `skills-refresh schedule` registers the daily 06:30 job: macOS via `t3-schedule add --hide --no-notify` on `haiku,luna`, prompt = `skills-refresh --job`, which itself settles the thread (nothing new) or surfaces it once with the changelog (applied) or the error; `--quiet` settles on applied too. Linux/WSL via cron. Symlinked source checkouts are left alone. No `skills update`/`skills check` involved.
- t3-manage-thread: `t3-spawn-thread --version` / `skills-refresh --version` print the installed release tag from the stamp (or `source checkout <git describe>`); `scripts/install --check` shows it. `--model luna` alias (`gpt-6-luna`).
- t3-schedule: `add --hide` (snooze keeper without the self-settle footer) and `add --no-notify` (no launch notification); `refresh` skips jobs whose runner is active instead of killing a spawn in flight.
- t3-schedule: `--model` accepts an ordered comma list (`opus,sol`): at fire time the runner probes each candidate with `t3-spawn-thread --dry-run` and spawns the first whose ecosystem is installed and has capacity; no `--model` ≡ `opus,sol`. Profile keeps following the spawn helper's capacity routing (unknown-capacity accounts only when nothing is verified).
- t3-setup / README: the standard T3 setup is `t3-manage-thread` + `t3-schedule`, both global, plus the `skills-refresh` job; `docs/onboarding/skills-refresh.md` is the paste-to-colleague upgrade note.

## v0.3.4 (2026-09-25)
- video-shrink-for-gemini: mandatory vocabulary grounding before any Gemini/OpenAI transcription (people, products, taxonomies/enums from the project's docs → `## Vocabulary` block and `--hint`); `transcribe-openai` without `OPENAI_API_KEY` prints skipped and exits 0 (enrichment, not a blocker). Annotation prompt carries the same vocabulary field.

## v0.3.3 (2026-09-25)
- video-shrink-for-gemini: `transcribe-openai` — second-opinion speech layer through OpenAI's transcription API (`gpt-transcribe` + vocabulary hint), aligned to the vendor transcript's speakers/timestamps or in chunks (`--diarize` optional); measured on Flemish meeting audio. video-frames-for-vision's annotation prompt reads it next to the vendor transcript.

## v0.3.2 (2026-09-25)
- video-frames-for-vision: defaults favour few but relevant frames (`--max-frames 60`, one view per page, 20 s coverage); over-budget demotion drops near-duplicate pages before short novel ones.
- agents-md / clickup-core: handoff to a non-technical reader who works through a coding agent = one copy-pasteable md block addressed to the agent.

## v0.3.1 (2026-09-25)
- video-frames-for-vision / leexi: Codex recipe targets Linux/WSL/macOS (apt/brew, `uv run --script` with POSIX paths); the PowerShell/winget instructions were wrong for a WSL-backed setup. Benchmark note: one Claude Code agent hits a media request limit after ~54 frames.

## v0.3.0 (2026-09-25)
- leexi: new skill (infrastructure layer split out of video-shrink-for-gemini). `download-leexi` gains `--at "today 14:00"` (nearest call in a time window, `--pick` on ambiguity) and a default git-ignored `./.local/leexi/<uuid>/` out dir; `leexi-calls` lists recent calls; shared stdlib client `leexi_api.py`; Windows-safe `uv run --script` invocation; unit tests.
- video-frames-for-vision: new skill for vision-only models (Codex, Claude Code) without Gemini. `select-frames` samples a recording at 1 fps, classifies people-only frames (skin/edge/content-region heuristics), groups screen frames into views (pHash + SSIM) and pages (same chrome + header band, scroll tolerant), keeps one frame per page plus extra scroll positions, crops the shared-content region at 2×, writes `manifest.md/json`, contact sheets and audit sheets (people-only sentinels, transients). Annotation prompt reproduces the meeting-analysis shape (screen events, topics, action items, ready-to-paste prompts); Codex recipe for Windows.
- video-shrink-for-gemini: **breaking** — `download-leexi` and `leexi.md` moved to the `leexi` skill; `scene-frames` removed in favour of `select-frames`. Docs delegate: Leexi input → `leexi`, no Gemini → `video-frames-for-vision`. Rerun `scripts/install` for both skills.
- clickup-core: `scripts/syncup.py` downloads a SyncUp's recording, AI notes and untimed notetaker transcript from a chat message, chat channel (`--list`) or notes Doc URL; token-only (no clickup.toml), private git-ignored output, exit 75 while ClickUp is still processing.
- t3-schedule: once-jobs retry a missed/failed slot until 23:00 that day (recurring jobs keep slot+10h: they have tomorrow).
- t3-spawn-thread: `--settle-when-done` footer is conditional — the worker self-settles only on a clean outcome (nothing new the user needs); otherwise it unhides itself (`t3-hide-thread --unhide <own id>`) and ends with a terse report.
- t3-schedule: `add --once YYYY-MM-DD` one-shot jobs with the recurring guarantees (catch-up until slot+10h, one spawn). Runner guards launchd's yearly re-fire; the catch-up poller retires fired/expired once-jobs (`list` shows the outcome, expiry notifies); `run-now` forces the date; past date/time rejected; `--weekdays`/`--days`/`--once` mutually exclusive.
- whatsapp-bridge: new skill. Local Python WhatsApp helper (pinned Neonize 0.4.7 built from source, `NEONIZE_BOT_TAG=off`, no browser/daemon): QR pairing via a real Terminal window, synced-history reads, contact lookup/bounded reply context, allowlisted individual sends with 5 s cross-process pacing. Mechanics live in the core; a repo-local wrapper skill owns the account, own number, allowed recipients and drafting policy.
- t3-limits: Codex usage is read per T3 instance from `<home>/auth.json` + `chatgpt.com/backend-api/wham/usage` (no CodexBar dependency): every Codex account gets its own row, attributed to the instance T3 would run, with the login e-mail on the plan line. Cache entries are bound to home path + account id; an exhausted window outlives the 15 min stale cutoff until its reset; missing percentages are unknown (`?`/`null`), never 0.
- t3-spawn-thread: one capacity policy for Claude and Codex — a driver switch (`--model astra` from a Claude thread) is routed by capacity too, the sibling account only breaks ties; no sibling no longer blocks routing. Every automatic route prints a decision block (candidates, windows, room, unknown/stale/excluded state, chosen account, override hint), also on refusal and under `--dry-run`. A single profile is polled too (an exhausted one refuses instead of spawning a blocked thread).
- t3-schedule: `pick-profile`, `picks.log` and the recent-pick penalty are gone; the runner omits `--profile` and inherits the spawn routing. All-exhausted spawns fail and are retried by the catch-up poller.
- Scope: default to repo-local registration; distinguish personal setup, project and skill source repositories. Only `t3-manage-thread` is recommended globally. Prompt/voice maintenance stays in the personal setup repository; migration and cloud-session skills belong in consuming projects.
- tone-of-voice: new skill. Interview-driven capture of how a person writes from their real samples (pasted, sent mail via google-workspace-core, Docs, posts), ping-pong confirmation, `tone-of-voice.md` with a starter template and anti-AI-slop checklist, wired into the global prompt.
- agents-md: `handoff.md` (relay prompt for a colleague/harness, dev → non-technical, non-technical → dev with intent first and symptoms over conclusions); template synced (delegation heading, sub-agent model lists, handoff pointer). clickup-core links to it for reporter → developer handoffs; wrapper template no longer carries a link that only resolves after copying.
- t3-manage-thread: `t3-list-profiles` lists enabled accounts per ecosystem (Claude / OpenAI / Google) with the exact `--profile` value; spawn examples drop `--profile`/`--thinking` (account and effort follow the parent). `code-review.md` absorbs the model pairing and hand-off-plugin rule; agents-md `global-template.md` delegation block simplified to match.
- t3-spawn-thread: `--profile` is an account label orthogonal to `--model` (`probackup` + `astra` → Codex ProBackup, + `fable` → Claude ProBackup); a driver switch without `--profile` picks the inherited account's sibling instance instead of failing. Docs/examples drop `--profile codex`.
- t3-manage-thread: `code-review.md` — opposite-model review as a 🏓 worker (when, spawn commands both directions, brief shape, reviewer output, builder push-back); `SKILL.md` slimmed to a commands-first entrypoint with cross-provider spawn examples.
- google-workspace-core: `gmail-export` writes a query's messages (or `--by-thread` conversations) as compact Markdown files plus `index.md` for local grep; `gmail-search` paginates and fetches metadata concurrently; `references/gmail-search.md` holds the search → export → grep → clean-up loop and Gmail query cheat sheet. Body text: strict UTF-8 before a declared Windows-1252, wrapped `On … wrote:` attributions trimmed, mailer tracking links dropped.
- agents-md: `global.md` + `global-template.md` for the user-level cross-project prompt (what belongs where, pruning by experiment, merging the template into an existing file, re-sync marker); t3-setup merges this template instead of external bases.
- t3-manage-thread: `dispatch-workers.md` — project-agnostic rules for spawning worker threads (short 🏓/📤 titles, thinker model, brief shapes, bookkeeping).
- google-workspace-core: one `gws.py --config workspace.json` CLI and importable `gws_core`; replaces REST/read-only/modular facades. Includes account-bound OAuth, secret-safe diagnostics, draft CRUD, Slides tooling and offline parity tests.
- ClickUp missing-token errors now identify checked paths safely.
- video-shrink-for-gemini: `download-leexi` fetches a Leexi call's transcript, summary, follow-up tasks and presigned recording through the public API (Basic auth, scoped keys, 403 on Python's default User-Agent); `leexi.md` condenses the API reference.
- slides: default to committed repo-local installs, so colleagues/cloud agents need no global skill.
- slides: reusable presentation craft, concise speaker notes, visual verification and curated MIT-attributed Slidev guidance; thin project wrappers retain local brand and delivery context.
- t3-spawn-thread: discover accounts across native provider drivers; model-aware name matching, ambiguity rejection, and preserved Codex account/effort inheritance.
- migration-parity: concise autonomous migration guidance with independent baselines, data/effect comparisons and end-to-end user workflows.
- t3-hide-thread: preserve fractional timestamps so same-second turn completion is re-snoozed; regression coverage for queued pings and attention requests.
- t3-usage-windows: list banked Codex resets as Markdown/JSON or consume the earliest expiry through the native app-server protocol.
- video-shrink-for-gemini: explicit `download-fathom --transcript-only` exports raw API JSON and speaker/timestamp Markdown without video or ASR.
- claude-cloud: disclosed profile/environment/repository defaults, create --wait/--title, official-CLI token refresh, paginated session review and redacted idempotent export.
- Command installers guard against switching checkouts accidentally; `--relink` opts in, project copies warn, and `--check` identifies the source.
- claude-cloud: headless Claude Code cloud sessions (envs, create, send, wait, read, archive) with T3-profile substring resolution through t3-manage-thread's Keychain mapping; undocumented-API experiment.
- video-shrink-for-gemini: measured local route for when Gemini is unavailable — `transcribe-local` (mlx-whisper ASR) and `scene-frames` (scene-sampled original-resolution frames with a visual-token estimate), plus subscription modality limits and per-model ID-reading fidelity.
- video-shrink-for-gemini: bounded native drafts, candidate provenance and targeted original-frame verification for opaque identifiers.
- t3-read-thread: expose parsed thread model selection in JSON for post-spawn route attestation.
- agents-md: concise guidance for creating and simplifying canonical agent entrypoints, grounded in intent, domain language, ownership and verification.
- t3-manage-thread: installer check recognizes T3 Code's `last-server-origin` fallback when the runtime descriptor is absent.
- **Breaking rename:** claude-cloud-feedback-loop merged into claude-cloud; dry-run and browser-fallback guides replace its entrypoint.
- video-shrink-for-gemini: browser-free Fathom API download and timing references; smaller readable 720p presets, measured 50 MiB fitting and minimal-chunk fallback.
- codexbar-setup: standalone macOS guide and Python helper for shared native profiles, bidirectional Claude credential sync and expiry alerts; linked from T3 setup.
- t3-manage-thread: clarify standalone/no-ping scope for parent tasks versus round-trip reviewers.
- t3-spawn-thread: model-aware Claude account routing from shared cached quota/pace data; explicit profiles win, known exhausted accounts are excluded, unknown capacity is reported.
- Antigravity: concise colleague setup; verified native CLI video-paste → Markdown transcript workflow.
- resource-audit: incorporate compressed-memory, worker-swarm, and stale-server investigation recipes from existing operator guardrails.
- resource-audit: separate macOS CPU/RAM diagnosis, process ownership, and recovery recipes; keep disk-audit focused on storage.
- Antigravity spawns: Gemini 3.8 Flash High default, model-encoded thinking; video skill delegates locally and requires verified Markdown output.
- t3-setup: `migrate-claude-routines.md` — Claude Desktop local routines → t3-schedule (registry + prompt locations, mapping, disable step).

## v0.2.1 — 2026-09-09

- clickup-core 0.2.1: pytest rootdir pinned to the skill (`[tool.pytest.ini_options]`) so a consumer
  repo's own pytest config no longer leaks into `pytest -q` inside the installed copy.
- t3-limits: cache usage reads per profile (90 s fresh window, `--fresh` to bypass) and fall back to
  the last good value on 429/network errors instead of reporting the account as unknown.
- t3-setup: default account's provider must carry no `CLAUDE_CONFIG_DIR` (the Keychain item is
  hashed from its value, so an explicit `$HOME/.claude` reads an entry that never existed).
- t3-setup: document the settings.json path for adding a Claude provider instance, reading the
  field shape from an existing instance instead of assuming it.
- t3-schedule: put pnpm's global bin (`$PNPM_HOME`, else `~/Library/pnpm`) on the launchd runner
  PATH, and have `scripts/install --check` resolve pnpm/uv/jq/sqlite3 under that PATH.
- t3-limits: print `<rateLimitTier> (<subscriptionType>)` when the tier does not match the plan.

## v0.2.0 — 2026-09-09

- Merge window warm-up and limit recovery into t3-usage-windows; unified CLI, system timezone, migrated top-up label.

### ClickUp core

- Add workspace-neutral clickup-core: discovery, tasks, rich comments, media, custom fields and configured handoff/review.
- Preserve native rich content on append; ship TOML templates, shared Loom downloads and offline contract tests.

## v0.1.0 — 2026-09-09

- Import eight skills, then replace personal examples with neutral fixtures.
- Add raw one-time T3 setup, MIT license and CLI distribution/update recipes.
- Check helper dependencies, resolve mise tools in launchd, migrate scheduler/top-up labels.
- Add visual-first and mixed recording prompts; make disk-audit scripts self-contained.
- Verify project CLI installation through a committed Claude directory symlink.
