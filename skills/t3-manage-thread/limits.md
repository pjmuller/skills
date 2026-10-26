# Rate-limit windows (t3-limits)

Flags: `t3-limits --help` (`--markdown` for a routing decision, `--json` for scripts, `--fresh`
skips the cache). Code: `scripts/lib/t3_limits.py`, shared with [routing](routing.md).

Reading the output:
- Percentages are **used** (CodexBar's menubar shows % left), relative to each account's own
  allowance (routing weights them by tier).
- `session` = 5 h rolling window (starts at its first request, not on the clock) · `weekly` = 7-day
  cap · `<Model> only` = per-model weekly sub-cap. Windows are whatever the endpoint reports, nothing
  hardcoded per provider (Codex Pro reports weekly only, Plus also a 5 h window).
- `pace` = share of the window elapsed; `room` = pace − used: **+20** spare, **−20** burning ahead.
  No pace for a stale window (no reset / reset in the past).
- Claude plan label: live `/api/oauth/profile` metadata, cached with usage for 90 s. Discovery
  failure keeps usage and marks the saved login label `(login fallback)`; login and `.claude.json`
  tier fields can lag subscription changes and never override a live tier (disagreement → notes).
  `unknown` = no label.
- **Tier** (`20x`, `5x map`, `1x?`; `multiplier`/`multiplier_source` in `--json`, also in
  `t3-list-profiles` and routing output) = advertised plan size, not quota left. Source: a label stating
  it (`max_20x`), else private `$T3CODE_HOME/userdata/t3-plan-multipliers.json`
  (`{"codex": {"prolite": 5}}`: driver → plan label → N; OpenAI publishes no multiplier), else `1x?`:
  unverified, ranked as the smallest plan, routing warns about the demotion.
- Setup-token profiles can lack a plan label. Never invent one or reauthenticate just to route. After
  independently confirming the plan, the same file may hold
  `"instances": {"<instance-id>": {"identity_hash": "<from --json>", "multiplier": 20}}`, applied only
  when the plan is absent and the account hash matches (a reported plan or changed login identity
  wins; replacing only the setup token does not prove an account change). Reverify/remove it when
  replacing the account. Plan size only, never account preference.

Source per enabled T3 provider instance (each row = the account T3 would run):
- **Claude**: macOS Keychain `Claude Code-credentials` (suffix `-<sha256(config dir)[:8]>` when the
  instance sets `config.homePath`), Linux/WSL `<homePath>/.credentials.json` (macOS fallback) →
  Anthropic OAuth usage endpoint. Empty homePath → `CLAUDE_CONFIG_DIR` (ignored when it is another
  instance's homePath: T3 sets it inside that instance's threads), then `~/.claude`.
- **Claude setup-token** (`env.CLAUDE_CODE_OAUTH_TOKEN`, no valid `/login` token; a revoked token can
  answer 429): one tiny `claude -p` Haiku turn through the unmodified CLI (`run_probe`; Anthropic
  allows subscription OAuth only in Claude Code itself), whose `rate_limit_event` carries the windows.
  A probe is a model turn, so it runs only when a session window is certainly open (`window_open`);
  else the reading is derived as idle (session 0 %, weekly kept) or unknown until the last local turn
  is 5 h old. Turns on claude.ai or another machine show at the next probe.
  Readings reused 5 min in `$T3CODE_HOME/userdata/t3-limits-probe.json`. Every 2 h
  (`FABLE_PROBE_SECONDS`) the probe runs on Fable instead (~100x a Haiku turn's quota): only that
  reports the `Fable only` cap. Plan = last live tier the API reported (`max_20x (live Oct 19)`), else
  the login label. Other per-model caps are lost. Row note `via setup-token probe`; `--fresh` probes
  anyway and may start a window. Logic: `probe_claude_usage`.
- **Codex**: `<homePath>/auth.json` (empty = `~/.codex`) → ChatGPT usage endpoint. Login e-mail shown
  so a mis-assigned home is visible. Top-level windows only; API-key logins have none.

Behaviour worth knowing:
- Tokens are never printed or refreshed (a refresh would rotate the CLI's own copy); an expired one
  reports itself and the other accounts still report. `HTTP 429` can also mean a revoked token.
- Endpoints are shared with other pollers and often 429. Last good payloads are cached in
  `$T3CODE_HOME/userdata/t3-limits-cache.json` (no tokens), bound to home + account identity, fresh
  90 s, marked-stale fallback up to 15 min. A cached exhausted window stays until its reset so routing
  keeps excluding it. `T3_LIMITS_DEBUG=1` traces cache hits.
- Paid overage is never shown.

Related: [t3-usage-windows](../t3-usage-windows/SKILL.md) confirms a window really reset before
resuming blocked threads.
