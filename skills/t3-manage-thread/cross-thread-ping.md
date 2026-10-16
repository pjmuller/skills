# Cross-thread ping (t3-ping-thread)

Flags: `t3-ping-thread --help`. Dispatches a `thread.turn.start` into the target
(same call as the UI composer): it arrives as a normal **user turn** and wakes
that agent on the target's own model. No provider-facing send tool exists yet
([upstream-checkpoint.md](upstream-checkpoint.md)).

- **Quoting trap (one home for this rule):** never put backticks or `$(...)` in
  a message or brief; the calling shell expands them first. Long content →
  markdown file, pass its path.
- **Cross-project pings are refused** unless `--allow-cross-project`: a ping is
  indistinguishable from a typed message, so a wrong target silently derails
  someone else's work. Resolve one exact id; never ping guesses.
- A ping never settles or hides anything. On T3 ≥ 0.1.0 use `t3_thread_send`.
- Batch routine updates; prefer worker milestone reports over status-check pings.
  After verifying a report, settle the worker rather than pinging "thanks".
- **Ping-back address**: the 🏓 spawn footer already carries the parent's T3 id
  (Claude session / `$CODEX_THREAD_ID` are **not** T3 thread ids) —
  [spawn-thread.md](spawn-thread.md).
- Confirm receipt from your own inbox (the user turn that woke you), not
  `t3-read-thread`: its SQLite snapshot trails the live inbox by a beat.

## Reuse a thread on another model

Reuse an existing thread when its context is the asset (planner → reviewer of
that plan, builder → follow-up fix, reviewer → re-review); start a new thread
when the task is unrelated (stale context costs tokens and anchors judgment).

```bash
t3-ping-thread --thread <id> --model sol -- "Review /abs/path/brief.md"   # Astra planner → Sol reviewer
t3-ping-thread --thread <id> --model opus --thinking high -- "…"          # Fable → Opus high
t3-ping-thread --thread <id> --model opus --no-turn                       # switch only, next turn uses it
```

- **Same provider account only.** The switch keeps the thread's `instanceId`
  (account, credentials, Codex home); Claude ↔ Codex or another account is
  refused — spawn a new thread instead ([spawn-thread.md](spawn-thread.md)).
- History continues: T3 resumes the same provider session on the new model
  (Claude restarts with its resume cursor; Codex switches per turn).
- Persisted with native `thread.meta.update`: later plain pings and the composer
  keep the new model. `turn.start`'s own `modelSelection` is per-turn only, so a
  raw turn without the meta update reverts on the next plain ping.
- `--model` without `--thinking` → the model's house effort; `--thinking` alone
  keeps the model. Aliases, floor and effort names match `t3-spawn-thread`.
- `--dry-run` prints old → new selection. A running turn finishes on the old model.
- Attest the real model when it matters: Claude transcript `message.model`
  (`~/.claude/projects/…/<session>.jsonl`), Codex rollout `turn_context.model/effort`,
  T3 `logs/provider/events.<thread>.log` `session.configured`.
