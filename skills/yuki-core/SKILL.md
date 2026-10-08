---
name: yuki-core
description: Pull Yuki's "Aan te leveren aankoopfacturen" (bank/card payments still missing a purchase invoice) for one quarter, as CSV or appended into the company's `<YYYY>-Q<n>` Google Sheet tab where colleagues track who hunts which invoice. Read-only Yuki SOAP client. Use from a repository's thin `yuki` wrapper that holds yuki.json.
---

# Yuki core: unmatched payments per quarter

**Intent.** Every quarter the accountant needs an invoice for each bank/card payment Yuki could not
match. This core lists those payments and appends them to a shared sheet tab; people fill the
manual columns (who, status, comment) and upload the invoices in Yuki. It never writes to Yuki.

Code: [`scripts/yuki.py`](scripts/yuki.py) (CLI), `scripts/yuki_core/` — `client.py` (zeep, read-only
allowlist), `outstanding.py` (parse, clean, quarter selection, CSV), `sheet.py` (append-only push via
the google-workspace-core CLI). Install check: `scripts/install --check`.

## Commands

Run from the wrapper's repository through `mise exec --` (it loads the API key env var):

```bash
Y() { mise exec -- uv run --quiet --project .agents/skills/yuki-core .agents/skills/yuki-core/scripts/yuki.py --config .agents/skills/yuki/yuki.json "$@"; }
Y outstanding --quarter 2026-Q3 --csv /tmp/out.csv   # stdout without --csv
Y sheet-push --quarter 2026-Q3 --dry-run             # then without --dry-run
Y sheet-push --quarter 2026-Q3 --tab "2026-Q3 test"  # push into a scratch tab
Y discover                                           # domains + administrations for a new wrapper
```

`--quarter` defaults to the last closed quarter. `sheet-push` prints a JSON summary
(`appended`, `seeded`, `created`).

## Wrapper config (`yuki.json`)

Template: [templates/yuki.example.json](templates/yuki.example.json). Keys: `company_label`,
`domain_id`, `administration_id` (from `discover`), `api_key_env` (env var holding the key, never
the key), `sheet` = `{spreadsheet_id, manual_columns, formula_columns?}` or `null` (CSV only), `gws` =
`{script, config}` (google-workspace-core `gws.py` + a Sheets-capable `workspace.json`; paths absolute,
`~`, or relative to yuki.json) or `null`; `--gws` / `--gws-config` override.

## Behaviour worth knowing

- **Data = items open today**, not a quarter-end snapshot. A quarter takes the rows dated inside it;
  older open items stay in their own quarter tab. Booked purchase invoices (`Aankoopfactuur`) are
  dropped (Yuki's screen hides them); payments of both signs stay (refunds are positive).
- **Formula columns** (optional, first in the tab): `{name, rules: [{label, pattern}]}` becomes
  `=IFS(REGEXMATCH(contact&" "&description_clean, pattern), label, …, TRUE, "")` per row (a "who
  probably owns this" hint). Written USER_ENTERED with the sheet locale's argument separator (`;` for
  nl_NL and other comma-decimal locales); never seeded; overwrite a cell by hand freely.
- **Append-only.** The tab is created on first push: header, row 1 frozen, amounts as `0.00`, widths
  for Resp/contact/description_clean, a basic filter sorted by description_clean then date (newest
  first). Later pushes require the exact header, append only unseen `item_id`s (Yuki `Item/@ID`),
  extend an existing basic filter over the new rows and never touch existing cells. A row that
  disappears from Yuki is *not* marked done; amounts of existing rows can go stale: Yuki stays the truth.
- **Seeding.** New rows matching one-to-one a row of the newest earlier quarter tab (by `item_id`, or for legacy
  tabs by date + original_amount + description_raw) get that tab's manual cells copied once.
- **Fails closed**: malformed amounts or dates, an unexpected response shape, missing or duplicate
  item ids, a header mismatch, or a read-back that does not show every new id exactly once.
- `foreign_amount`/`exchange_rate` are parsed from the Belgian-format bank text (`-1.090,21`).

## Yuki API gotchas

- Generic host `https://api.yukiworks.be/ws/<Service>.asmx`; tenant hosts (`l3038-*.yukiworks.be`)
  reject web-service calls. NL tenants use `api.yukiworks.nl`.
- SOAP names are case-sensitive: `sessionID`, `administrationID`; `sessionId` gives a misleading
  "Invalid session ID".
- API keys carry write rights; the client's allowlist (`ALLOWED` in `client.py`) is the safety net.
- Quota 1000 calls/day; one run costs 3 (Authenticate, SetCurrentDomain, OutstandingCreditorItems).
- Docs: [Yuki API (BE)](https://support.yuki.be/en/support/solutions/articles/80000787603-yuki-api-documentation),
  [Accounting web service](https://support.yuki.nl/en/support/solutions/articles/80000785926-accounting-web-service).
