# Changelog

## Unreleased
- t3-manage-thread: `dispatch-workers.md` — project-agnostic rules for spawning worker threads (short 🏓/📤 titles, thinker model, brief shapes, bookkeeping).
- google-workspace-core: add a secret-safe offline doctor and modular `client.json` fallback; ClickUp missing-token errors now identify checked paths safely.
- video-shrink-for-gemini: `download-leexi` fetches a Leexi call's transcript, summary, follow-up tasks and presigned recording through the public API (Basic auth, scoped keys, 403 on Python's default User-Agent); `leexi.md` condenses the API reference.
- google-workspace-core: neutral Workspace REST/read-only facades and modular clients; explicit account configuration, preserved compatibility interfaces, offline auth and request tests.
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
