---
name: t3-maintenance
description: "Use for fleet-wide T3 housekeeping: a thread inventory, monthly cleanup, stuck or undelivered delegated tasks, threads that hit a usage limit, purging old threads (disk, secrets), \"would this secret be redacted?\", unsent composer drafts, preview tabs eating RAM, \"mine my prompts\". One thread → t3-manage-thread; finding one → t3-manage-thread (t3-find-thread)."
---

# T3 Maintenance

T3 >= 0.1. Helpers in `scripts/`, on PATH via `scripts/install` (`--check`); flags: `--help`.

| Command | For | Details |
| --- | --- | --- |
| `t3-fleet list` | one line per thread across projects; `--stalled` = delegated tasks stuck or never delivered | `--limited` / `--lineage`: [fleet.md](fleet.md) |
| `t3-drafts` | unsent composer text (the user's sticky notes: "DONE", "TODO read") | |
| `t3-my-prompts` | the user's own prompts, for recurring-instruction mining; `--skills` = threads per installed skill (use vs maintenance, unused ones too) | [below](#prompt-patterns-t3-my-prompts) |
| `t3-purge-threads` | hard-delete old threads + transcripts; `drop-v1` frees the frozen 0.0.x `state.sqlite` | [purge.md](purge.md) |
| `t3-thread-archive` | searchable archive purged threads live on in; `check` = would it redact stdin? | [below](#archive-t3-thread-archive) |
| `t3-preview-gc` | close preview tabs idle past `--idle-hours` of threads with no running turn (macOS) | |

One thread (settle, ping): native tools, [t3-manage-thread](../t3-manage-thread/SKILL.md); no bulk
wrapper. Dirty checkouts: [gitsync](../gitsync/SKILL.md). Short ids: the thread's UUID prefix,
else 8 hex of a sha1 of the opaque id; every helper takes the full id or ≥ 8 chars.

## Hard rules

- **T3's store is never written while T3 runs.** `~/.t3/userdata/statev2.sqlite` is read through a
  read-only WAL snapshot. Only `t3-purge-threads apply --yes` / `drop-v1 --yes` write, and they refuse
  unless T3 Code is fully closed.
- **Purge only on the user's explicit request**, after showing `list`; never work around a refusal
  or a keep rule ([purge.md](purge.md)).
- **Secrets:** settling or T3's own delete redact nothing; raw text stays in the store until a purge.
  Run `t3-thread-archive check` whenever a secret passes through a thread.

## Prompt patterns (`t3-my-prompts`)

Start with `--stats`. Fits the budget → dump once with `--out`; else `--outline`, then `--project`
chunks. Authorship from T3's `createdBy` (agent briefs, cross-thread sends, sub-agents dropped).
Judge against [rubric.md](rubric.md), the global instruction file and repo AGENTS.md files. Propose;
edit only when asked.

## Archive (`t3-thread-archive`)

Purge frees disk and drops secrets from T3, yet old threads stay findable: one cumulative SQLite file
`~/.t3/backups/t3-archive.sqlite` (mode 600, `$T3_ARCHIVE`), FTS5 search for
[t3-find-thread](../t3-manage-thread/find-thread.md). Search-only: only purge's `--full-backup` restores.

- **Every write redacts secrets first**, deterministically (an LLM judge would see the values again).
  Rules and known misses: docstring of `scripts/t3_redact.py`. `check` runs the same `redacted()` call:
  `true` + categories on stderr (exit 0) or `false` (exit 1); never prints values. Plain config
  (`PORT=3000`) stays `false`. Redaction is not rotation: a leaked credential stays leaked.
- **A miss → fix upstream**: version stamps, `scrub` and stale detection assume one rule set, and a fix
  protects every user. Never a local rule file or a patched installed copy (`skills-refresh` then
  blocks every update). In a `pjmuller/skills` clone: rule in `t3_redact.py`, synthetic case in
  `test_t3_redact.py` (assembled at runtime, never a token-shaped literal), bump `t3_redact.VERSION`,
  CHANGELOG line, tests green, commit or PR per AGENTS.md (no push rights: fork + PR). It goes out in
  the user's name: their sending rule applies.
- **Rule change installed → at once, without asking** (safe with T3 open): `t3-thread-archive sync`
  then `scrub` (`--dry-run` counts first). Why and how: [archive.md](archive.md).
