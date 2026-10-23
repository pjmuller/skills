# Commands and local artifacts

All commands run with `uv run --no-project python <skill>/scripts/cockpit.py`. Arguments are paths/IDs, not shell snippets. Output contains artifact paths and coverage only. Failures redact upstream stdout/stderr.

```sh
cockpit.py collect --project <project> --mailbox-id <google-uuid> \
  --gws-script <google-workspace-core>/scripts/gws.py \
  --gws-config <account-wrapper>/workspace.json \
  --out <new-private-directory> --max-threads 200
cockpit.py continuation --bundle <directory> --history <earlier-bundles-or-their-parent>...
cockpit.py detail --bundle <directory> --thread-id <gmail-hex-id>
cockpit.py validate --bundle <directory> --findings <findings.json>
cockpit.py apply --bundle <directory> --findings <findings.json> \
  --thread-id <gmail-hex-id> --allow-draft-corrections
cockpit.py render --bundle <directory> --findings <findings.json> --out <report.html>
```

`collect` paginates all draft stubs (default maximum 20 pages) and reads the threads holding them, newest draft first; undrafted inbox mail is out of scope. Only `--max-threads` full threads are read. Standalone compose drafts are excluded and counted. Coverage reports draft threads discovered/checked, then the discovered-but-unchecked count; when listing is capped, **additional unlisted threads are unknown**. Gmail estimates are not exact totals. Increase the bound deliberately if the uncovered backlog warrants it.

A non-DRAFT inbound followed by a non-self SENT reply is answered. SENT self-addressed mails are ReplyPen notes. A spoofed own From without SENT remains inbound and is flagged for review. Human clients' X-Mailer headers do not prove automation. Outbound messages with genuine automation/list headers or uncertain authorship remain uncertain, not automatically answered. The model still checks actual authorship when the distinction affects an action.

- `inventory.json`: complete discovered draft-thread IDs and pagination flag; no message bodies.
- `index.json`: bounded snippets, subjects, state, health, IDs, Gmail links, coverage. Read first.
- `threads/<id>.json`: Gmail + provider-filtered rp lineage. Read only selected threads.
- `details/<id>.json`: refreshed thread, latest run body/notes, full MIME drafts, fingerprint. Read before review/correction; correction eligibility expires after four hours. Stale findings can still render with a single refresh-before-acting notice.
- `continuation.json`: per thread new / unchanged / changed / unknown against earlier bundles of the same
  mailbox, with the prior finding and `Mail-ref` ([continuity](continuity.md)). Adds `carried` rows to `index.json`.
- `findings.json`: the merged final findings; the next run's history. Keep it in the bundle.
- `config.json`: machine-local adapter/project target. Do not publish.
- `corrections/<id>.json`: original draft, hash, evidence, write/readback state; `.txt` is the full replacement body.

These files contain private mail; output directories should be outside source control. Files are mode 600, newly created directories mode 700. Do not commit them, attach entire bundles to tickets, or repeat raw content in the final response. This core needs no private ReplyPen checkout or host access. `rp run debug` is available for a narrow trace drill, with files kept in the same private evidence area.

Immediately before a write, the audit records `write_attempted`. If the update/readback raises, that status means outcome unknown: read Gmail before any retry.

Missing original run bodies (including after raw-data retention expires) refuse correction; the current Gmail body cannot prove untouched AI origin, and no trace fallback is used.

`apply` does not run automatically during rendering. It revalidates findings and current provider/run, lists current drafts to prove uniqueness, fetches the draft and thread again, and uses GWS `gmail-draft-update --expect-message`. GWS preserves headers/thread/files and verifies them on readback. Plain text must match `draft_markdown` word for word: leading `[[✏️ …]]` notes ReplyPen placed and whitespace/re-wrapping are ignored, any changed word refuses. HTML-only, multiple plain/HTML parts, unsupported encodings, edited drafts and changed threads are refused.

The HTML leg comes from ReplyPen's own placement renderer (`rp dev tools draft-render`, host `markdown.RenderDraft`), never a local copy: the current draft's HTML must equal the rendering of its markdown (word for word when the plain text needed the tolerant match) (else a draft font, signature, `body_html` or human HTML edit; refused, correct by hand), and the replacement goes in with `--html-file`. Without it GWS writes escaped text and Gmail shows raw `**markdown**`. No renderer (old `rp`/host) → refused, nothing written. Readback compares both legs after CRLF/trailing-newline normalization only (GWS serializes CRLF). A write failure may have happened after Gmail accepted the write; inspect the audit and read Gmail before retrying. Never blind-retry mutations.
