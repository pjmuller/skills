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

Return path is decided per spawn, from what the user asked for that spawn:
🏓 when the parent needs the result back (review, delegated implementation, any
sub-task the parent verifies); 📤 standalone when the user said "standalone /
separate thread / hand off" (visible, nobody pings back, never hidden or settled
by helpers). Not clearly said → **default to 🏓**; the user can always promote
it. A thread's own mode never propagates: a standalone thread is a clean slate
for what it spawns. Hidden ≠ stopped, and neither settle nor archive can hide a
live worker (both stop its session): use snooze ([hide-thread.md](hide-thread.md)).

## Fire-and-forget: `--settle-when-done`

For standalone work nobody needs to verify (e.g. a `yt-ingest` batch): hides the
thread while it runs and appends a footer that makes the worker settle itself
(`t3-settle-thread --self`, last tool call — [settle-thread.md](settle-thread.md#settle-yourself-then-settle-this-thread))
**only on a clean outcome**. Intent: the human is the bottleneck, so a thread that
did exactly what was asked and learned nothing they need shouldn't cost them a
glance. Anything that needs them — blocked, partial, a surprising finding, a
decision or follow-up — stays: the worker unhides itself and ends with a terse
report instead. Use it whenever the user says "…and settle it when done" for a
spawned thread; the same judgement applies to "…then settle this thread".
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

`--profile` / `--model` / `--thinking` and their aliases: `--help`;
`t3-list-profiles` prints the enabled accounts per ecosystem with the exact
`--profile` value (use it when the user names an account, so no typos). When limits are
tight, `t3-limits` ([limits.md](limits.md)) shows the same cached usage used by routing. Pass
`--thinking` **only when the user names a level** — an explicitly chosen model
otherwise gets its house default (sol/opus high · fable/astra medium · haiku low),
which is the policy we want.

Long task: write the spec to a markdown file, keep the brief to path + locked
decisions + verification expectation ([dispatch-workers.md](dispatch-workers.md) for the
full brief shape and title rules). Inline briefs are shell arguments — the
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

Omitted `--profile` (or `auto`) selects among the enabled T3 instances of the resolved
model's driver — Claude **and** Codex, one policy. Explicit profiles, including
`T3_SPAWN_PROVIDER`, win unchanged and never poll (`--profile claude` still means the
built-in `claudeAgent` account). Model, thinking and cross-project checks keep their rules.

Policy (`scripts/lib/profile_routing.py`, usage from `t3_limits.py` — the same numbers
`t3-limits` prints, 90 s cache):

- **Excluded**: any relevant window at 100 % until its reset (session, weekly, any other
  top-level Codex window, and a `<Model> only` cap for the requested family). A cached
  exhausted cap stays excluded even after the cache is too old to serve as a reading.
- **Unknown**: unreachable account (429, expired token, no login), stale reading, missing
  percentage, past reset. Ranked after every verified account; picked only when nothing
  is verified, with "capacity unverified" in the reason.
- **Ranking**: worst window's pace room (pace − used) first, then minimum headroom. This is
  the whole rule; a window ≥ 90 % used is labelled `[tight]` but not demoted — a weekly at
  92 % that resets in two hours is still the right pick over one burning far ahead of pace.
  Ties prefer the inherited account (on a driver switch: its sibling, same display name
  minus the driver word), then the instance id.
- **All exhausted** → the spawn refuses before creating a thread; `--profile NAME` is the
  intentional override. Usage can change after selection; no reservation or prediction of
  in-flight work, and paid overage never counts as capacity.

Every automatic route prints its decision block on stderr (also under `--dry-run`):

```
Profile routing for claude-fable-5-1 (usage cached ≤90 s; explicit --profile NAME bypasses this):
  claudeAgent             session 3% (room +25) · weekly 35% (room +16) · Fable only 50% (room +1)
  claudeAgent_kampkompas  session 6% (room +22) · weekly 17% (room -4) · Fable only 28% (room -15)
  claudeAgent_dentai      session 6% (room +22) · weekly 18% (room +15) · Fable only 31% (room +2)  ← selected
  → claudeAgent_dentai: best bottleneck room (Fable only +2)
```

Known trade-offs of the single rule: bottleneck ranking ignores a strong second window
(weekly +45 with session −2 loses to weekly +16 with session +5), and nothing spreads
near-simultaneous spawns across equal accounts — the next read (≤ 90 s later) sees the
real consumption instead.

Profile names come from T3's native registry on every invocation: exact instance ID first,
then a unique case-insensitive ID/display-name match. An explicit model narrows name
matches to its driver (`--profile beta --model astra` selects Codex Beta even when Claude
Beta exists). Disabled profiles are excluded. Ambiguous names fail; use an exact ID. Adding
accounts in T3 needs no helper maintenance. Existing threads are separate: changing their
instance restarts the session, and T3 rejects Codex continuation across different shared
homes. Do not patch thread metadata to migrate running work.

Drivers without per-instance usage (Antigravity, forks) keep the inherited account or its
unique sibling; otherwise "Choose --profile". Missing model caps cannot be inferred.
