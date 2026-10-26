# Finding mail without reading it all

Deterministic listing/export; your own `grep` does the fuzzy part. Gmail's query language passes
through untouched.

1. **List**: `gmail-search '<query>' -n 200` (date, from, subject, id per line). Iterate the query here.
2. **Export**: `gmail-export '<query>' -o /tmp/gmail/<topic> -n 200 [--by-thread]` → one Markdown file
   per message (or per conversation), quoted chains and signatures stripped, plus a date-sorted
   `index.md`. Reruns only fetch new ids.
3. **Grep locally** (`rg -C2`), read only what matters. Full chain or PDFs: `gmail-thread`,
   `gmail-attachments`, `gmail-export --attachments`.
4. **Clean up**: the export is a private-mail copy. After answering, ask whether it may go; on yes
   `rm -rf` it. Never delete silently, never leave it unasked.

## Gmail query cheat sheet

Verified live against the API (2026-09).

| Need | Query |
| --- | --- |
| Person, any direction | `from:jansen OR to:jansen`, or just `jansen` (name and address) |
| Address parts | `from:alex` matches `alex.jansen@…` (local part splits on `.`); `from:example.com` = domain |
| Several people | `{from:alex from:sam.peeters}` (`{}` = OR); `from:(bank.example OR vendor.example)` |
| Me | `from:me to:vendor.example`, `to:me` |
| All / any word | `contract cancel` (implicit AND) · `contract OR agreement` |
| Exact phrase | `"become a customer"`; `subject:"Re: Quote"` |
| Near each other | `move AROUND 5 date` |
| Exclude | `-newsletter`, `-from:noreply`, `-subject:automatic`, `NOT invoice` |
| Subject only | `subject:(offer OR quote)` |
| Date window | `after:2025/01/01 before:2025/06/30` (`2025-01-01`, epoch seconds also work) |
| Relative | `newer_than:6m`, `older_than:1y` (`d`, `m`, `y`) |
| Attachments | `has:attachment`, `filename:pdf`, `filename:contract.pdf`, `larger:1M`, `smaller:10K` |
| Google files | `has:drive`, `has:document`, `has:spreadsheet`, `has:youtube` |
| Where | `in:anywhere` (adds Spam/Trash), `in:sent`, `in:drafts`, `label:<name>`, `has:nouserlabels` |
| State | `is:unread`, `is:starred`, `is:important`, `category:updates` |
| Headers | `cc:`, `bcc:`, `deliveredto:`, `list:vendor.example`, `rfc822msgid:<id>` |

Gotchas that cost the most time:

- **Whole words, no stemming, no substrings**: `subject:loan` and `subject:loans` are disjoint;
  `from:janse` finds nothing. List variants with `OR`, or search wide (person + period) and grep.
- Numbers are unreliable terms (`400.000`, `400 000`, `400k`): search people + period, grep the
  number afterwards; anchor on a currency sign or unit (headers and signatures match digits too).
- Recurring facts hide in periodic mail (one invoice per period); the decision sits in the first
  thread and a change in a later reply. Compare across periods before answering.
- `in:inbox` misses archived mail; use `in:anywhere` when a count looks low.
- `-n` defaults are small.
- Per-user quota: big `--by-thread` sweeps back off and report failed ids; rerun to fetch the rest.
- A surviving quoted chain (Dutch/French/German markers are stripped) means an unusual client:
  `--full` or `gmail-thread`.

Deeper: [operators](https://support.google.com/mail/answer/7190) ·
[API filtering](https://developers.google.com/gmail/api/guides/filtering) ·
[quota](https://developers.google.com/gmail/api/reference/quota).
