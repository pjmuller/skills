# Spawning a thread (t3-spawn-thread)

Flags: `t3-spawn-thread --help`. `--dry-run` resolves everything and prints the
routing decision, parent, model, thinking and any appended footer, creating nothing.

Resolution order in `scripts/t3-spawn-thread`: project (current git root,
registered if needed) → parent thread (Claude process ancestry, or
`CODEX_THREAD_ID` inside T3; `--source-thread` overrides) → model/thinking →
account ([routing](#automatic-profile-routing)). The thread runs full-access in
the local checkout and gets focus. Inheriting from a parent in another T3
project is refused unless `--allow-cross-project-source`: an accidental inherit
silently runs the work under the wrong project/provider.

## 🏓 round-trip workers

A `🏓` title appends a ping-back footer with the resolved parent id and hides
the thread while it runs ([hide-thread.md](hide-thread.md); `--hide` /
`--no-hide` override, a failed arm only warns). Workers whose brief merely said
"ping back" silently ended in their own thread, hence the mechanical footer. It
guarantees the instruction, not compliance: `t3-fleet list --stalled`
([t3-maintenance](../t3-maintenance/SKILL.md)) detects workers that never pinged.
Nothing settles the worker: after its report is verified, `t3-settle-thread --wait ID`.

Return path is decided per spawn from what the user asked: 🏓 when the parent
needs the result back (review, delegated implementation, anything it verifies);
📤 standalone when the user said "standalone / separate thread / hand off"
(visible, nobody pings back, never hidden or settled by helpers). Unclear →
**🏓**; the user can promote it. A thread's own mode never propagates to what it
spawns. Hidden ≠ stopped; settle and archive both stop a session, so only snooze
hides a live worker.

## Fire-and-forget: `--settle-when-done`

For standalone work nobody needs to verify. Hides the thread and appends a
footer: on a **clean outcome** the worker runs `t3-settle-thread --self` as its
last call ([settle-thread.md](settle-thread.md#settle-yourself-then-settle-this-thread));
blocked/partial work, material failures, unresolved findings or user decisions →
it unhides itself and ends with a terse report. Intent: the human is the
bottleneck; a verified, finished thread shouldn't cost a glance, and a
correction already folded into the deliverable is still clean. Use it when the
user says "…and settle it when done". Refused with a 🏓 title (the orchestrator
settles those). A finished thread still in "needs you" didn't run the footer.

## Titles, models, briefs

- **Title**: explicit `--title` is hard-set (no `titleSeed`, then
  `thread.meta.update`) so the emoji survives T3's auto-titler; without it the
  auto-titler names the thread from the first 72 prompt chars.
- **Thinking**: no `--model` → inherit the parent's model and effort (terminal:
  project default, else Opus high). An explicit `--model` gets its house effort
  (sol/opus high · fable/astra medium · haiku low; case table in the script).
  Pass `--thinking` only when the user names a level.
- **`sol` / `opus` aliases** pick the newest version in T3's local model
  manifest; for Sol a fresh (< 1 h) per-account Codex model cache is
  authoritative, and a fresh cache without Sol stops the spawn. Full model IDs
  stay pinned. `scripts/lib/model_resolution.py`, no LLM call.
- **Gemini**: `--model gemini` → Antigravity Flash High; thinking is encoded in
  the model ID suffix (`--thinking` swaps it). T3's Google login is separate from
  native `agy` login.
- **Brief**: long task → spec in a markdown file, brief = path + locked decisions
  + verification expectation ([dispatch-workers.md](dispatch-workers.md)).
  Inline briefs obey the [quoting rule](cross-thread-ping.md).
- **Images**: no first-class attachments (a `thread.turn.start` with a hand-made
  attachment id is rejected). Copy the image to a stable path such as `/tmp/…`
  (not `~/.t3/userdata/attachments/`, which the user may clear) and name it in
  the brief; workers do open it.
- `T3 provider is missing or disabled` while the UI shows it enabled → fix the
  built-in defaults in `scripts/lib/profile_registry.py`, not settings.json.
  Don't substitute `claude -p`: T3 does not discover arbitrary Claude sessions.

## Automatic profile routing

The one home for account-routing policy. Omitted `--profile` (or `auto`) picks among
the enabled T3 instances of the resolved model's driver — Claude **and** Codex,
one policy (`scripts/lib/profile_routing.py`, usage from `scripts/lib/t3_limits.py`,
the same cached numbers `t3-limits` prints; see [limits.md](limits.md) for pace/room).
Explicit `--profile` or `T3_SPAWN_PROVIDER` wins unchanged and never polls; it is
also the override when every account is exhausted.

- **Excluded**: any relevant window at 100 % until its reset, including a
  `<Model> only` cap for the requested family.
- **Unknown** (unreachable, stale, missing numbers): ranked after every verified
  account, picked only when nothing is verified.
- **Ranking**: worst window's pace room first, plus a small bonus for weekly
  windows about to reset (use-it-or-lose-it), then minimum headroom. `[tight]`
  (≥ 90 % used) is a label, not a demotion: a weekly at 92 % resetting in two
  hours beats one burning far ahead of pace.
- **Ties** keep the inherited account (on a driver switch: its sibling, same
  display name minus the driver word), then instance id.
- Paid overage is never capacity. Every automatic route prints its reasoning on
  stderr.

Accepted trade-offs: bottleneck ranking ignores a strong second window, and
near-simultaneous spawns are not spread across equal accounts (the next read,
≤ 90 s later, sees real consumption). No reservation or prediction of in-flight work.

Profile names come from T3's native registry on every call (exact id, else a
unique case-insensitive id/display-name match narrowed by `--model`'s driver),
so adding accounts in T3 needs no helper change. Drivers without per-instance
usage (Antigravity, forks) keep the inherited account or its unique sibling.
Existing threads are separate: changing their instance restarts the session and
T3 rejects Codex continuation across different homes — don't patch thread
metadata to migrate running work.
