# Finding mail without reading it all

Three deterministic steps; the agent's own `grep` does the fuzzy part.

1. **List** metadata only: `gmail-search '<query>' -n 200`. One line per message (date, from,
   subject, id). Iterate on the query here, it costs almost nothing.
2. **Export** the hits as compact Markdown: `gmail-export '<query>' -o /tmp/gmail/<topic> -n 200
   [--by-thread]`. One file per message (`YYYY-MM-DD_<id>.md`: title, date/from/to/cc, id, thread,
   attachments, then the body with quoted chains and signatures stripped) plus `index.md`
   (one line per file, date-sorted). `--by-thread` writes one file per conversation with a
   `## <date> · <sender>` section per message; use it when the answer is spread over replies.
   Re-running with a wider query only fetches new ids and rebuilds the index.
3. **Search locally**: `grep -ril 'opzeg' /tmp/gmail/<topic>`, `grep -n -i -E 'deadline|uiterlijk' …`,
   `rg -C2 …`. Read only the files that matter, `sed -n` on long ones. Need the full chain or the
   PDFs? `gmail-thread <threadId>`, `gmail-attachments <id> -o DIR` (or `gmail-export --attachments`).

4. **Clean up.** The export is a local copy of private mail. Once the answer is delivered, ask the
   user whether everything was found and whether the folder may go; on yes, `rm -rf` the whole
   topic folder. Never delete it silently (they may want a second look) and never leave it
   behind unasked.

Pass Gmail's own query language through untouched; do not invent a filter layer on top of it.

## Gmail query cheat sheet

Every row below was verified live against the API (2026-09). `-n` counts in the notes are hits.

| Need | Query |
| --- | --- |
| Person, any direction | `from:reniers OR to:reniers`, or just `reniers` (display name and address) |
| Address parts | `from:kim` also matches `kim.zwerts@…` (local part splits on `.`); `from:kbc.be` = whole domain |
| Several people | `{from:alexandru from:kim.zwerts}` (`{}` = OR); `from:(kbc.be OR juumo.io)` |
| Me | `from:me to:supplier.com`, `to:me` |
| All words (AND) | `contract opzeg` (implicit AND; `AND` also works) |
| Any word | `contract OR overeenkomst OR agreement` |
| Exact phrase | `"klant worden"`; `subject:"Re: Klant worden"` |
| Near each other | `verhuis AROUND 5 datum` |
| Exclude | `-newsletter`, `-from:noreply`, `-subject:automatisch`, `NOT factuur` |
| Subject only | `subject:(offerte OR quote)` |
| Date window | `after:2025/01/01 before:2025/06/30` (`2025-01-01` and epoch seconds also work) |
| Relative | `newer_than:6m`, `older_than:1y` (`d`, `m`, `y`) |
| Attachments | `has:attachment`, `filename:pdf`, `filename:contract.pdf`, `larger:1M`, `smaller:10K` |
| Google files | `has:drive`, `has:document`, `has:spreadsheet`, `has:youtube` |
| Where | `in:anywhere` (adds Spam/Trash), `in:sent`, `in:drafts`, `label:<name>`, `has:nouserlabels` |
| State | `is:unread`, `is:starred`, `is:important`, `category:updates` |
| Headers | `cc:`, `bcc:`, `deliveredto:`, `list:vendor.com` (mailing-list id), `rfc822msgid:<id>` |
| Grouping | `(from:kbc.be OR from:ing.be) subject:contract after:2024/01/01` |

Gotchas that cost the most time:

- **Whole words, no stemming, no substrings** (verified): `subject:lening` and `subject:leningen`
  are disjoint sets; `from:zwert` finds nothing. List variants with `OR`, or search wide (person +
  period) and let `grep` do the substring/regex work locally.
- Numbers are unreliable search terms (`400.000`, `400 000`, `400k`). Search on the people and
  the period, grep the export for the number pattern afterwards.
- Recurring facts hide in periodic mail (`subject:factuur <vendor>` gives one value per period);
  the decision sits in the first thread (`"klant worden"`, `offerte`, `voorstel`) and a change in
  a later reply. Compare across periods before answering.
- `in:inbox` fails on an archived mailbox; use `in:anywhere` when the count is suspiciously low.
- `-n` defaults are small; listing paginates at 500 per page, so `-n 300` is fine for a first
  sweep of one person's history.
- Grep noise: header lines (`attachments:`, `id:`) and signatures (phone, VAT numbers) match digit
  patterns; anchor on a currency sign, unit or nearby keyword.
- Gmail meters units per minute per user; big `--by-thread` sweeps back off automatically and a
  failed id is reported, never silently dropped. Rerun the same command to fetch the rest.
- Multi-language mailboxes: reply markers in Dutch/French/German are stripped by the exporter;
  a quoted chain that survived means an unusual client, use `--full` or `gmail-thread`.

Dig deeper:

- Google's operator list: <https://support.google.com/mail/answer/7190>
- API search semantics (`q` = the web UI syntax): <https://developers.google.com/gmail/api/guides/filtering>
- Per-user quota units per method: <https://developers.google.com/gmail/api/reference/quota>
