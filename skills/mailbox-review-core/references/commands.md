# Commands and local artifacts

All commands run with `uv run --no-project python <skill>/scripts/cockpit.py`. Arguments are paths/IDs, not shell snippets. Output contains artifact paths and coverage only. Failures redact upstream stdout/stderr.

```sh
cockpit.py collect --project <project> --mailbox-id <google-uuid> \
  --gws-script <google-workspace-core>/scripts/gws.py \
  --gws-config <account-wrapper>/workspace.json \
  --out <new-private-directory> [--max-threads 200] [--max-followups 300]
cockpit.py detail --bundle <directory> --thread-id <gmail-hex-id>
cockpit.py apply --bundle <directory> --thread-id <gmail-hex-id> --draft-id <gmail draft id> \
  --run-id <rp run uuid> --fingerprint <detail fingerprint> --body-file <reply.md> \
  --reason "<why>" --allow-draft-corrections
cockpit.py link --url <https url> [--label <text>]
```

`collect` paginates all draft stubs (default maximum 20 pages) and reads the threads holding them, newest draft first; only `--max-threads` of them are read. It then lists threads where we replied to someone in the last 14 days (`FOLLOWUP_DAYS`; self-addressed ReplyPen notes excluded) plus threads ReplyPen ran on in that window without leaving a draft, reads up to `--max-followups` and keeps those without a draft whose newest mail is an unanswered message from a person (`scope: followup`). One `t3-mail-link index` pass then tags every row with `t3` (owner + newest mentioning threads, `null` if T3 never saw it) and `new_since_t3`. Standalone compose drafts are excluded and counted. `coverage.line` is the report's coverage sentence; when listing is capped, **additional unlisted threads are unknown**.

A non-DRAFT inbound followed by a non-self SENT reply is answered. SENT self-addressed mails are ReplyPen notes. A spoofed own From without SENT remains inbound and is flagged for review. Human clients' X-Mailer headers do not prove automation. Outbound messages with genuine automation/list headers or uncertain authorship remain uncertain, not automatically answered.

- `inventory.json`: discovered draft-thread and follow-up candidate IDs, pagination flags; no message bodies.
- `index.json`: per thread: subject, ready `link`, bounded snippet, state, `scope`, `stale`, health, `t3`, `new_since_t3`, IDs, Gmail URL; coverage. Read first.
- `threads/<id>.json`: Gmail + provider-filtered rp lineage. Read only selected threads.
- `details/<id>.json`: refreshed thread, latest run body/notes, full MIME drafts, `fingerprint`. Read before review/correction; a correction needs it at most 4 hours old.
- `briefs/`: reviewer briefs and replacement bodies for this run.
- `corrections/<id>.json`: original draft, hash, reason, write/readback state; `.txt`/`.html` are the replacement legs.
- `config.json`: machine-local adapter/project target. Do not publish.

The directory is one run's scratch plus the correction audits: nothing reads it the next day. Files are mode 600, directories 700; keep them outside source control and never attach a bundle to a ticket.

`apply` takes the reviewed detail snapshot as its contract: the `--fingerprint` must equal the detail file's (a later `detail` on a changed thread invalidates the review), the snapshot must be under 4 hours old and `--run-id` the latest run. It refuses a body that drops the original quoted suffix. It then lists current drafts to prove uniqueness, refetches draft, run and thread, and uses GWS `gmail-draft-update --expect-message`. Plain text must match `draft_markdown` word for word: leading `[[✏️ …]]` notes ReplyPen placed and whitespace/re-wrapping are ignored, any changed word refuses. HTML-only, multiple plain/HTML parts, unsupported encodings, edited drafts and changed threads are refused. Immediately before the write the audit records `write_attempted`: if the update/readback raises, the outcome is unknown; read Gmail before any retry. Never blind-retry mutations.

The HTML leg comes from ReplyPen's own placement renderer (`rp dev tools draft-render`, host `markdown.RenderDraft`), never a local copy: the current draft's HTML must equal the rendering of its markdown (else a draft font, signature, `body_html` or human HTML edit; refused, correct by hand), and the replacement goes in with `--html-file`. No renderer (old `rp`/host) → refused, nothing written. Readback compares both legs after CRLF/trailing-newline normalization only.
