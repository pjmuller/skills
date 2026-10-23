---
name: t3-find-thread
description: Fuzzy-find a past T3 Code thread by project, time window and topic keywords — deterministic FTS5 narrowing over the local thread store, then LLM judging with progressive disclosure (search → peek → grep). Use for "which thread did we…", "find the T3 thread where…", "where did I ask about X", "that conversation last month about Y", "/t3-find-thread".
---

# T3 Find Thread

`scripts/t3-find-thread` narrows over a read-only FTS5 cache of T3's `statev2.sqlite`; **you** judge.
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

Gmail URL/id → `t3-mail-link find` ([mail-link.md](../t3-manage-thread/mail-link.md)): it resolves
the account and every id form first, then calls this search.

Thread ids: full id or ≥8-char short id (the thread's UUID). Reading a thread in full → native
`t3_thread_read`.

**Purged threads** live on in the backup archive ([t3-maintenance](../t3-maintenance/SKILL.md#archive-t3-thread-archive)).
`search` adds it when the live store has no hit or `--since`/`--until` reach before the live store
(`--backup on|off` forces); hits are flagged `_(backup)_` and have no T3 link (the thread is gone).
`peek`/`grep` take their ids as usual; `read <id> [--tools]` replaces `t3_thread_read` for them.
Archived tool calls show in `grep` and `read --tools` (role = tool name); entry numbers match.

**Revive a purged thread** (T3 can't reopen it): export, then start a fresh thread on the file.
1. `t3-find-thread read <id> --limit 0 > ~/Downloads/<slug>.md`: every message whole (tens of KB).
   Add a `--tools` copy only as a grep-only tool log (often 10x larger).
2. `peek <id>` gives the project; `t3_thread_launch` there with message "Continuation of purged
   thread <title>. Read ~/Downloads/<slug>.md first (tool log: …-tools.md, grep only). Then: <ask>".
Verified 2026-10: a fresh agent rebuilt task, decisions, commits and next step from the export alone.

## Opening

- In T3 chat: `t3-open-thread <id> --link` → `[title](t3-thread://v1/<threadId>)`.
- Desktop app: `t3-open-thread <id>` (only when the user asks).
- HTML reports: `t3code://threads/<env>/<url-encoded threadId>`; `t3-open-thread <id> --dry-run`
  prints it.

Install: `scripts/install` (`--check`). Fleet work: [t3-maintenance](../t3-maintenance/SKILL.md).
