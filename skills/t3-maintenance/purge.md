# Purge (`t3-purge-threads`)

Manual request only. `list` (dry run) → user's go → user quits T3 → `apply --yes`.

- **Cohort:** top-level threads in `--archived` / `--settled` / `--deleted`, older than `--older-than`
  (default 7d, on `updated_at`, which settling bumps: conservative), oldest `--max` (50) per run.
  Sub-agent and delegated-task descendants go with their root.
- **Kept** (`list` shows them as `kept` + reason): pinned, live run, pending approval, a wake-up target
  (enabled native scheduled task, `t3-schedule pending-resumes`, `t3-mail-link`), an open PR, or a real
  conversation (8+ typed messages or typed on 2+ days: the threads that get revived; one-shot briefs,
  scheduled runs and delegated tasks almost never are). Keep a settled thread out: pin it.
- **Apply** archives the cohort first ([archive.md](archive.md); any failure aborts), deletes its rows in
  one transaction, then its transcripts, provider logs and attachments, then VACUUMs. Old
  `purged-threads-*.sqlite` slim backups are folded into the archive, then offered for deletion.
- **`--full-backup`** adds a `VACUUM INTO` store copy (GBs), verified (integrity + per-table row counts)
  before anything is deleted. It replaces the previous run's copy: one undo step, since each copy holds
  every secret the purge removes. Restore: quit T3, move `statev2.sqlite{,-wal,-shm}` aside, copy the
  backup in as `statev2.sqlite`, reopen T3. Deleted transcript files are not in it.
- **Interrupted** before `committed` = store unchanged (the archive may already hold the cohort:
  harmless, rerun). After it, a rerun can't find leftover transcript files; the action log
  (`~/.local/state/t3-maintenance/actions/`) lists them. During VACUUM the store stays valid; space comes
  back on the next VACUUM / `t3 doctor --fix`.
- Why this exists: T3's own delete only tombstones, history and space stay ([#17845](https://github.com/pingdotgg/t3code/issues/17845)).

Periodic review, a reminder that never applies:
`t3-schedule add --name t3-purge-review --days sun --at 10:00 --project <setup-repo> --settle-when-done
-- "Run t3-purge-threads list --settled --archived and t3-thread-archive stats. Under 50 threads: done.
Else report the cohort and ask me; on go I quit T3 and run apply --yes."`
