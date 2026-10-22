# Model and account routing

`t3-pick-instance MODEL [ALLOWED_IDS_CSV]` prints `<instanceId> <modelId> <effort>`: the input for
`delegate_task` `target` and `t3_thread_launch` `modelSelection` (`t3-relay` uses it too).

## Models

Provider-only helper input (`t3-pick-instance openai|codex`, relay/scheduler `--model codex`)
selects Astra; `claude|anthropic` selects Opus. Explicit models always win: direct Sol code
review and Astra-selected scoped Sol children remain valid. House effort and capacity routing
apply after model selection; personal policy lives in the `instructions` config slot.

Native T3 APIs do **not** use these helper defaults. Always pass the resolved model/account
and effort in `delegate_task.target` / `t3_thread_launch.modelSelection`. A provider-only
`delegate_task` inherits the model on the same instance, or takes the provider's first model
on another instance (which can be Sol). An omitted launch selection inherits the caller, or
uses the project default outside a thread. This skill does not intercept native calls.

- Aliases: `sol` / `opus` pick the newest version in T3's model manifest (`lib/model_resolution.py`);
  `fable` → `claude-fable-5-1`, `astra` → `gpt-6-astra`, `luna` → `gpt-6-luna`, `haiku` →
  `claude-haiku-5-5`, `gemini` → Antigravity Flash High. Full ids pass through.
- **Floor**: OpenAI below `gpt-6` and Sol below 6.1 are refused ("5.5" in a brief means Opus 5.5).
- **House effort**: sol/opus high · fable/astra medium · haiku low. Pass another effort only when
  the user names a level. Option id: `reasoningEffort` (Codex) or `effort` (Claude).
- Valid models and options per account: `orchestrator_capabilities`.

## Accounts

Model, account and repository are independent. A generic model request never pins an
account or implies product affinity. Resolve immediately before **each** spawn; do not
reuse an earlier pick for a batch. Native provider children inherit the parent account
and bypass this router: stage large fan-outs or use explicitly routed `delegate_task`.

One policy for Claude and Codex (`lib/profile_routing.py`, usage from `lib/t3_limits.py`, the numbers
`t3-limits` prints; [limits.md](limits.md)). The user named an account → use that instance id
(`t3-list-profiles` for exact ids), and check `t3-limits` when it may be exhausted. They named
several → `t3-pick-instance MODEL a,b`. Before a huge or batched job, check `t3-limits` and the
active fleet, and stage it on small-tier accounts one at a time.

- **Excluded**: any relevant window at 100 % until its reset, including a
  `<Model> only` cap for the requested family.
- **Unknown** (unreachable, stale, missing numbers): ranked after every verified
  account, picked only when nothing is verified.
- **Score** (PJ, 2026-09-27; plan-weighted 2026-10-08): the tightest relevant
  weekly-class window's **headroom per hour until its reset** (`headroom% /
  max(hours, 1)`; an untouched window counts as 100 % over its full length),
  **times the plan tier** ([limits.md](limits.md): label `max_20x` → 20, else the
  private multiplier map, e.g. Codex `prolite` → 5, else `1x?` → 1). Highest wins. This is what a
  human reads off the reset times and plan sizes: the first weekly cap to expire
  gets priority, growing continuously as the reset nears, but 25 % left on a 5x
  is a quarter of 25 % left on a 20x.
- **Session**: 5 h windows never enter the score, but a session that is tight
  ranks after the ones with room. Tight = `multiplier × session headroom %` below
  10 % of the largest verified plan's session (20x beside 20x: ≥ 90 % used, the
  old rule; 5x beside 20x: ≥ 60 % used; 1x beside 20x: always, i.e. overflow
  only — the routing output says so). Excluded or unknown accounts do not set
  the bar. Also tight: a session at least 50% used and ahead of its elapsed-window
  pace. This protects running work before the 90% cliff; it does not reserve quota.
- **Load** (2026-10-22): rank by `score × session left / (1 + live load)`; session
  left = tightest relevant short window's headroom fraction (1 without one). Load per
  instance from T3's store (`lib/fleet_load.py`, read-only): each owner thread with a
  live run counts once on the account its run uses (not the composer), weight 1 or 3
  with `routing-load: heavy` ([workers.md](workers.md#briefs-and-titles)); queued
  runs behind it add nothing, a queue held behind a failed run doesn't count;
  native sub-agents fold into their owner as `max(weight, live natives)`; quiet
  runs still count (flagged); `delegate_task` children count on their own account.
  Starts/30 min are shown, never added. Store missing/unreadable → quota-only,
  with a warning. Only new picks move: running threads keep their account.
  `T3_ROUTING_LOAD=shadow` keeps the quota-only pick and prints the adjusted one.
- **Ties** go to the instance id order (`claudeAgent` preferred).
- Paid overage is never capacity. Every automatic route prints its reasoning on
  stderr, with each reading's actual age (`seen`; cached readings can be minutes
  old) and an **observation gap** when runs ended after that reading (their final
  usage may be missing). It also appends inputs + quota-only and adjusted pick (no
  prompts, titles, tokens) to `t3-routing-decisions.jsonl` beside `settings.json`
  (≤ 256 KB, private, locked against concurrent spawns) for replay, e.g. `jq -c 'select(.quota_pick != .adjusted_pick)'`.


## Temporary override

A private `~/.t3/userdata/t3-routing-override.json` (keep the file in your setup repo, symlink it) bends
automatic routing for a while, e.g. to fill one account before applying a banked limit reset:

```json
{"until": "2026-10-22T18:00:00+02:00", "weekly_cap": 90,
 "prefer": [{"id": "claudeAgent_a", "until": "2026-10-17T17:00:00+02:00"},
            {"id": "claudeAgent_b", "from": "2026-10-17T17:00:00+02:00"}]}
```

The first `prefer` instance that is verified, not session-tight, inside its optional `from`/`until`, and
whose highest relevant weekly-class window (a `<Model> only` cap counts for that model) is under `weekly_cap`
wins outright; otherwise the score above decides. Exclusion, unknown usage and an account the user named still win; `ALLOWED_IDS_CSV` applies it among those. The cap is a
preference cutoff, not a ceiling: running threads keep burning, ordinary routing may still pick the
account above it. Top-level `until` (UTC offsets required) is mandatory; expired or invalid → ordinary routing,
noted in the reason. Dry runs print why each entry was taken or skipped. Disable: delete the file.

Accepted trade-offs: weekly ranking ignores a strong second window. Load is a
coarse count, not a token forecast. Sequential spawns spread because each accepted
launch is a live run before the next pick; truly simultaneous picks can still
collide (no reservation ledger). Usage that finished after a reading is only
warned about, not re-probed.

