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
- **Visibility is preserved** from T3's live state: a snoozed target gets its
  keeper re-armed (T3 clears the snooze on every incoming turn), a visible one
  stays visible. A ping to a busy worker can still expose it for up to 120 s
  ([hide-thread.md](hide-thread.md)); send urgent corrections anyway. A ping
  never settles anything.
- Batch routine updates; prefer worker milestone reports over status-check pings.
  After verifying a report, settle the worker rather than pinging "thanks".
- **Ping-back address**: the 🏓 spawn footer already carries the parent's T3 id
  (Claude session / `$CODEX_THREAD_ID` are **not** T3 thread ids) —
  [spawn-thread.md](spawn-thread.md).
- Confirm receipt from your own inbox (the user turn that woke you), not
  `t3-read-thread`: its SQLite snapshot trails the live inbox by a beat.
