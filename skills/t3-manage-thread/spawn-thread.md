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

**Model floor:** OpenAI below `gpt-6` and Sol below 6.1 are refused ("5.5" in a brief means
Opus 5.5). Deliberately older, e.g. a cyber task the current model refuses: `--allow-old-model "<reason>"`.

## 🏓 round-trip workers

A `🏓` title appends a ping-back footer with the resolved parent id and hides
the thread while it runs ([hide-thread.md](hide-thread.md); `--hide` /
`--no-hide` override, a failed arm only warns). Workers whose brief merely said
"ping back" silently ended in their own thread, hence the mechanical footer. It
guarantees the instruction, not compliance: `t3-fleet list --stalled`
([t3-maintenance](../t3-maintenance/SKILL.md)) detects workers that never pinged.
Nothing settles the worker: after its report is verified, `t3-settle-thread --wait ID`.

Return path is decided per spawn from what the user asked: 🏓 when the result
feeds back into **this thread's deliverable** (review, delegated sub-step,
anything this thread still has to verify before it can finish); 📤 standalone
(visible by default, nobody pings back; conditional mode below is opt-in) when:
- the user said "standalone / separate thread / separate process / own job /
  hand off", or
- the task is a **new, orthogonal scope** the user will follow on its own (new
  tooling, a new feature), even if it also happens to re-check something this
  thread built. Test: would this thread's answer change when the result lands?
  No → 📤.
Unclear *sub-step* of the current task → **🏓**; the user can promote it.
Misfired? Convert in place, don't respawn: `t3-hide-thread --unhide`, rename to
`📤 …`, ping the thread that it is standalone and must ignore its ping-back footer. A thread's own mode never propagates to what it
spawns. Hidden ≠ stopped; settle and archive both stop a session, so only snooze
hides a live worker.

## Fire-and-forget: `--settle-when-done`

Conditional self-settlement for standalone work: use an explicit user request or
an authorized routing policy recorded in the brief, never standalone status alone.
The helper appends the canonical completion footer in `scripts/t3-spawn-thread`;
that footer defines clean completion and exceptions. Default visibility is hidden;
`--settle-when-done --no-hide` keeps the thread visible while running. On clean
delivery the worker runs `t3-settle-thread --self` as its last tool call
([settle-thread.md](settle-thread.md#settle-yourself-then-settle-this-thread));
otherwise it stays open and unhides if needed. Explicit keep-open or later user
instructions win. Refused with a 🏓 title: the parent settles those after verification.

## Titles, models, briefs

- **Title**: explicit `--title` is hard-set (no `titleSeed`, then
  `thread.meta.update`) so the emoji survives T3's auto-titler; without it the
  auto-titler names the thread from the first 72 prompt chars.
- **Thinking**: no `--model` → inherit the parent's model and effort (terminal:
  project default, else Opus high). An explicit `--model` gets its house effort
  (sol/opus high · fable/astra medium · haiku low; family-glob `case` in the
  script, so new versions match; other models inherit).
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
- **Score** (PJ, 2026-09-27; plan-weighted 2026-10-08): the tightest relevant
  weekly-class window's **headroom per hour until its reset** (`headroom% /
  max(hours, 1)`; an untouched window counts as 100 % over its full length),
  **times the plan multiplier** stated in the label (`max_20x` → 20, `max_5x` → 5;
  a label without one — Claude `pro`, Codex `pro`/`prolite`, `unknown` — → 1, so
  such accounts stay unweighted among themselves). Highest wins. This is what a
  human reads off the reset times and plan sizes: the first weekly cap to expire
  gets priority, growing continuously as the reset nears, but 25 % left on a 5x
  is a quarter of 25 % left on a 20x.
- **Session**: 5 h windows never enter the score, but a session that is tight
  ranks after the ones with room. Tight = `multiplier × session headroom %` below
  10 % of the largest verified plan's session (20x beside 20x: ≥ 90 % used, the
  old rule; 5x beside 20x: ≥ 60 % used; 1x beside 20x: always, i.e. overflow
  only — the routing output says so). Excluded or unknown accounts do not set
  the bar.
- **Ties** keep the inherited account (on a driver switch: its sibling, same
  display name minus the driver word), then instance id.
- Paid overage is never capacity. Every automatic route prints its reasoning on
  stderr.

Accepted trade-offs: bottleneck ranking ignores a strong second window, and
near-simultaneous spawns are not spread across equal accounts (the next read,
≤ 90 s later, sees real consumption). No reservation or prediction of in-flight work.

For a huge or batched job, check `t3-spawn-thread --dry-run`, `t3-limits`, and
the active fleet before launch. Plan weights come from the login label, which
can lag a billing change (Claude) or state no multiplier (Codex `pro`/`prolite`):
an unweighted or stale-labelled account is ranked by percentage alone, so stage
huge jobs on it one at a time and recheck actual consumption. Explicit
`--profile` still wins.

Profile names come from T3's native registry on every call (exact id, else a
unique case-insensitive id/display-name match narrowed by `--model`'s driver),
so adding accounts in T3 needs no helper change. Drivers without per-instance
usage (Antigravity, forks) keep the inherited account or its unique sibling.
Existing threads are separate: changing their instance restarts the session and
T3 rejects Codex continuation across different homes — don't patch thread
metadata to migrate running work.
