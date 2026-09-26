---
name: t3-find-thread
description: Fuzzy-find a past T3 Code thread by project, time window and topic keywords — deterministic FTS5 narrowing over the local thread store, then LLM judging with progressive disclosure (search → peek → grep → read). Use for "which thread did we…", "find the T3 thread where…", "where did I ask about X", "that conversation last month about Y", "/t3-find-thread".
---

# T3 Find Thread

`scripts/t3-find-thread` narrows deterministically over a read-only FTS5 cache of T3's local
store; **you** judge. Never dump a whole thread into context. Subcommands, flags, cache location:
`t3-find-thread --help`; scoring lives in the script. Without FTS5 it falls back to slow LIKE scans.

## Workflow

1. **Translate the fuzzy ask** into filters + 4–8 keyword variants: synonyms, table/file/service
   names, error strings, the tool involved. The user dictates by voice — add `--fuzzy` when a term
   looks phonetic. `--since` keeps threads *active* in the window (created earlier but touched
   inside it still match).
2. **`search`** — read the `terms` coverage column (`3/4`) first: full coverage beats raw hit count.
3. **`peek` the top 3–5** if more than one is plausible; first prompts usually settle it.
4. **`grep`** the finalists for the distinguishing fact — cheap, targeted, quotable.
5. **Loop ≤3×**: no hits → drop a term, add `--fuzzy`, widen `--since`, relax `--project`.
   Too many → `--all`, a distinguishing term, or `--role user`.
6. **Answer** in markdown: top pick + 1–2 lines of why with one evidence snippet, runner-ups as a
   table of short ids. The user picks one — *then* run `t3-open-thread <id>`, never unasked.

Terms may be quoted phrases; `ahoy` matches `ahoy_events` (the index keeps a raw and a
separator-split copy). Thread ids: any prefix ≥ 8 chars.

## Opening a thread

**Links to threads do not work inside T3 chat**: its markdown sanitizer allows only
http/https/mailto/file, http(s) opens externally, and there is no desktop deep link upstream
(pingdotgg/t3code#4996) — custom schemes and helper applets were tried and dropped. Hence short
ids, and `scripts/t3-open-thread <id>` drives the desktop app's cmd+k palette (needs Accessibility
rights; archived threads are not in the palette; log in the cache dir).

Install: `scripts/install` (`--check` verifies deps, store, symlinks). Related:
[t3-manage-thread](../t3-manage-thread/SKILL.md) (spawn/ping/read/settle),
[t3-maintenance](../t3-maintenance/SKILL.md) (fleet).
