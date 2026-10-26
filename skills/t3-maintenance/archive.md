# Archive internals (`t3-thread-archive`)

What is kept and dropped, caps, schema: docstring and top of `scripts/t3_archive.py`. Redaction rules
and known misses: docstring of `scripts/t3_redact.py`. Hard rules: [SKILL.md](SKILL.md#archive-t3-thread-archive).

- **Writers:** purge `apply` (its cohort), `sync` (missing or changed threads, read-only on T3's store),
  `import` (old `purged-threads-*.sqlite` slim backups). No nightly job: nothing else hard-deletes T3
  history. Re-archiving replaces a thread's rows; nothing expires. Writers share
  `t3-archive.sqlite.lock` (a second one waits).
- **Redaction order:** text is redacted before any clip (a cut could drop `PASSWORD =` and keep the
  value). `threads.redaction` stamps the rule version; a trigger makes an older writer copy fail instead
  of writing raw text; `stats` shows versions.
- **After a `VERSION` bump:** `sync` re-cuts every thread still in T3 from its full source text (its
  copy predates the rules; `--force` also rewrites current ones). `scrub` then re-redacts the rest
  (purged threads): rebuilds into a fresh file (old text would linger in FTS segments and free pages),
  verifies parity + idempotency, swaps atomically; needs one archive-sized temp file. On SSD/APFS the
  old file's blocks are freed, not wiped.
- **Sizes** (2026-10): a 6.6 GB store archives to ~450 MB in ~40 s, tool text 85% of it; on a 500 MB
  archive `sync --force` ~3 min, `scrub` ~1.5 min.
- Out of scope: Codex's `~/.codex/thread_history_1.sqlite` (T3 already holds that tool output).
