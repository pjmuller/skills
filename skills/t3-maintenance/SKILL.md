---
name: t3-maintenance
description: Audit and maintain the user's T3 Code thread fleet, or mine their recent prompts for recurring instructions. Use for unexpected old or missing sidebar threads, monthly T3 cleanup, thread inventory, orchestrator fleet view of worker threads (stalled/unanswered workers, bulk unsettle or ping), bulk settle/unsettle repair, purging old transcripts, unsent composer drafts, "mine my prompts", or "/t3-maintenance". Do not use for spawning, pinging, reading, or settling one known worker thread; use t3-manage-thread for that lifecycle.
---

# T3 Maintenance

Helpers in `scripts/`, put on PATH by `scripts/install` (`--check` verifies). Flags and defaults:
`--help` on each command and subcommand.

- `t3-thread-maintenance` — audit/repair settlement state.
- `t3-fleet` — orchestrator view of worker threads; bulk unsettle/ping.
- `t3-drafts` — unsent composer text per thread, read-only. The user keeps per-thread sticky notes
  there ("DONE", "TODO read") as well as half-written prompts, so listing across threads is the
  point. `--limited` needs `t3-usage-windows` on PATH.
- `t3-my-prompts` — compact the user's own prompts for recurring-instruction mining.
- `t3-purge-threads` — delete old threads + provider transcripts (they hold secrets).
- Shared store access: `scripts/t3_store.py` (also imported by `t3-usage-windows`).

Neighbours: rate-limited threads → [t3-usage-windows](../t3-usage-windows/SKILL.md); recurring
jobs → [t3-schedule](../t3-schedule/SKILL.md); finding one past thread →
[t3-find-thread](../t3-find-thread/SKILL.md). Settle = kill the session and its sub-agents
([settle-thread.md](../t3-manage-thread/settle-thread.md)); hiding a live worker is
[t3-hide-thread](../t3-manage-thread/hide-thread.md). These helpers patch gaps in T3 itself; retire
each once upstream covers it (maintainer's inventory lives in the personal setup repository,
`decissions/t3_monkey_patches.md`).

## Hard rule — how these tools touch T3

T3's live database is never written. Reads use a read-only SQLite snapshot of the WAL projection
store; every mutation shells out to the `t3-manage-thread` helpers (`t3-settle-thread`,
`t3-ping-thread`, `t3-delete-thread`). Writing directly corrupts a running app's event-sourced store.
Only exception: `t3-purge-threads apply --mode hard`, which refuses unless T3 Code is fully closed.

Mutating subcommands are dry-run by default, capped by `--max`, re-read each candidate right before
dispatch, verify the fresh projection afterwards, and log every attempt to
`~/.local/state/t3-maintenance/actions/`. Keep all five when changing them — they make a bulk repair
recoverable.

## Thread fleet repair (`t3-thread-maintenance`)

Audit first; repair only a cohort the audit justifies: preview, read the exact IDs, repeat with
`--apply`. Cohorts are deliberately narrow and never touch deleted, archived, busy/error,
approval-pending or user-blocked threads:

- `settle-old` — threads with no explicit settle state (legacy `NULL` override), idle and unpinned
  past `--older-than`. Never overrides a deliberate keep-active.
- `revive-auto` — only threads whose *latest* settle event came from T3's own `server:auto-settle`,
  i.e. hidden by the app, not by the user.

The audit's "recent auto-settled" section is evidence, not an instruction to revive everything. It
also reports T3's inactivity window (three days when no `sidebarAutoSettleAfterDays` is stored); if
that is wrong, fix it in Settings → General, not by mass-reviving.

## Fleet view (`t3-fleet`) glossary

T3 stores no worker topology; `t3-fleet list` infers it:

- **Child of P** — the thread's *first* user message (its brief) contains
  `t3-ping-thread --thread P`; a `--from LABEL` in that brief becomes the thread's label.
- **Pinged back** — P has a user message containing `[ping from LABEL]` (any `[ping from` if the
  brief named no label) at/after the child's brief. Per-label matching keeps siblings from masking
  each other.
- **Stalled** — assistant-last AND session `stopped` AND a resolvable parent never got the ping
  back: provably dead. `unknown-parent` = same state without a resolvable parent, so just as likely
  an ordinary finished thread. `--stalled` matches both; `--stalled=strict` only the provable ones.

## Prompt patterns (`t3-my-prompts`)

Start with `--stats`. If the projected input fits the budget, dump once with `--out`; otherwise
`--outline` to find heavy projects and run separate `--project` chunks rather than raising the
budget. Judge against [rubric.md](rubric.md), the global instruction file and relevant repo
AGENTS.md files (a deduplication check, not evidence). Propose changes; edit only when asked.

## Purge (`t3-purge-threads`)

Manual request only. Gotchas the code can't show:

- `--mode soft` (T3's own `thread.delete` + transcript/log unlink) keeps **every row in SQLite**,
  secrets included; only `--mode hard` (T3 closed, `VACUUM INTO` backup first) removes them.

- Transcripts are resolved by provider session UUID (`provider_session_runtime.resume_cursor_json`)
  across every Claude home and `~/.codex/sessions` — never by cwd slug, never guessed. `unresolved`
  usually means the thread predates resume cursors or Claude's 30-day `cleanupPeriodDays` already
  removed the file.
- `--older-than` uses `updated_at`, which a bulk settle bumps: conservative (threads look younger).
