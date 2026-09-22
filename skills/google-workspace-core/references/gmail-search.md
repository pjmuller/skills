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
3. **Search locally**: `grep -ril 'kredietaanvraag' /tmp/gmail/<topic>`, `grep -n -E '[0-9]{3}\.?[0-9]{3}' …`,
   `rg -C2 …`. Read only the files that matter, `sed -n` on long ones. Need the full chain or the
   PDFs? `gmail-thread <threadId>`, `gmail-attachments <id> -o DIR` (or `gmail-export --attachments`).

Pass Gmail's own query language through untouched; do not invent a filter layer on top of it.

## Gmail query cheat sheet

| Need | Query |
| --- | --- |
| Person, any direction | `from:zwerts OR to:zwerts` or just `zwerts` (matches display name and address) |
| Several people | `{from:alexandru from:kim.zwerts}` (`{}` = OR) |
| Words anywhere, all required | `lening architect` (implicit AND) |
| Any of several words | `lening OR krediet OR hypotheek` |
| Exact phrase | `"totale ontlening"` |
| Exclude | `-newsletter`, `-from:noreply` |
| Subject only | `subject:(lening OR krediet)` |
| Date window | `after:2025/01/01 before:2025/06/30`, `newer_than:6m`, `older_than:1y` |
| Attachments | `has:attachment`, `filename:pdf`, `filename:offerte.pdf`, `larger:1M` |
| Where | `in:anywhere` (also Spam/Trash), `in:sent`, `label:bank`, `is:starred` |
| Grouping | `(from:kbc.be OR from:ing.be) subject:lening after:2024/01/01` |

Gotchas that cost the most time:

- **Whole words only.** Gmail does not do substrings: `lening` misses `leningen`, `krediet` misses
  `kredietaanvraag`, `400000` misses `400.000`. List the variants with `OR`, or search wide
  (person + date window) and let `grep` do the substring/regex work locally.
- Amounts are unreliable search terms (`400.000`, `400 000`, `400k`, `€400.000`). Search on the
  people and period, grep for `[0-9]{3}[.,]?[0-9]{3}` afterwards.
- Names: the address part matters. `from:kim` matches `Kim Zwerts <kim.zwerts@kbc.be>`; a domain
  (`from:kbc.be`) catches colleagues who took over the file.
- Dates are `YYYY/MM/DD`. `newer_than:` / `older_than:` take `d`, `m`, `y`.
- `-n` defaults are small; paginated listing goes to 500 per page, so `-n 300` is fine for a
  first sweep of a person's history.
- Grep noise: header lines (`attachments:`, `id:`) and signatures (phone, VAT numbers) match digit
  patterns. Anchor on currency or context: `grep -n -E '€ ?[0-9]|[0-9] ?(eur|k\b)|ontlen|krediet'`.
- Gmail meters units per minute per user; big `--by-thread` sweeps back off automatically and a
  failed id is reported, never silently dropped. Rerun the same command to fetch the rest.
- Multi-language mailboxes: reply markers in Dutch/French/German are stripped by the exporter;
  a quoted chain that survived means an unusual client, use `--full` or `gmail-thread`.
