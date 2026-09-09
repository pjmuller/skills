# Renaming a thread (t3-rename-thread)

```bash
t3-rename-thread THREAD_ID -- "New title"   # hard-set; --prefix / --wait / --dry-run in --help
```

Same `thread.meta.update` dispatch that `t3-spawn-thread --title` uses. T3's auto-titler
only replaces a title that still equals its seed, so a renamed thread keeps its name.
`--wait` exists because prefixing an auto-titled thread too early prefixes the placeholder;
the current title is read from the SQLite projection (eventually consistent, seconds).

When you already know the final name at spawn time, pass `--title` to `t3-spawn-thread`
instead — one call, no wait. Rename is for threads that already exist or that were
auto-titled. Not a settle/snooze: the session keeps running.
