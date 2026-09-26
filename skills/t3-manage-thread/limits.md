# Rate-limit windows (t3-limits)

Flags: `t3-limits --help` (`--markdown` for a routing decision, `--json` for
scripts, `--fresh` skips the cache). Code: `scripts/lib/t3_limits.py`, shared
with [spawn routing](spawn-thread.md#automatic-profile-routing).

Glossary:
- Percentages are **used** (CodexBar's menubar shows % left).
- `session` = 5 h rolling window (starts at its first request, not on the clock) ·
  `weekly` = 7-day cap · `<Model> only` = per-model weekly sub-cap.
- `pace` = share of the window already elapsed (what an even load would have
  used); `room` = pace − used: **+20** = spare capacity, **−20** = burning ahead
  of pace. No pace for a stale window (no reset / reset in the past).
- Plan label = `rateLimitTier`, plus `(subscriptionType)` when they disagree
  (e.g. `max_20x (pro)`); both come from the local credential written at login,
  so a wrong tier means re-login that home.

Source per enabled T3 provider instance, so each row is the account T3 would run:
- Claude: Keychain item `Claude Code-credentials`, suffixed
  `-<sha256(config dir)[:8]>` when the instance sets `config.homePath` →
  Anthropic OAuth usage endpoint.
- Codex: `<homePath>/auth.json` (empty = `~/.codex`) → ChatGPT usage endpoint.
  The login e-mail is shown so a mis-assigned home is visible. Only top-level
  windows; API-key logins have none.

Behaviour worth knowing:
- Tokens are never printed or refreshed (a refresh would rotate the CLI's own
  copy); an expired one reports itself and the other accounts still report.
- The endpoints are shared with other pollers and often 429. Last good payloads
  are cached in `$T3CODE_HOME/userdata/t3-limits-cache.json` (no tokens), bound
  to home + account id, served fresh for 90 s and as marked-stale fallback up to
  15 min. A cached exhausted window stays until its reset so routing keeps
  excluding it. `T3_LIMITS_DEBUG=1` traces cache hits.
- Paid overage is never shown or counted as capacity.

Related: [t3-usage-windows](../t3-usage-windows/SKILL.md) confirms a window
really reset before resuming blocked threads.
