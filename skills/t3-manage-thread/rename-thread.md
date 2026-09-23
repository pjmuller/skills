# Renaming a thread (t3-rename-thread)

```bash
t3-rename-thread THREAD_ID -- "New title"   # hard-set; --prefix / --wait / --dry-run in --help
```

Same `thread.meta.update` dispatch that `t3-spawn-thread --title` uses. Since v0.0.42
(#10720) a manual title sets `titleState.source="manual"` and the auto-titler never
overwrites it (before: it only skipped titles that still equalled their seed). Native
agent-side rename is accepted upstream (#11968; PR #12018 closed unmerged 2026-09-19, V2 freeze) — retire this helper when
`t3_thread_update` shows up in the agent tool list.
`--wait` exists because prefixing an auto-titled thread too early prefixes the placeholder;
the current title is read from the SQLite projection (eventually consistent, seconds).

When you already know the final name at spawn time, pass `--title` to `t3-spawn-thread`
instead — one call, no wait. Rename is for threads that already exist or that were
auto-titled. Not a settle/snooze: the session keeps running.
