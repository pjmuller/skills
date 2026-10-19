# Rate-limit windows (t3-limits)

Flags: `t3-limits --help` (`--markdown` for a routing decision, `--json` for
scripts, `--fresh` skips the cache). Code: `scripts/lib/t3_limits.py`, shared
with [routing](routing.md).

Glossary:
- Percentages are **used** (CodexBar's menubar shows % left).
- `session` = 5 h rolling window (starts at its first request, not on the clock) ·
  `weekly` = 7-day cap · `<Model> only` = per-model weekly sub-cap.
- `pace` = share of the window already elapsed (what an even load would have
  used); `room` = pace − used: **+20** = spare capacity, **−20** = burning ahead
  of pace. No pace for a stale window (no reset / reset in the past).
- Claude plan label comes from live `/api/oauth/profile` organization metadata,
  cached with usage for 90 s; `--fresh` refreshes both. Discovery failures retain
  valid usage and mark the saved credential label `(login fallback)`.
  Login and `.claude.json` tier fields can lag subscription changes; neither
  overrides a live tier. Disagreement appears in `t3-limits` notes.
  `unknown` means no label was available.
- **Tier** (`20x`, `5x map`, `1x?`) is printed after the plan in `t3-limits`
  (`multiplier`/`multiplier_source` in `--json`), `t3-list-profiles` and spawn
  routing. Source: a label stating it (`max_20x`), else the private
  `$T3CODE_HOME/userdata/t3-plan-multipliers.json` (`{"codex": {"prolite": 5}}`,
  driver → plan label → N) for labels that state none (Codex `pro`/`prolite`;
  OpenAI publishes no multiplier in metadata), else `1x?`: unverified, ranked as
  the smallest plan, never optimistic. Tier = advertised size, not quota left.
- Percentages are relative to each account's own allowance. A 1x account at
  20% and a 20x account at 20% do not have equal quota left; routing multiplies
  headroom by the tier. A fresh reading does not reserve capacity for running jobs.
- Windows are whatever the endpoint reports, nothing is hardcoded per provider
  (e.g. Codex Pro currently reports weekly only, Plus also a 5 h window).

Source per enabled T3 provider instance, so each row is the account T3 would run:
- Claude on macOS: Keychain item `Claude Code-credentials`, suffixed
  `-<sha256(config dir)[:8]>` when the instance sets `config.homePath` →
  Anthropic OAuth usage endpoint. Linux/WSL reads `<homePath>/.credentials.json`;
  macOS falls back to that file if Keychain has no usable login. Empty homePath
  uses `CLAUDE_CONFIG_DIR` (ignored when it is another instance's homePath: T3
  sets it inside that instance's threads), then `~/.claude`. Windows execution stays inside WSL.
- Claude with a 1-year `claude setup-token` (settings `env.CLAUDE_CODE_OAUTH_TOKEN`) and no
  valid `/login` token (expired locally, or the usage API refuses it: a revoked token can answer
  429): one tiny turn through the unmodified CLI (`run_probe`: `claude -p --model haiku --effort low
  --output-format stream-json`, no tools/MCP/hooks/session file, the profile's config dir) whose
  `rate_limit_event` carries the 5 h and weekly windows. Not a raw API call: Anthropic allows
  subscription OAuth only in Claude Code itself. A probe is a model turn, so `window_open` allows
  it only when a window is certainly open: the last reading's window still runs, or a local turn
  (newest `<config>/projects/*/*.jsonl`) came after a window-free point (the reading's reset, or
  an idle check: no local turn for 5 h / since that reset) that is < 5 h old. Idle → derived
  reading (session 0 %, weekly kept until its reset); turns since the last reading with the
  window state unprovable → error until the last turn is 5 h old. Turns elsewhere (claude.ai,
  another machine) show at the next probe; a window opened there is invisible locally, so a probe
  can start one only if nothing polled during that whole window (CodexBar polls every 5 min). Readings reused 5 min, stored per config dir + account
  in `$T3CODE_HOME/userdata/t3-limits-probe.json`. At most every 2 h (`FABLE_PROBE_SECONDS`) the
  probe runs on Fable instead: only a Fable turn reports the Fable weekly cap
  (`seven_day_overage_included` → `Fable only`), at ~100x a Haiku turn's quota. No reading yet → error until the first turn
  after an idle check; `--fresh` probes anyway (may start a window). Lost vs the API: other per-model
  caps; the plan is the last live tier the API reported for that account (`max_20x (live Oct 19)`,
  kept in the probe store), else the saved login label (`(login fallback)`), which can lag plan
  changes. Note: `via setup-token probe`.
- Codex: `<homePath>/auth.json` (empty = `~/.codex`) → ChatGPT usage endpoint.
  The login e-mail is shown so a mis-assigned home is visible. Only top-level
  windows; API-key logins have none.

Behaviour worth knowing:
- Tokens are never printed or refreshed (a refresh would rotate the CLI's own
  copy); an expired one reports itself (never sent; setup-token profiles probe
  instead) and the other accounts still report. `HTTP 429` can also mean a
  revoked token: this endpoint answers 429 to non-Claude-Code clients.
- The endpoints are shared with other pollers and often 429. Last good payloads
  are cached in `$T3CODE_HOME/userdata/t3-limits-cache.json` (no tokens), bound
  to home + account identity (Claude: hash of account/org ids, token fingerprint
  if no local identity), served fresh for 90 s and as marked-stale fallback up to
  15 min. A cached exhausted window stays until its reset so routing keeps
  excluding it. `T3_LIMITS_DEBUG=1` traces cache hits.
- Paid overage is never shown or counted as capacity.

Related: [t3-usage-windows](../t3-usage-windows/SKILL.md) confirms a window
really reset before resuming blocked threads.
