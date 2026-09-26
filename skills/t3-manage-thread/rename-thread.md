# Renaming a thread (t3-rename-thread)

Flags: `t3-rename-thread --help` (`--prefix`, `--wait`, `--dry-run`). Same
`thread.meta.update` dispatch as `t3-spawn-thread --title`; since T3 v0.0.42 a
manual title is marked `source="manual"` and the auto-titler never overwrites it.

Know the name at spawn time → pass `--title` to `t3-spawn-thread` instead. Rename
is for existing or auto-titled threads. `--wait` exists because prefixing an
auto-titled thread too early prefixes the placeholder (the current title comes
from the eventually consistent SQLite projection). Not a settle/snooze: the
session keeps running. Retire this helper once native agent-side rename ships
([upstream-checkpoint.md](upstream-checkpoint.md)).
