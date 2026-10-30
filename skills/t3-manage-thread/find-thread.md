# Find, read and open past threads

North star: past work is reusable context. Find the thread that already researched or decided
something and continue it, history included, instead of re-explaining or redoing it. Works from
vague or dictated memory.

`t3-find-thread` narrows over a read-only FTS5 cache of T3's `statev2.sqlite`; **you** judge.
Never dump a whole thread into context. Flags: `--help`.

## Workflow

1. **Translate the ask** into filters + 4–8 keyword variants (synonyms, table/file names, error
   strings). Voice-dictated: `--fuzzy` for phonetic terms. `--since` = *active* in the window.
2. **`search`**: full term coverage (`3/4` column) beats raw hits. Sub-agent / delegated threads
   are hidden; `--subagents` includes them.
3. **`peek`** the top 3–5 (first prompts usually settle it).
4. **`grep`** finalists for the distinguishing fact.
5. **Loop ≤3×**: no hits → drop a term, `--fuzzy`, widen `--since`/`--project`. Too many → `--all`,
   `--role user`.
6. **Answer**: top pick + one evidence snippet, runner-ups as short ids. Titles in the output are
   already native T3 chat links.

Gmail URL/id → `t3-mail-link find` ([mail-link.md](mail-link.md)): it resolves
the account and every id form, then calls this search.

Ids: full id or ≥8-char short id. `read <id>` pages a thread's messages in full (`--from`,
`--limit`; live or purged); native `t3_thread_read` also works for live threads.

**Purged threads** live on in the backup archive ([t3-maintenance](../t3-maintenance/SKILL.md#archive-t3-thread-archive));
secrets there read `[redacted:<category>]`. `search` adds it when the live store has no hit with
every term or `--since`/`--until` predate the live store (`--backup on|off` forces); hits show
`_(backup)_`, no T3 link. `grep` and `read --tools` also see archived tool calls (role = tool
name); entry numbers match across commands.

**Revive a purged thread** (T3 can't reopen it): `t3-find-thread read <id> --limit 0 >
~/Downloads/<slug>.md` (every message whole; a `--tools` copy only as a grep-only log, often 10x
larger), then `t3_thread_launch` in the project `peek` shows: "Continuation of purged thread
<title>. Read ~/Downloads/<slug>.md first. Then: <ask>". Verified 2026-10: a fresh agent rebuilt
task, decisions, commits and next step from the export alone.

## Opening

- In T3 chat: `t3-open-thread <id> --link` → `[title](t3-thread://v1/<threadId>)`. Older settled
  target → dead chip, add the plain-text fallback ([settled targets](workers.md#-t3_thread_launch)).
- Desktop app: `t3-open-thread <id>` (only when the user asks).
- HTML reports: `t3code://threads/<env>/<url-encoded threadId>`; `t3-open-thread <id> --dry-run`
  prints it.

Installed with this skill's `scripts/install` (both commands). Fleet work: [t3-maintenance](../t3-maintenance/SKILL.md).
