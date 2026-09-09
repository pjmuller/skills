---
name: t3-maintenance
description: Audit and maintain PJ's T3 Code thread fleet, or mine his recent prompts for recurring instructions. Use for unexpected old or missing sidebar threads, monthly T3 cleanup, thread inventory, orchestrator fleet view of worker threads (stalled/unanswered workers, bulk unsettle or ping), bulk settle/unsettle repair, "mine my prompts", or "/t3-maintenance". Do not use for spawning, pinging, reading, or settling one known worker thread; use t3-manage-thread for that lifecycle.
---

# T3 Maintenance

Five helpers in `scripts/`, symlinked onto PATH by `scripts/install` (`--check` verifies):

- `t3-thread-maintenance` — audit/repair settlement state (`audit`, `list`, `settle-old`, `revive-auto`).
- `t3-fleet` — orchestrator view of worker threads (`list`, `unsettle`, `ping`).
- `t3-limited` — threads stuck on a provider rate/usage limit (`list`, `resume`, `schedule` — one-shot LaunchAgent resume at a wall-clock time); see the `t3-resume-limited` skill.
- `t3-drafts` — unsent composer text per thread (`list`, `show`); read-only, no sending yet (PJ undecided).
- `t3-my-prompts` — compact PJ's own prompts for recurring-instruction mining.

Drafts are not in the store: they sit in the Electron renderer's localStorage
(`~/Library/Application Support/t3code/Local Storage/leveldb`, key `t3code:composer-drafts:v1`), which
`t3-drafts` copies before reading. PJ uses them as per-thread sticky notes ("DONE", "TODO read",
"then $t3-settle-thread …") as well as half-written prompts, so listing them across threads is the point.
localStorage has no per-draft timestamp — `list` sorts and filters on the thread's `updated_at`.

Recurring scheduled threads are a separate skill (`t3-schedule`). Why each of these helpers exists
and when it can go: `decissions/t3_monkey_patches.md`.

Flags and defaults: `--help` on each command and subcommand. This doc carries only what `--help`
cannot: the safety contract, the cohort semantics, and the fleet glossary.

## Hard rule — how these tools touch T3

T3's database is never written by this skill. Reads go through a read-only SQLite snapshot
transaction of the WAL projection store; every mutation shells out to the `t3-manage-thread`
helpers (`t3-settle-thread`, `t3-ping-thread`) instead. Violating this corrupts a live app's store.

The mutating subcommands are dry-run by default, cap themselves with `--max`, re-read each candidate
immediately before dispatch, verify the fresh projection afterwards, and append every attempted
action to `~/.local/state/t3-maintenance/actions/`. Keep all five when changing them — they are what
makes a bulk repair recoverable.

Settle semantics (settle = kill the session and its sub-agents) live in
[t3-manage-thread/settle-thread.md](../../../ai/skills/t3-manage-thread/settle-thread.md); hiding a
live worker is a separate helper,
[t3-hide-thread](../../../ai/skills/t3-manage-thread/hide-thread.md).

## Thread fleet repair

Audit first, repair only a cohort the audit justifies: preview, read the exact IDs, then repeat with
`--apply`.

Cohorts are deliberately narrow — each answers one question, and neither touches deleted, archived,
busy/error, approval-pending or user-blocked threads:

- `settle-old` — threads T3 never gave an explicit settle state (legacy `NULL` override), idle and
  unpinned past `--older-than`. It will not override a deliberate keep-active.
- `revive-auto` — only threads whose *latest* settle event came from T3's own `server:auto-settle`
  command, i.e. threads the app hid on its own, not ones PJ settled.

The audit's "recent auto-settled" section is evidence, not a standing instruction to revive
everything. It also reports T3's inactivity window: three days when no `sidebarAutoSettleAfterDays`
preference is stored. If that is wrong, fix it in Settings → General, not by mass-reviving.

## Fleet view (`t3-fleet`)

One line per thread, newest activity first. Built for orchestrating many 🏓 worker threads:

```bash
t3-fleet list --recent 12h --title-prefix 🏓
t3-fleet list --here --stalled              # dead workers in this repo
t3-fleet list --parent THREAD_ID --json     # my children, for scripts
```

Glossary — how the view infers the worker topology T3 itself does not store:

- **Child of P** — the thread's *first* user message (its brief) contains
  `t3-ping-thread --thread P`; a `--from LABEL` in that brief is remembered as the thread's label.
- **Pinged back** — P has a `role:user` message containing `[ping from LABEL]` (any `[ping from` if
  the brief named no label) dated at/after the child's brief. Per-label matching keeps sibling
  workers from masking each other.
- **Stalled** (tri-state) — `stalled` = assistant-last AND session `stopped` (not `ready`) AND a
  resolvable parent that never got the ping back: a worker we can prove is dead. `unknown-parent` =
  same corpse, no resolvable parent, so just as likely an ordinary finished thread. `--stalled`
  matches both; `--stalled=strict` only the provable ones.

`unsettle` and `ping` are bulk wrappers over the `t3-manage-thread` helpers: one result line per id,
continue on failure, non-zero exit if any failed, `--dry-run` prints the commands.

## Prompt patterns

Start with `t3-my-prompts --stats`. If the projected input fits the output budget, dump it once with
`--out`; if not, use `--outline` to find the heavy projects and run separate `--project` chunks
rather than raising the budget.

Judge the result against [rubric.md](rubric.md), plus global `ai/CLAUDE.md` and the relevant repo
AGENTS.md files. Existing instructions are a deduplication check, not prompt evidence. Propose
changes; edit only when asked.

## Purge old threads (`t3-purge-threads`)

Thread transcripts hold every env var/token that crossed a turn — on manual request, bulk-purge
old ones. `list` is the default and always a dry run; a cohort flag is mandatory, pinned/running/
blocked threads are never selected.

```bash
t3-purge-threads list --archived --settled --older-than 3d   # what would go (--size adds MB, slow)
t3-purge-threads apply --mode soft --archived --older-than 30d --max 50
```

`--mode soft` = `t3-delete-thread` per thread (T3's own `thread.delete`): sets `deleted_at`, stops
the session, drops attachments; the helper then unlinks the resolved Claude/Codex `.jsonl`
transcripts + provider log — **every row stays in SQLite**. `--mode hard` deletes the rows,
attachments, provider logs and the resolved Claude/Codex transcript files, `VACUUM INTO` backup
first; it refuses unless T3 Code is fully closed and `--yes` is given (the store is event-sourced —
see the row in `decissions/t3_monkey_patches.md`). Threads whose transcript can't be resolved are
counted as `unresolved`, never guessed.

Transcripts are resolved by provider session UUID (`provider_session_runtime.resume_cursor_json`:
Claude `resume`/`resumeSessionAt`, Codex `threadId`) globbed across every Claude home in
`settings.json` and `~/.codex/sessions` — never by cwd slug. "Unresolved"/"no file" today means the
transcript predates the cursor era or Claude's 30-day `cleanupPeriodDays` already removed it
(verified 2026-09-07: every miss was a March–May thread). `--older-than` uses `updated_at`, which a
bulk settle bumps — conservative (threads look younger, never older).
