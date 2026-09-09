# Rate-limit windows (t3-limits)

```bash
t3-limits                   # every Claude profile + Codex, aligned, Europe/Brussels
t3-limits --profile work  # substring of instance id / display name / "codex"
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

Chain: T3 `settings.json` → enabled `claudeAgent` instances → per-profile macOS Keychain item
(`Claude Code-credentials`, or `-<sha256(absolute config dir)[:8]>` when `config.homePath` is set) →
`GET api.anthropic.com/api/oauth/usage`. Codex comes from `codexbar usage --provider codex --format
json`; if CodexBar is missing only its own row degrades.

Percentages are **used** — the inverse of CodexBar's menubar "% left". `session` = the 5h rolling
window (resets 5h after its first request, not on the clock) · `weekly` = the 7-day cap ·
`<Model> only` = per-model weekly sub-cap (`weekly_scoped`).

Extra usage (paid overage) is never shown and never a routing input. It's off by default; when the user
enables it on a profile it is a deliberate decision to keep code running there, so the spend is
noise for pace decisions.

Cached: the usage endpoint is shared with other pollers (CodexBar, `t3-usage-windows topup`), so
it answers 429 often. Each profile's last good payload is kept in `~/.t3/userdata/t3-limits-cache.json`
(mode 0600, no tokens): younger than 90 s it is served without a call (`--fresh` bypasses), and on a
429/network error one short retry (honouring `Retry-After`) is followed by the cached value if it is
under 15 min old — shown as `(cached 3m ago)` / `"stale": true` with `fetched_at`. Only without a
usable cache does the account report `HTTP 429`. `T3_LIMITS_DEBUG=1` traces cache hits on stderr.

Tokens are never printed and never refreshed (a refresh would rotate Claude Code's own copy); an
expired one prints `token expired — run any turn in that profile to refresh` and the rest still report.

Related: [t3-usage-windows](../t3-usage-windows/SKILL.md) — confirm a window really
reset before resuming blocked threads. GUI views: `cswap list`, the CodexBar menubar.
