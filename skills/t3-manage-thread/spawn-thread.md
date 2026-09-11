# Spawning a thread (t3-spawn-thread)

```bash
t3-spawn-thread --title "Short title" -- "<task brief>"
```

Uses the current git root (registers it as a T3 project if needed), inherits the
calling thread's model/thinking and uses capacity-aware Claude profile selection
(terminal fallback: project default,
high), full-access in the local checkout, focuses T3 Code. Refuses to inherit
from a thread in another T3 project unless `--allow-cross-project-source` — an
accidental inherit silently runs the work under the wrong project/provider.

## 🏓 round-trip workers

`--title "🏓 <task>"` does two things:

1. Appends the ping-back footer to the brief (resolved parent id; a report
   never hides a visible orchestrator). Without an address a worker
   silently ends in its own thread (2026-09-02); the footer is deterministic for *appending*, not for compliance — `t3-fleet --stalled` (`pinged_back`) is the detector. `--dry-run` shows the footer.
2. Hides the thread while it runs; the agent keeps working
   ([hide-thread.md](hide-thread.md)). Override `--hide` / `--no-hide`;
   failing to arm is a warning, not a failure.

Nothing here settles the worker. After its report is verified:
`t3-settle-thread --wait THREAD_ID`.

## Fire-and-forget: `--settle-when-done`

For standalone work nobody needs to verify (e.g. a `yt-ingest` batch): hides the
thread while it runs and appends a footer that makes the worker run
`t3-settle-thread --self` as its last tool call ([settle-thread.md](settle-thread.md#settle-yourself-then-settle-this-thread)).
Refused together with a 🏓 title — round-trip workers are settled by their
orchestrator. Compliance detector is the same as for ping-backs: a thread still
in "needs you" after it finished didn't run the footer.

An explicit `--title` is hard-set (no `titleSeed`, re-asserted via
`thread.meta.update`) so the emoji survives T3's auto-titler. No `--title` →
Luna auto-titles from the first 72 chars.

## Profiles, models, briefs

Antigravity: `--model gemini` selects provider `antigravity` and
`gemini-3.8-flash-high`. `--profile antigravity` also defaults to Flash High when
switching from another provider. Flash thinking lives in the model ID:
`--thinking low|medium|high` selects its suffix; no separate effort option is sent.
Explicit full model IDs work too. T3's Google login is separate from native `agy` login.

`--profile` / `--model` / `--thinking` and their aliases: `--help`. When limits are
tight, `t3-limits` ([limits.md](limits.md)) shows the same cached usage used by routing. Pass
`--thinking` **only when the user names a level** — an explicitly chosen model
otherwise gets its house default (sol/opus high · fable/astra medium · haiku low),
which is the policy we want.

Long task: write the spec to a markdown file, keep the brief to path + locked
decisions + verification expectation. Inline briefs are shell arguments — the
backtick / `$(...)` rule in [cross-thread-ping.md](cross-thread-ping.md) applies.

`T3 provider is missing or disabled: codex` while the UI shows it enabled → the
settings entry was deleted ("Reset to defaults"); the helper mirrors T3's
built-in fallback, so fix the script, not settings.json. Don't substitute
`claude -p`: T3 does not discover arbitrary Claude sessions.

## Screenshots / images in a brief

No first-class attachments: the composer uploads via a WebSocket RPC, and a
`thread.turn.start` carrying a hand-made attachment id is rejected
(`invalid_command`, 2026-09-08). Copy the image to a stable path (e.g.
`/tmp/<topic>-<date>.jpg`, not `~/.t3/userdata/attachments/` which the user may
clear) and put the path in the brief; every harness can `Read` it. Verified:
workers do open the file when the brief names it.

## Automatic profile routing

Omitted `--profile` (or `auto`) selects among enabled Claude accounts after resolving
the requested/inherited model. Explicit profiles, including `T3_SPAWN_PROVIDER`,
win unchanged (`--profile claude` still means the built-in `claudeAgent` account).
Model, thinking and cross-project checks retain their existing rules.

With multiple Claude accounts, reuse `t3-limits` reads/cache; no extra setup.
Exclude exhausted session, weekly and matching model-only caps. Rank fresh accounts
by their worst window's pace room, then minimum headroom. Ties prefer the inherited
account, then instance ID. Paid overage never adds capacity or changes billing settings.

Fresh capacity beats unknown/stale usage. With only unknown candidates, prefer the
inherited account, then instance ID, and print that capacity is unverified. A stale
exhausted cap remains excluded until its reset; a past reset is unknown, not proof
of replenishment. If every candidate is exhausted, stop before creating a thread;
`--profile NAME` is an intentional override. Usage can change after selection.

A single Claude profile skips polling. Other providers retain existing selection:
CodexBar cannot attribute quota to multiple T3 instances. Monthly overage spend caps
are not subscription windows and are not a routing signal. Missing model caps cannot
be inferred. Implementation: `scripts/lib/profile_routing.py`; shared collection,
parsing and cache: `scripts/lib/t3_limits.py` (also used by the `t3-limits` CLI).
