# Rate-limit windows (t3-limits)

```bash
t3-limits                   # every Claude profile + Codex, aligned, Europe/Brussels
t3-limits --profile dentai  # substring of instance id / display name / "codex"
t3-limits --markdown        # one table (used · pace · room · resets) — paste into a routing decision
t3-limits --json            # rows: account, instance_id, window, used_percent, pace_percent, room_percent, resets_at, resets_in_seconds
                            # an unreachable account yields one row {account, instance_id, window: null, error} — "unknown", not "stale"
```

`pace` = % of the window already elapsed = what an evenly spread load would have used by now.
`room` = pace − used: **+20** = 20 points under pace (spare capacity, steer work here), **−20** =
burning faster than even. Session pace is relative to the 5h window (resets 5h after its first
request), weekly/`<Model> only` to the 7-day window. No pace when the window is stale (`no reset`
/ reset in the past — nothing requested since). Codex shows only its top-level windows (Spark
sub-windows dropped as noise). Repo-local consumer: `pjroute` in macbook_setup.

Chain: T3 `settings.json` → enabled `claudeAgent` instances → per-profile macOS Keychain item
(`Claude Code-credentials`, or `-<sha256(absolute config dir)[:8]>` when `config.homePath` is set) →
`GET api.anthropic.com/api/oauth/usage`. Codex comes from `codexbar usage --provider codex --format
json`; if CodexBar is missing only its own row degrades.

Percentages are **used** — the inverse of CodexBar's menubar "% left". `session` = the 5h rolling
window (resets 5h after its first request, not on the clock) · `weekly` = the 7-day cap ·
`<Model> only` = per-model weekly sub-cap (`weekly_scoped`).

Extra usage (paid overage) is never shown and never a routing input. It's off by default; when PJ
enables it on a profile it is a deliberate decision to keep code running there, so the spend is
noise for pace decisions.

Tokens are never printed and never refreshed (a refresh would rotate Claude Code's own copy); an
expired one prints `token expired — run any turn in that profile to refresh` and the rest still report.

Related: [t3-resume-limited](../../../.agents/skills/t3-resume-limited) — confirm a window really
reset before resuming blocked threads. GUI views: `cswap list`, the CodexBar menubar.
