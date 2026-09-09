---
name: t3-find-thread
description: Fuzzy-find a past T3 Code thread by project, time window and topic keywords — deterministic FTS5 narrowing over the local thread store, then LLM judging with progressive disclosure (search → peek → grep → read). Use for "which thread did we…", "find the T3 thread where…", "where did I ask about X", "that conversation last month about Y", "/t3-find-thread".
---

# T3 Find Thread

~1.8k threads / ~33k messages live in T3's local SQLite projection. The CLI narrows
deterministically over a read-only FTS5 index; **you** judge. Never dump a whole thread into
context. Subcommands `search` / `peek` / `grep` / `read` (delegates to `t3-read-thread`), every
flag, the cache location and the scoring formula: `t3-find-thread --help`.

## Workflow

1. **Translate the fuzzy ask** into filters + 4–8 keyword variants: synonyms, table/file/service
   names, error strings, the tool involved. PJ dictates by voice — add `--fuzzy` when a term looks
   phonetic. `--project` is fuzzy too; `--since` keeps threads *active* in the window (created
   earlier but touched inside it still match).
2. **`search`** — read the `terms` coverage column (`3/4`) first: full coverage beats raw hit count.
3. **`peek` the top 3–5** if more than one is plausible; first prompts usually settle it.
4. **`grep`** the finalists for the distinguishing fact — cheap, targeted, quotable.
5. **Loop ≤3×**: no hits → drop a term, add `--fuzzy`, widen `--since`, relax `--project`.
   Too many → `--all` (every term must hit), a distinguishing term, or `--role user`.
6. **Answer** in markdown: top pick + 1–2 lines of why with one evidence snippet, runner-ups as a
   table of short ids. PJ picks one — *then* run `t3-open-thread <id>`, never unasked.

Terms may be quoted phrases; `ahoy` matches `ahoy_events` (index keeps a raw and a
separator-split copy). Thread ids: any prefix ≥ 8 chars.

## Opening a thread

**Links to threads do not work inside T3 chat**: its markdown sanitizer whitelists
http/https/mailto/file, http(s) opens externally, and there is no desktop deep link upstream
(pingdotgg/t3code#4996) — custom schemes and helper applets were tried and dropped. Hence: answer
with short ids; on PJ's pick run `t3-open-thread <id>` (focuses T3 Code, drives the cmd+k
palette; needs Accessibility for T3 Code, already granted). Archived threads are not in the
palette. `--browser` / `--dry-run` in `--help`; attempts logged under `~/.cache/t3-find-thread/`.

## Install

`scripts/install` symlinks both helpers into `~/.local/bin`; `--check` verifies deps + store +
symlinks; tests: `python3 -m unittest discover -s scripts -p 'test_*.py'`. Without FTS5 it
falls back to LIKE scans with a warning. Related: `t3-manage-thread` (spawn/ping/read/settle),
`t3-maintenance` (fleet).
