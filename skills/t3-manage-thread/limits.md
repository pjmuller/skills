# Rate-limit windows (t3-limits)

```bash
t3-limits                   # every Claude + Codex profile T3 knows, aligned, Europe/Brussels
t3-limits --profile work  # substring of instance id / display name
t3-limits --markdown        # one table (used · pace · room · resets) — paste into a routing decision
t3-limits --fresh           # skip the cache (see below)
t3-limits --json            # rows: account, instance_id, window, used_percent, pace_percent, room_percent, resets_at, resets_in_seconds
                            # an unreachable account yields one row {account, instance_id, window: null, error} — "unknown", not "stale"
```

`pace` = % of the window already elapsed = what an evenly spread load would have used by now.
`room` = pace − used: **+20** = 20 points under pace (spare capacity, steer work here), **−20** =
burning faster than even. Session pace is relative to the 5h window (resets 5h after its first
request), weekly/`<Model> only` to the 7-day window. No pace when the window is stale (`no reset`
/ reset in the past — nothing requested since). Codex shows only its top-level windows (Spark
sub-windows dropped as noise).

Chain, per enabled T3 provider instance so every row is attributed to the account T3 would run:
- Claude: `settings.json` → `claudeAgent` instances → per-profile macOS Keychain item
  (`Claude Code-credentials`, or `-<sha256(absolute config dir)[:8]>` when `config.homePath` is set) →
  `GET api.anthropic.com/api/oauth/usage`.
- Codex: `settings.json` → `codex` instances → `<config.homePath>/auth.json` (empty home path =
  `~/.codex`, Codex CLI's default) → `GET chatgpt.com/backend-api/wham/usage` with that login's
  account id. The plan line shows the login e-mail so a mis-assigned home is visible. Every
  top-level window is a row (Pro currently exposes only the weekly one; a session window appears
  when the plan has it); model reserves and reset credits are notes. API-key logins have no windows.
No CodexBar dependency (the same endpoint it polls).

Percentages are **used** — the inverse of CodexBar's menubar "% left". `session` = the 5h rolling
window (resets 5h after its first request, not on the clock) · `weekly` = the 7-day cap ·
`<Model> only` = per-model weekly sub-cap (`weekly_scoped`).

The plan label after the account name is `rateLimitTier` (minus `default_claude_`), plus
`(subscriptionType)` when the tier does not match the plan — e.g. `max_20x (pro)`, while a real
Max account just shows `max_20x`. Both come from the local
credential written at `claude auth login`, not from the API: if the tier looks wrong, re-login
that home.

Extra usage (paid overage) is never shown or counted as subscription capacity.
[Automatic spawn routing](spawn-thread.md#automatic-profile-routing) excludes exhausted
subscription windows regardless of overage settings; explicit profiles bypass routing.

Cached: the usage endpoints are shared with other pollers (CodexBar, `t3-usage-windows topup`), so
they answer 429 often. Each instance's last good payload is kept in `~/.t3/userdata/t3-limits-cache.json`
(mode 0600, no tokens), bound to the home path + account id that produced it (a re-login or home
reassignment never inherits another account's numbers): younger than 90 s it is served without a
call (`--fresh` bypasses), and on a 429/network error one short retry (honouring `Retry-After`) is
followed by the cached value if it is under 15 min old — shown as `(cached 3m ago)` / `"stale": true`
with `fetched_at`. Older than that the account reports the error (`HTTP 429`), keeping only a cached
exhausted window whose reset is still ahead, so routing keeps excluding it. A missing percentage prints
`?` and is `null` in JSON. `T3_LIMITS_DEBUG=1` traces cache hits on stderr.

Tokens are never printed and never refreshed (a refresh would rotate Claude Code's own copy); an
expired one prints `token expired — run any turn in that profile to refresh` and the rest still report.

Related: [t3-usage-windows](../t3-usage-windows/SKILL.md) — confirm a window really
reset before resuming blocked threads. GUI views: `cswap list`, the CodexBar menubar (shows % left).

Collection and cache live in `scripts/lib/t3_limits.py`, shared with spawn routing.
`T3CODE_HOME` selects both settings and cache (default `~/.t3`).
