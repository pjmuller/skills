# Commands and local artifacts

Run with `uv run --no-project python <skill>/scripts/cockpit.py`. Arguments are paths/IDs, not shell
snippets. Output carries artifact paths and coverage only; failures redact upstream stdout/stderr.

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

**collect** first checks the mailbox UUID/provider/email against the GWS identity, then reads
draft threads (newest first, up to `--max-threads`) and follow-up candidates (scope in SKILL.md;
window `FOLLOWUP_DAYS`, self-addressed ReplyPen notes excluded). One `t3-mail-link index` pass tags
every row with `t3` and `new_since_t3` ([continuity](continuity.md)). Standalone compose drafts are
excluded and counted. `coverage.line` is the report's coverage sentence; when listing is
capped, **additional unlisted threads are unknown**.

Authorship: a non-DRAFT inbound followed by a non-self SENT reply is answered; SENT self-addressed
mail is a ReplyPen note. A spoofed own From without SENT stays inbound and is flagged. Human clients'
X-Mailer headers do not prove automation; outbound mail with automation/list headers or no recipient
stays uncertain, not answered.

| Artifact | Holds |
|---|---|
| `index.json` | per thread: subject, ready `link`, snippet, state, `scope`, `stale`, health, `t3`, `new_since_t3`, IDs, Gmail URL; coverage. **Read first.** |
| `inventory.json` | discovered draft-thread and follow-up IDs, truncation flags; no bodies |
| `threads/<id>.json` | Gmail + provider-filtered rp lineage; read only selected threads |
| `details/<id>.json` | refreshed thread, latest run body/notes, full MIME drafts, `fingerprint`; read before review/correction |
| `briefs/` | reviewer briefs and replacement bodies |
| `corrections/<id>.json` | original draft, hash, reason, write/readback state; `.txt`/`.html` = replacement legs |
| `config.json` | machine-local target; do not publish |

One run's scratch plus correction audits: nothing reads it the next day. Files 600, directories 700;
keep outside source control, never attach a bundle to a ticket.

**apply** takes the reviewed detail snapshot as its contract: `--fingerprint` must equal the detail
file's (a later `detail` on a changed thread invalidates the review), the snapshot is under 4 hours
old (`EVIDENCE_HOURS`) and `--run-id` is the latest run. It refuses a body that drops the original
quoted suffix, proves the draft unique from a fresh listing, refetches draft, run and thread, and
writes via GWS `gmail-draft-update --expect-message`. Plain text must match `draft_markdown` word for
word (leading placed `[[✏️ …]]` notes and re-wrapping ignored). Refused: HTML-only drafts, more than
one plain or HTML part, unsupported encodings, edited drafts, changed threads. The audit records
`write_attempted` just before the write: if update/readback raises, the outcome is unknown; read Gmail
before any retry, never blind-retry.

The HTML leg comes from ReplyPen's own renderer (`rp dev tools draft-render`), never a local copy: the
current draft's HTML must equal the rendering of its markdown (else a draft font, signature,
`body_html` or human HTML edit: refused, correct by hand). No renderer (old `rp`) → refused, nothing
written. Readback compares both legs after CRLF/trailing-newline normalization only.

**link** prints a report-safe Markdown link: escaped label, https only, query and fragment dropped.
