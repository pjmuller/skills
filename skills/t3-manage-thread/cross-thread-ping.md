# Cross-thread ping (t3-ping-thread)

```bash
t3-ping-thread --thread TARGET_THREAD_ID --from "sender label" -- "status message"
```

Dispatches a `thread.turn.start` into the target (T3's own local orchestration
API, same call as the UI composer): it arrives as a normal **user turn** and
wakes that agent, using the target's own model. No provider-facing send tool
exists as of v0.0.42. Flags (retries, cross-project, hide overrides): `--help`.

- **Quoting trap (one home for this rule):** never put backticks or `$(...)` in
  a message or brief — the calling shell expands them first (2026-08-31). Long
  content → write a markdown file and pass its path.
- Visibility is preserved from T3's live state, not the title: a snoozed target
  gets its keeper re-armed ([hide-thread.md](hide-thread.md) — T3 clears the
  snooze on the incoming turn), a visible target stays visible. A ping never
  settles anything.
- Batch routine updates; prefer worker milestone reports over status-check pings.
  On a running Codex turn, a received ping can leave turn timestamps unchanged:
  T3 treats the newer message as queued and disables Snooze (UI and API) for
  up to 120s. Each new ping restarts that window. Send urgent corrections anyway;
  do not delay delivery or interrupt work just to keep the sidebar quiet.
- Cross-project pings are refused by default (`--allow-cross-project`): a ping
  is indistinguishable from a typed message, so a wrong target silently
  derails someone else's work. Resolve one exact id; never ping guesses.
- Ping-back address: the 🏓 spawn footer already carries the parent id
  (mapped from the Claude ancestor session / Codex `$CODEX_THREAD_ID`, which are
  **not** T3 thread ids) — see [spawn-thread.md](spawn-thread.md).
- Confirm receipt from your own inbox (the user turn that woke you), not from
  `t3-read-thread`: its SQLite snapshot trails the live inbox by a beat.
