# Changelog

## Unreleased

## v0.4.6 (2026-10-08)

- t3-manage-thread: automatic profile routing is plan-aware. The headroom-per-hour score is multiplied by the multiplier the login label states (`max_20x` → 20, `max_5x` → 5, no multiplier → 1), and session tightness is measured in the same plan units relative to the largest verified plan (a 5x beside a 20x is tight from 60 % used; a 1x beside a 20x is overflow only). Unlabelled providers (Codex `pro`/`prolite`) keep the unweighted ranking; exclusion, unknown/stale handling, model-only caps and explicit `--profile` are unchanged. Routing output shows `%/h × Nx = score`.

- agents-md: verify rule now front-loads the proof: before non-trivial work the agent designs how it will verify end to end without the human (seed data, demo UI, device, scheduled check), builds that tooling first, flags only when it is a chunk of work, and treats "can you check…" as a defect.

## v0.4.5 (2026-10-08)

- video-shrink-for-gemini: `download-loom` fetches a public Loom share's video, metadata and Loom's own timestamped transcript without login (share-page Apollo cache, GraphQL fallback); `loom.md` documents the merge with Gemini. recording-followups lists Loom as a speech layer.

- t3-route: decide conditional self-settlement per standalone dispatch; verified durable delivery, existing authorization and no user review required. Eligible tasks stay visible while running; helper footer preserves keep-open instructions and surfaces material findings.

- agents-md: concise Markdown reports use progressive disclosure, callouts and Mermaid; conclusions stay visible.

- agents-md: simplify colleague handoffs to pre-merged prompts and short installation steps; retain inline repo maps, keep setup mechanics outside the global prompt, and scale optional PR/review flow to regression risk.

- agents-md: one role-neutral core with product-owner Git assistance, repository-aware integration and release authority; global-prompt migration inventories all homes/overrides, preserves backups and verifies fresh instruction loading.

## v0.4.4 (2026-10-07)
- t3-route (new): instruction-only intake, verified thread reuse and dispatch through a private wrapper; account/scope-aware onboarding and bounded corrections, with source evidence separate from inferred intent.
- t3-mail-link: `resolve` reads the selected account and Gmail thread ID without linking, spawning, writing mail-link state or scheduling; ambiguous references remain unresolved.
- bitwarden (pilot): `bw-once` opens human Terminal for fresh native authentication, performs one bounded lookup/copy/Send, then locks before delivery; no agent vault session, clipboard expiry preserves newer contents. Current released CLI requires a master password; live-vault UX remains unverified.
- yuki-core (new): Yuki "Aan te leveren aankoopfacturen" for one quarter (`yuki.py outstanding|sheet-push|discover`): read-only zeep client behind a method allowlist, carryover flag for older open items, Belgian-format FX parsing, fails closed on malformed data; `sheet-push` creates the `<YYYY>-Q<n>` tab, appends only unseen Yuki item ids, seeds manual cells once from the previous quarter tab and verifies on read-back. Company ids, sheet and Google account live in the wrapper's `yuki.json`.
- t3-setup / agents-md: offer browser cookie import, verify selected profiles in installed harnesses, and save only purpose/profile/account routing in the user's global prompt; retain browser fallbacks and keep setup details private.
- agents-md: global template tells agents to use T3 inline visual replies (`html_preview`/`html_render`, T3 ≥0.0.46) for charts/tables/mockups instead of prose or loose HTML files.
- agents-md: prefer native T3 browser tools in both Claude and Codex; retain tab IDs and verify account identity, with profile-selection details kept outside the global prompt.
- clickup-core: `[[file:NAME]]` links an attachment of the target task in comments, handoffs, reviews and descriptions (fails closed before writing on unknown/ambiguous names; newest version wins); bare attachment filenames are auto-linked instead of becoming ClickUp's dead domain links; `attach` prints `reference: [[file:<title>]]`.
- clickup-core: `chat read` / `chat post` for channels, DMs and threads; `--image` posts real inline images through the web app's session (`chat session` reads the one-year refresh cookie from a Chrome profile; the public API stores chat images as `src="http://null/"`).
- data-enrichment: durable URL/PDF capture to Markdown via free Jina, then one pinned treg/Olostep fallback; preserve raw evidence, links and billing receipts. Free capture needs no token.
- t3-schedule: persistent systemd user timers on Linux/WSL for recurring jobs and one-time continuations, sharing the existing retry/catch-up and duplicate guards; macOS keeps launchd. Installer checks verify scheduler readiness.
- t3-manage-thread: harden platform credential loading and background-worker readiness; use the native scheduler for Linux skills-refresh jobs.

## v0.4.3 (2026-10-02)
- t3-limits: reads Claude's `/login` credential from `<home>/.credentials.json` on Linux/WSL (and as macOS Keychain fallback) instead of crashing on a missing `security` binary; a profile that only holds a `claude setup-token` gets a "setup-token only" row (the usage API answers 403 to those tokens).
- skills-refresh: `schedule` on Linux/WSL warns when no cron daemon runs (with the WSL `[boot] systemd=true` persistence hint) and prints the zone the hour is read in; `--version` reports the release stamp for a managed copy inside a setup repo (was: that repo's commit).
- t3-find-thread: `t3-open-thread` refuses on Linux/WSL with a sidebar hint (`--browser` still works); docs mark it macOS-only.
- t3-setup: `skills add` lines pass `-a claude-code` (+ `-a codex`) so the CLI never prompts for agents in a non-TTY shell; verify the Codex login inside WSL (`codex login status`), not the Windows desktop app; WSL limitations listed in one place.
- t3-purge-threads: never purges a thread with a pending wake-up (`t3-schedule pending-resumes` continuation, `t3-mail-link list --thread-ids` link); `list` reports them as kept (`kept_pending_wake` in `--json`), a failing helper aborts.
- data-enrichment (new): one `TREG_TOKEN` for the treg.to catalog (~3,800 endpoints: email find/verify, person and company enrichment, scraping blocked pages, social, SERP/keywords, reviews, generation). `treg.py search|get` are free and print one line per endpoint (price, observed success); `call` caps routed spend at $0.05 and reports the real charge; `balance`. SKILL.md gives inspiration, money/verification rules and pointers into treg's own docs instead of a list.
- text-to-speech (new): provider-neutral voice discovery, single-clip generation with key-free provenance, optional normalization, and offline comparison; ElevenLabs/Gemini controls, accent guidance, and a catalog-to-Voice-Design workflow for specific voices.
- perplexity-core (new): `px.py ask` = one sourced research question over the Perplexity Agent API (web_search always on, optional people_search), markdown + retrieved-source list or `--schema` structured JSON with nullable fields and verified `*url` keys; `check` spends nothing. Extracted from brellascraper's enrichment service. Empty answers exit 3 after one retry; 429s back off.
- t3-setup: "Fresh machine" section for a Mac with nothing installed (Homebrew via one Terminal line the user pastes, then gh/jq/mise, Claude Code CLI, T3 Code cask, GitHub login) and a non-developer rule; startable from Claude Desktop's Code tab.
- recording-followups (new): after a Fathom/Leexi/SyncUp transcript, a debrief note plus self-contained T3 prompts, one temp file per prompt spawned by path (`t3-spawn-thread … < file`); light code research before proposing; thinker vs coding-model routing. Linked from video-shrink-for-gemini, leexi, clickup-core.
- agents-md: global template gains self-armed follow-ups: when the next step needs time to pass, the agent schedules `t3-schedule add --once <date> --resume-thread self` and reports a new ⏰ status. `t3-schedule` accepts `--resume-thread self` (the calling thread).
- t3-schedule: `pause <name> [--until YYYY-MM-DD]` and `resume <name>` keep recurring repo jobs registered while runners and catch-up skip them; an until date resumes at local midnight. `list`/`show` display effective status.
- t3-schedule: repo specs record `machines` (`one` default · `many` via `add --many-machines`) and `adopted_by` (label, git user.name, since, random id; `t3-schedule machine --label`). Adopting a one-machine job registered elsewhere asks for confirmation at a terminal and needs `--takeover` unattended (`--force` never implies it, also on `add`/`migrate --force`); repo-wide adopt checks every job before writing. A one-machine job no longer listing this machine skips at fire time (before the T3 wait and right before the spawn) and in catch-up; `list` shows who runs what. Intent from the local checkout, not a lock: the old machine stops once it pulls. Run `t3-schedule refresh` so existing runners get the check, then `adopt` each job once to record the machine.
- agents-md: global template gains four rules from PJ's first prompt retro: 80/20 cut first + opposite-model opinion on consequential design, web-verified external facts, Downloads + short thread titles, read the colleague's machine notes before writing instructions for their agent.
- clickup-core: `triage.md` escalations open with a gradable `Needs developer because:` reason (env gap · authority · cross-boundary · unresolved doubt · incident); a bare escalation goes back to the PO's agent.
- agents-md: global template gains the in-worktree session commit rule, minimal global skill registration, and same-session refresh of committed shared-skill copies.
- agents-md: global template env rule tightened: values only in `~/.config/mise-env/<org>/<repo>.env` (chmod 600), never a repo `.env` or `source .env`.
- t3-usage-windows: `topup` is the single automatic flow: runs daily 05:00–21:00 (was Mon–Fri) and gives accounts without a session window (Codex, weekly only) one `start` per local day on the first tick from 05:00 (state beside the log). `start` covers named Codex instances. The short-lived `warmup install` / `usage-window-warmup` job is gone: `t3-schedule remove usage-window-warmup`, `git rm` its two `.agents/schedules/` files, rerun `t3-usage-windows topup install`. Warm-up child threads are titled `Warm-up — <profile> <model>`.
- t3-schedule: recurring job definitions are versioned in the project repo (`.agents/schedules/<name>.json` + `.prompt.md`; no path, no profile); the runtime dir keeps a machine-local pointer + artefacts. `adopt <repo|spec>` opts a machine in (never on clone), `migrate` moves pre-versioning jobs, `list` flags untracked/uncommitted/missing specs and stale runners. `--once`/`--resume-thread` stay local.
- google-workspace-core: `gmail-draft-update <draft-id> (--body TEXT | --body-file PATH|-) [--html-file PATH] [--expect-message ID]` edits a draft body in place, never sends. Draft id, threadId, headers and every other MIME part stay byte-identical (no header refolding, original line endings, body Content-ID/Disposition kept); the candidate is checked before the PUT, so unsupported shapes are refused without writing, and verified again on read-back.
- video-shrink-for-gemini: `shrink-video --max-bytes 48M` splits output over the limit into overlapping `<name>.gemini.partNN.mp4` + `<name>.chunks.md` (absolute start/end per part); re-encodes once with 30 s keyframes, then stream-copies.
- resource-audit: read-only `resource_snapshot.sh` (CPU via top's second sample, memory pressure, paging, process swarms; printed suggestions only) + `scripts/install`.
- t3-manage-thread: `skills-refresh --version` reports "source checkout" only for this repo's own checkout (a managed copy inside a setup repo now shows its tag); `t3-spawn-thread` house effort by model family; `t3-rename-thread --help` corrected.
- claude-cloud: `--help` documents defaults, env fallbacks and exit codes. t3-maintenance: t3-drafts tests hermetic.
- t3-schedule: `add --resume-thread ID` schedules a continuation: at fire time the job pings that thread with the prompt; if it is deleted/archived/unreadable, its profile is gone or the ping fails, it spawns a fallback thread with the prompt + a bounded context pack. `t3-read-thread` exposes `deleted_at`.
- t3-manage-thread: a requested "separate/standalone thread" is spawned visible (`--no-hide` or 📤); 🏓 alone hides it while running.
- t3-manage-thread: `t3-mail-link` links a T3 thread to a Gmail thread (URL, hex id or `--search`; `FMfcg` web ids via the Chrome tab title). A weekday LaunchAgent poller pings the thread on new inbound mail (own/sent mail marks seen, no wake); the woken agent drafts, asks or settles per [mail-link.md](skills/t3-manage-thread/mail-link.md). Account via a google-workspace-core wrapper config.

## v0.4.2 (2026-09-26)
- t3-manage-thread: show account plan labels in limits JSON/Markdown and spawn routing explanations; clarify account-relative percentages and large-job capacity checks without changing routing. Sync the t3-drafts test fixture with the session/activity tables read by limit detection.

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
