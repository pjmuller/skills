---
name: t3-maintenance
description: "Audit and maintain the user's T3 Code thread fleet, or mine their recent prompts for recurring instructions. Use for thread inventory across projects, monthly T3 cleanup, orchestrator fleet view (stuck or undelivered delegated tasks), purging old transcripts, unsent composer drafts, \"mine my prompts\", uncommitted/unpushed leftovers across recently active repos (one worker thread per repo), or \"/t3-maintenance\". Not for launching, messaging, reading or settling one thread: use the native T3 tools (t3-manage-thread)."
---

# T3 Maintenance

T3 >= 0.1 only. Helpers in `scripts/`, on PATH via `scripts/install` (`--check`). Flags: `--help`.

- `t3-fleet` — one line per thread across projects; kinds `top` / `launched` / `task` /
  `subagent` from V2 lineage; `--stalled` = delegated tasks stuck or never delivered;
  `--limited` / `--lineage` = compact quota/launch diagnostics ([below](#fleet-diagnostics)).
- `t3-drafts` — unsent composer text per thread (the user's sticky notes: "DONE", "TODO read").
- `t3-my-prompts` — the user's own prompts, compacted for recurring-instruction mining.
- `t3-purge-threads` — hard-delete old threads + transcripts (secrets); `drop-v1` frees the frozen
  0.0.x `state.sqlite`.
- `t3-thread-archive` — the searchable backup archive purged threads live on in
  ([below](#archive-t3-thread-archive)); `stats`, `sync`, `import` of old slim backups.
- `t3-preview-gc` — free browser-preview renderers (macOS): `--apply` closes tabs idle past `--idle-hours`
  whose thread has no running turn (same path as `t3_preview_close`; frees the renderer since T3 0.1).
- `t3-git-leftovers` — repos with uncommitted/unpushed work, one worker per repo ([below](#git-leftovers-t3-git-leftovers)).
- `scripts/t3_store.py` — shared read-only store access, schema notes, short ids.

Settling, unsettling, pinging: native `t3_thread_organize` / `t3_thread_send` / `task_status`
([t3-manage-thread](../t3-manage-thread/SKILL.md)); there is no bulk wrapper. Neighbours:
[t3-find-thread](../t3-find-thread/SKILL.md), [t3-schedule](../t3-schedule/SKILL.md).

## Hard rule

T3's store (`~/.t3/userdata/statev2.sqlite`) is read through a read-only WAL snapshot, never
written while T3 runs. Only exception: `t3-purge-threads apply --yes` / `drop-v1 --yes`, which
refuse unless T3 Code is fully closed.

Short ids: a thread's own UUID prefix (`c811b689`), else 8 hex of a sha1 of the opaque id;
every helper accepts the full id or ≥ 8 chars of that key.

## Fleet diagnostics

`t3-fleet list --limited [--json]` includes tasks/native children. Structured root
`usage_limit` on the latest **executed** failed run of a top-level/launched owner = actionable; queued/unstarted
cancelled submissions cannot hide it. Active/later successful work and settled threads
are excluded. `limitRecovery` alone is historical, never proof of a current limit.
Terminal assistant limit text (even on a completed run) = suspected, never actionable.
Delegated-task and native-child failures = `review_needed`: their parent (`recovery_owner_id`) may already
have recovered/replaced them. Includes runless failed children with rate-limit/HTTP429
terminal text (any role). Never resume those children blindly.

<details><summary>Selection, ancestry and evidence</summary>

`list --lineage` includes all child kinds; `list --descendants ID` restricts to recursive
children. Parent evidence comes from structured subagents/lineage or the first user
message's sender, never project/time proximity. Missing sender stays unknown. Actual
launch/delegate tool results corroborate known edges when structured output is available.
JSON adds current instance/model/options, first-run selection, parent evidence and limit
time/reset/status; existing keys retain their meanings. No raw tool payloads/transcripts.

Diagnostic modes default unbounded; ordinary `list` keeps 50. Any explicit/default
truncation warns on stderr, including `--json` (stdout remains a JSON array).
These commands only read; recovery/launch decisions stay with the caller/native tools.

</details>

## Git leftovers (`t3-git-leftovers`)

Repos = T3 threads of the last 14 days ∪ `--root` repos with recent commits ∪ `--always`. One
orchestrator owns a run dir; the ledger makes reruns adopt, never duplicate.

```bash
R=~/.local/state/git-leftovers/$(date +%F)
t3-git-leftovers survey --out $R --apply-ff --ignore-thread <own thread id>
t3-git-leftovers dispatch $R --model <m> --dry-run       # read the briefs, then without --dry-run
t3-git-leftovers dispatch $R --model <m> --wait          # background shell; ≤ --max-parallel live
t3-git-leftovers status $R --markdown                    # landed / protected / blocked / running
```

Workers launch via `t3-relay launch` ([relay.md](../t3-manage-thread/relay.md); async, the ledger
holds the relay id until the titled thread shows in `t3-fleet`, retried after 15 min), titled
`🧹 git leftovers <repo> <date>`, and follow [git-leftovers.md](git-leftovers.md). `status`
re-checks git and thread state; report its counts only. `blocked` = the worker stayed open for the
user; `unverified` = git could not be re-read (never counted landed).

## Prompt patterns (`t3-my-prompts`)

Start with `--stats`. Fits the budget → dump once with `--out`; else `--outline`, then separate
`--project` chunks. Authorship: T3's `createdBy` (agent briefs, cross-thread sends, sub-agents
dropped); 0.0.x history falls back to title/opener heuristics. Judge against [rubric.md](rubric.md),
the global instruction file and repo AGENTS.md files. Propose; edit only when asked.

## Purge (`t3-purge-threads`)

Manual request only.

- Cohorts `--archived` / `--settled` / `--deleted`, top-level threads; sub-agent and delegated-task
  descendants go with their root. Never: touched in the last 7 days, pinned, live run, pending
  approval, a thread a wake-up targets (enabled native scheduled task, `t3-schedule
  pending-resumes`, `t3-mail-link`), an open PR, or a real conversation (8+ typed messages or typed
  on 2+ days: the threads that get revived; one-shot briefs, scheduled runs and delegated tasks
  almost never are). `list` shows those as `kept` with the reason. A failing helper = refuse.
- `apply` first copies the cohort into the [archive](#archive-t3-thread-archive) (a failure or a
  missing thread aborts), then deletes from every thread-keyed table (V2 and the copied 0.0.x tables).
  `--full-backup` adds a `VACUUM INTO` store copy (GBs), verified (integrity + per-table row
  counts) before anything is deleted; it replaces the previous run's copy (one undo step: each
  copy holds every secret the purge removes). Old
  `purged-threads-*.sqlite` slim backups are folded into the archive, then offered for deletion.
- The archive is search-only (reviving a purged thread from it: [t3-find-thread](../t3-find-thread/SKILL.md));
  only the full backup restores. Restore: quit T3, move
  `statev2.sqlite{,-wal,-shm}` aside, copy the backup in as `statev2.sqlite`, reopen T3. Deleted
  transcript files are not in it.
- One transaction, set-based deletes (some thread columns have no usable index; per-id deletes
  took hours), progress per phase/table. Interrupted before `committed` = store unchanged (the
  archive may already hold the cohort: harmless, rerun). After it: rows gone, a rerun can't find the
  leftover transcript files; the action log lists them. During VACUUM: the store stays valid,
  space comes back on the next VACUUM / `t3 doctor --fix`.
- Keep a settled thread out of a purge: pin it. T3's own delete (sidebar multi-select) only
  tombstones: history and space stay ([#17845](https://github.com/pingdotgg/t3code/issues/17845)).
- Transcripts resolve by provider session id (V2 `nativeThreadRef`, imported resume cursors) across
  every Claude home and `~/.codex/sessions`, never by cwd slug. Attachments by id, provider log by
  T3's sanitized file name.
- `--older-than` (default 7d) uses `updated_at`, which settling bumps: conservative.

## Archive (`t3-thread-archive`)

INTENT: purge frees disk and drops secrets from T3, yet old threads stay findable. One cumulative
SQLite file, `~/.t3/backups/t3-archive.sqlite` (mode 600, `$T3_ARCHIVE`), built for rare searches:
FTS5 `entries` + `threads`. `t3-find-thread` falls back to it ([t3-find-thread](../t3-find-thread/SKILL.md)).

- Kept: thread metadata + lineage, every user/assistant message whole (+ attachment names),
  reasoning head, one entry per finished tool call (call + output head/tail, more room for
  failures), diffs, sub-agent prompt/result, questions/answers, errors. Dropped: event log, receipts, started/updated
  tool states, context-window / task / checkpoint noise, image bytes. Caps: top of `t3_archive.py`.
- Written only by `apply` (its cohort) and by hand (`sync`: missing or changed threads; read-only on
  T3's store). Re-archiving replaces a thread's rows; nothing expires. No nightly job: nothing else
  hard-deletes T3 history.
- Measured 2026-10-18: the whole 6.6 GB store archives to 445 MB (incl. the old 0.0.x backup) in
  ~40 s; tool text is 85% of it. Codex's own
  `~/.codex/thread_history_1.sqlite` is out of scope: T3 already holds its threads' tool output.
