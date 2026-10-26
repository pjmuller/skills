# Model and account routing

`t3-pick-instance MODEL [ALLOWED_IDS_CSV]` prints `<instanceId> <modelId> <effort>`: the input for
`delegate_task` `target` and `t3_thread_launch` `modelSelection` (`t3-relay` uses it too).

## Models

Provider-only input (`t3-pick-instance openai|codex`, relay/scheduler `--model codex`) selects Astra;
`claude|anthropic` selects Opus. Explicit models always win (direct Sol code review, Astra-assigned
Sol children); no automatic Astra-to-Sol fallback. Personal policy: the `instructions` config slot.

Native T3 calls bypass these defaults: always pass the resolved model, account and effort in
`delegate_task.target` / `t3_thread_launch.modelSelection`. Else a provider-only `delegate_task`
inherits the model on the same instance or takes the provider's first model on another (can be Sol),
and an omitted launch selection inherits the caller (project default outside a thread).

- Aliases: `sol` / `opus` pick the newest version in T3's model manifest (`lib/model_resolution.py`);
  `fable` → `claude-fable-5-1`, `astra` → `gpt-6-astra`, `luna` → `gpt-6-luna`, `haiku` →
  `claude-haiku-5-5`, `gemini` → Antigravity Flash High. Full ids pass through.
- **Floor**: OpenAI below `gpt-6` and Sol below 6.1 are refused ("5.5" in a brief means Opus 5.5).
- **Small models** (haiku, luna) never run a standalone thread unasked: `t3-relay`/`t3-schedule`
  refuse them without `--allow-small-model`; in your own `t3_thread_launch` warn the user, launch
  only if they insist.
- **House effort**: sol/opus high · fable/astra medium · haiku low; another level only when the user
  names one. Option id: `reasoningEffort` (Codex) or `effort` (Claude). Valid models and options per
  account: `orchestrator_capabilities`.

## Accounts

Model, account and repository are independent: a model request never pins an account or implies
product affinity. Pick immediately before **each** spawn, never reuse a pick across a batch. Native
provider sub-agents inherit the parent account and bypass the router: stage large fan-outs or use
routed `delegate_task`s.

User named an account → that instance id (`t3-list-profiles`), checking `t3-limits` when it may be
exhausted; several → `t3-pick-instance MODEL a,b`. Huge or batched job → check `t3-limits` and the
active fleet first, stage it on small-tier accounts one at a time.

Automatic pick (`lib/profile_routing.py`, one policy for Claude and Codex, on the numbers `t3-limits`
prints: [limits.md](limits.md)):

1. **Excluded**: any relevant window at 100 % (incl. a `<Model> only` cap for the requested family)
   until its reset. **Unknown** (unreachable, stale, missing numbers): ranked after every verified account.
2. **Score** = the tightest relevant weekly-class window's headroom per hour until its reset
   (`headroom% / max(hours, 1)`; untouched = 100 % over its full length) × the plan
   [tier](limits.md) multiplier. Soonest-expiring quota wins, more so as the reset nears; 25 % left
   on a 5x is a quarter of 25 % left on a 20x.
3. **Session** (5 h) never enters the score, but a tight session ranks after those with room. Tight =
   `multiplier × session headroom %` below 10 % of the largest verified plan's session (5x beside 20x:
   ≥ 60 % used; 1x beside 20x: always, i.e. overflow only), or ≥ 50 % used and ahead of its elapsed
   pace (protects running work; reserves nothing). Excluded or unknown accounts don't set the bar.
4. **Load**: rank by `score × session left / (1 + live load)` (session left = tightest short window's
   headroom fraction, else 1). Load per instance from T3's store (`lib/fleet_load.py`, read-only):
   each owner thread with a live run counts on the account its run uses (not the composer), weight 1,
   or 3 with `routing-load: heavy` ([workers.md](workers.md#briefs-and-titles)); native sub-agents fold
   in as `max(weight, live natives)`; `delegate_task` children count on their own account; quiet runs
   count (flagged); queued runs, or a queue held behind a failed run, don't. Starts/30 min are shown,
   never added. Unreadable store → quota-only, warned. Only new picks move. `T3_ROUTING_LOAD=shadow`
   keeps the quota-only pick and prints the adjusted one.
5. **Ties**: instance id order (`claudeAgent` first). Paid overage is never capacity.

Every automatic route explains itself on stderr, with each reading's age (`seen`) and an
**observation gap** when runs ended after it (final usage may be missing), and appends inputs +
quota-only and adjusted pick (no prompts, titles, tokens) to `t3-routing-decisions.jsonl` beside
`settings.json` (≤ 256 KB, private, locked) for replay: `jq -c 'select(.quota_pick != .adjusted_pick)'`.

Known limits: weekly ranking ignores a strong second window; load is a coarse count, not a token
forecast; truly simultaneous picks can collide (no reservation ledger; sequential ones spread because
each accepted launch is live before the next pick); usage finished after a reading is only warned about.

## Temporary override

A private `~/.t3/userdata/t3-routing-override.json` (kept in your setup repo, symlinked) bends
automatic routing for a while, e.g. to fill one account before applying a banked limit reset:

```json
{"until": "2026-10-22T18:00:00+02:00", "weekly_cap": 90,
 "prefer": [{"id": "claudeAgent_a", "until": "2026-10-17T17:00:00+02:00"},
            {"id": "claudeAgent_b", "from": "2026-10-17T17:00:00+02:00"}]}
```

The first `prefer` instance that is verified, not session-tight, inside its optional `from`/`until`,
and whose highest relevant weekly-class window (a `<Model> only` cap counts for that model) is under
`weekly_cap` wins; otherwise the score decides. Exclusion, unknown usage and a user-named account still
win; `ALLOWED_IDS_CSV` applies it among those. The cap is a preference cutoff, not a ceiling: running
threads keep burning, ordinary routing may still pick the account above it. Top-level `until` (UTC
offset required) is mandatory; expired or invalid → ordinary routing, noted in the reason. Dry runs
print why each entry was taken or skipped. Disable: delete the file.
